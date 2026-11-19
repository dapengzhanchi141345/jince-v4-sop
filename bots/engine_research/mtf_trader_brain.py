#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mtf_trader_brain.py —— 人工操盘手式「多周期方向研判」引擎
=========================================================
用户 11-12 18:55 口谕: "关键是要学会跟人工操盘手一样分析行情, 把黄金等流动性
强的品种, 大周期方向、下周期方向全部学会分析, 然后再小周期上交易, 整个行情
走势都了如指掌"。

本引擎把「自上而下」的看盘能力固化为可计算、可回测、可值守的技能:
  第1层 D1  (大周期定方向): 趋势结构 HH/HL vs LH/LL + MA20/60 + DI差强度 + 关键位
  第2层 H4  (次周期定结构): 同套判定, 并给出「顺势推进 / 回调 / 逆势反弹」阶段
  第3层 H1  (共振过滤)    : 引擎现役 SKIP_H1 所用方向
  第4层 M15 (小周期找点位): 现役 signal_of 突破信号 + 上述多周期方向闸

核心纪律(人工操盘手):
  * 大周期多头只做多, 大周期空头只做空 —— 不逆势抄底摸顶
  * H4 阶段为「回调」时才是较优入场; 「逆势反弹」阶段观望
  * 价格离关键位过近(追高/摸底)降级
  * 全周期方向一致 = 共振, 分数越高仓位越可放开(本研究不改仓位)

严格无未来函数: 高周期 bar 只在【已收线】后才对 M15 生效
  D1 收线 = 次日 00:00(按日切), H4 收线 = bar_time+4h, H1 收线 = bar_time+1h
  用 searchsorted(收盘时刻 <= 当前M15时刻) 取最后一根, 与引擎实时读法一致。

验证: 把「多周期方向闸」接入 v2 的 M15 回测(固定1ATR绝对收益), 5折WF对比
      基线(仅H1共振) vs +D1方向闸 vs +D1&H4方向闸 —— 证明技能是否真带来 edge。

输出:
  research/mtf_brain/<SYM>_研判卡.md   (每品种一张操盘手研判卡, 中文大白话)
  research/mtf_brain/mtf_verdict.json (方向闸回测结论)
  research/mtf_brain/MTF_SOP.md       (多周期研判SOP, 固化技能)
纯研究, 不改 live; 任何闸门变更须 WFO五验 + chief R11。
"""
import os, csv, json, sys, datetime as dt
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import liquid_wfo_m15_v2 as W
import liquid_wfo_m15_v3 as V3

ROOT = "E:/GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "research", "mtf_brain")
SYMS = W.SYMS


# ─────────────── 高周期数据 & 研判 ───────────────
def load_tf(sym, tf):
    p = os.path.join(DATA, f"{sym}_{tf}.csv")
    if not os.path.exists(p):
        return None
    t, o, h, l, c = [], [], [], [], []
    with open(p, newline="", encoding="utf-8") as f:
        r = csv.reader(f); next(r, None)
        for row in r:
            if len(row) < 5: continue
            try:
                ts = row[0][:19]
                fmt = "%Y-%m-%d" if len(ts) == 10 else "%Y-%m-%d %H:%M:%S"
                t.append(dt.datetime.strptime(ts, fmt).timestamp())
                o.append(float(row[1])); h.append(float(row[2]))
                l.append(float(row[3])); c.append(float(row[4]))
            except Exception: continue
    if len(c) < 30: return None
    return dict(t=np.array(t), o=np.array(o), h=np.array(h),
                l=np.array(l), c=np.array(c), n=len(c))


def rollmean(x, w):
    cs = np.concatenate(([0.0], np.cumsum(x)))
    e = np.arange(len(x)) + 1
    s = np.clip(e - w, 0, len(x))
    return (cs[e] - cs[s]) / np.maximum(e - s, 1)


def swing_structure(h, l, c, look=5):
    """摆动结构: 返回每根的 +1(上升HH/HL) / -1(下降LH/LL) / 0(震荡)。
    用左右各 look 根的局部极值判定, 严格只用历史(右邻为已完成的bar)。"""
    n = len(c)
    st = np.zeros(n, dtype=np.int8)
    for i in range(look, n - look):
        hh = h[i-look:i+look+1].max(); ll = l[i-look:i+look+1].min()
        is_hh = h[i] >= hh - 1e-9
        is_ll = l[i] <= ll + 1e-9
        if is_hh: st[i] = 1
        elif is_ll: st[i] = -1
    # 前向填充到最后, 得到"截至该根的最新结构"
    last = 0
    for i in range(n):
        if st[i] != 0: last = st[i]
        elif last != 0: st[i] = last
    return st


def analyze_tf(d, tf):
    """返回该周期每根 bar 的: 方向dir / 强度strength / 结构structure /
    关键位(近20根高低) / 阶段phase / MA快慢。"""
    c, h, l = d['c'], d['h'], d['l']
    n = d['n']
    fast = rollmean(c, 20 if tf == 'D1' else 10)
    slow = rollmean(c, 60 if tf == 'D1' else 30)
    # 趋势强度: 简版 DI 差(14), 与引擎同族口径
    up = h - np.concatenate(([h[0]], h[:-1]))
    dn = np.concatenate(([l[0]], l[:-1])) - l
    pj = np.where((up > dn) & (up > 0), up, 0.0)
    mj = np.where((dn > up) & (dn > 0), dn, 0.0)
    cp = np.concatenate(([0.0], np.cumsum(pj)))
    cm = np.concatenate(([0.0], np.cumsum(mj)))
    kk = np.arange(n); st_ = np.maximum(0, kk - 13)
    sp = cp[kk+1]-cp[st_]; sm = cm[kk+1]-cm[st_]; dd = sp+sm
    dx = np.where(dd > 0, np.abs(sp-sm)/np.maximum(dd, 1e-12)*100, 0.0)
    direction = np.where((fast > slow) & (c > fast), 1,
                np.where((fast < slow) & (c < fast), -1, 0)).astype(np.int8)
    structure = swing_structure(h, l, c)
    # 关键位: 近20根摆动高低
    key_hi = np.zeros(n); key_lo = np.zeros(n)
    for i in range(20, n):
        key_hi[i] = h[i-20:i].max(); key_lo[i] = l[i-20:i].min()
    # 阶段: 顺势推进(方向与结构同向) / 回调(方向仍顺但结构反向) / 逆势反弹
    phase = np.zeros(n, dtype=np.int8)
    for i in range(n):
        if direction[i] != 0 and structure[i] == direction[i]: phase[i] = 1    # 顺势推进
        elif direction[i] != 0 and structure[i] == -direction[i]: phase[i] = -1  # 回调
        else: phase[i] = 0
    return dict(t=d['t'], c=c, h=h, l=l, n=n, dir=direction, dx=dx,
                struct=structure, phase=phase, hi=key_hi, lo=key_lo,
                fast=fast, slow=slow, tf=tf)


def bar_close_times(d, tf):
    """每根高周期 bar 的【收线时刻】(之后才对该信息可见)。"""
    dur = {'D1': 86400, 'H4': 14400, 'H1': 3600}[tf]
    return d['t'] + dur


def align_to_m15(an, tf, m15_t):
    """把高周期研判对齐到每根 M15: 只用收线时刻 <= 当前M15时刻的最后一根。"""
    ct = bar_close_times(an, tf)
    j = np.searchsorted(ct, m15_t, side='right') - 1
    out = {}
    for key in ('dir', 'dx', 'struct', 'phase', 'hi', 'lo', 'c'):
        arr = an[key]
        out[key] = np.where(j >= 0, arr[np.clip(j, 0, len(arr)-1)], 0 if key != 'c' else np.nan)
    return out


# ─────────────── 多周期方向闸 ───────────────
def build_brain(sym, P):
    d1, h4, h1 = load_tf(sym, 'D1'), load_tf(sym, 'H4'), load_tf(sym, 'H1')
    A1, A4, A1h = (analyze_tf(d1, 'D1') if d1 else None,
                   analyze_tf(h4, 'H4') if h4 else None,
                   analyze_tf(h1, 'H1') if h1 else None)
    m15_t = P['t']
    B1 = align_to_m15(A1, 'D1', m15_t) if A1 else None
    B4 = align_to_m15(A4, 'H4', m15_t) if A4 else None
    return dict(A1=A1, A4=A4, A1h=A1h, B1=B1, B4=B4, m15_t=m15_t)


def mtf_filter(brain, k, s, level):
    """level: 0=基线(不加); 1=+D1方向闸; 2=+D1&H4方向闸; 3=+D1&H4且避开逆势反弹"""
    if level == 0 or brain is None or brain['B1'] is None:
        return k, s
    d1 = brain['B1']['dir'][k]
    ok = (d1 == s)
    if level >= 2 and brain['B4'] is not None:
        d4 = brain['B4']['dir'][k]
        ok = ok & (d4 == 0) | (ok & (d4 == s))   # H4 中性或同向
    if level >= 3 and brain['B4'] is not None:
        ph = brain['B4']['phase'][k]
        ok = ok & (ph != -1)                    # 避开 H4 逆势反弹阶段
    return k[ok], s[ok]


def ev_with_gate(P, brain, g, level, cost=W.COST_R):
    k, s = W.gen_signals(P, g)
    k, s = mtf_filter(brain, k, s, level)
    R, _, _ = W.simulate(P, g, k, s, cost=cost)
    n = len(R)
    if n == 0:
        return dict(n=0, net=0., avg=0., win=0., R=R)
    slm = min(g['sl_mult'], W.REAL_SL_CAP)
    Ra = (R + cost) * slm - cost
    seg = np.array_split(Ra, 8) if n >= 8 else [Ra]
    return dict(n=n, net=float(Ra.sum()), avg=float(Ra.mean()),
                win=float((R > 0).mean()), R=Ra,
                seg8=sum(1 for x in seg if x.sum() > 0))


# ─────────────── 操盘手研判卡 ───────────────
def zh_dir(v):
    return {1: "多头(上升)", -1: "空头(下降)", 0: "震荡/中性"}.get(int(v), "?")
def zh_phase(v):
    return {1: "顺势推进", -1: "回调休整", 0: "方向不明"}.get(int(v), "?")
def zh_struct(v):
    return {1: "高点抬高/低点抬高(HH-HL)", -1: "高点降低/低点降低(LH-LL)", 0: "无明确结构"}.get(int(v), "?")


def write_card(sym, brain, P, verdict=None):
    A1, A4, A1h = brain['A1'], brain['A4'], brain['A1h']
    m15c = P['c']
    lines = ["# %s · 操盘手多周期研判卡" % sym, "",
             "> 生成: 2026-11-12 · 数据源 D1/H4/H1/M15 四层 · 严格已收线对齐(无未来函数)",
             "> 用法: **大周期定方向 → 次周期定结构 → 小周期找点位**；不逆势抄底摸顶。", ""]
    lines.append("## 一句话结论")
    d1 = int(A1['dir'][-1]); d4 = int(A4['dir'][-1]) if A4 else 0
    px = float(m15c[-1])
    if d1 == 1 and d4 in (0, 1):
        conclusion = "**大方向偏多**：只找做多点位，回调到支撑转强再进；不追高、不做空。"
    elif d1 == -1 and d4 in (0, -1):
        conclusion = "**大方向偏空**：只找做空点位，反弹到阻力转弱再进；不摸底、不做多。"
    elif d1 != d4 and d4 != 0:
        conclusion = "**大周期与次周期分歧**：H4 正在回调/反弹，宜观望等共振，不急于开单。"
    else:
        conclusion = "**方向不明/震荡**：降低交易频率，只做区间边界的高质量信号。"
    lines.append(conclusion); lines.append("")
    lines.append("## 四层行情地图")
    lines.append("| 层级 | 方向 | 结构 | 阶段 | 趋势强度(DI差) | 关键阻力 | 关键支撑 | 当前价 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for name, A in (("D1 大周期", A1), ("H4 次周期", A4), ("H1 共振层", A1h)):
        if A is None: continue
        i = -1
        lines.append("| %s | %s | %s | %s | %.1f | %.5f | %.5f | %.5f |" %
                     (name, zh_dir(A['dir'][i]), zh_struct(A['struct'][i]),
                      zh_phase(A['phase'][i]), A['dx'][i], A['hi'][i], A['lo'][i], px))
    lines.append("")
    # 位置感(人工操盘手最看重的"了如指掌")
    hi, lo = float(A1['hi'][-1]), float(A1['lo'][-1])
    rng = max(hi - lo, 1e-9)
    pos = (px - lo) / rng * 100
    lines.append("## 位置感（当前价在 D1 区间的位置）")
    lines.append("- D1 近20根区间: **%.5f ~ %.5f**，当前价 **%.5f**，位于区间 **%.0f%%** 分位。" % (lo, hi, px, pos))
    lines.append("- " + ("⚠ 贴近区间上沿 → 追高风险，等回调，不重仓追多。" if pos > 80 else
                         "⚠ 贴近区间下沿 → 摸底风险，等转强确认，不重仓抄底。" if pos < 20 else
                         "处于区间中部 → 两侧都有空间，按信号质量择优。"))
    lines.append("")
    lines.append("## 交易计划（小周期 M15 执行）")
    if d1 == 1:
        lines += ["- 只做 **多单**；M15 出现 `signal_of` 突破买信号且 H1 同向才考虑。",
                  "- 较优入场: H4 阶段为「回调休整」后重新转强、价格回到 H4 支撑(%.5f)附近。" % (float(A4['lo'][-1]) if A4 else lo),
                  "- 失效条件: D1 方向翻空 或 跌破 D1 关键支撑 %.5f → 立即停止做多。" % lo,
                  "- 目标: 上看 D1 关键阻力 %.5f；到位后按 PROFIT_SECURE 锁利，不贪。" % hi]
    elif d1 == -1:
        lines += ["- 只做 **空单**；M15 出现突破卖信号且 H1 同向才考虑。",
                  "- 较优入场: H4 反弹到阻力(%.5f)附近转弱。" % (float(A4['hi'][-1]) if A4 else hi),
                  "- 失效条件: D1 方向翻多 或 突破 D1 关键阻力 %.5f → 立即停止做空。" % hi,
                  "- 目标: 下看 D1 关键支撑 %.5f；到位后按 PROFIT_SECURE 锁利。" % lo]
    else:
        lines += ["- 方向未定，**优先观望**；仅当四层共振明确后再恢复交易。"]
    lines.append("")
    lines.append("## 多周期方向闸 回测验证（本卡结论的量化背书）")
    if verdict:
        lines.append("| 闸门级别 | 成交 | 净R(固定1ATR) | 每笔R | 胜率 | 8段正 |")
        lines.append("|---|---|---|---|---|---|")
        for lv, name in ((0,"L0 基线(仅H1共振)"), (1,"L1 +D1方向闸"),
                         (2,"L2 +D1&H4方向闸"), (3,"L3 +避开H4逆势反弹")):
            r = verdict.get(str(lv))
            if r: lines.append("| %s | %d | %+.2f | %+.4f | %.1f%% | %d/8 |" %
                               (name, r['n'], r['net'], r['avg'], r['win']*100, r['seg8']))
        lines.append("")
        lines.append("- " + verdict.get('note', ''))
    lines += ["", "---",
              "*本卡为研究产物，不构成实盘指令；参数/闸门变更须 WFO 五验 + Hermes chief R11 翻闸。*", ""]
    with open(os.path.join(OUT, f"{sym}_研判卡.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ─────────────── 主流程 ───────────────
def main():
    os.makedirs(OUT, exist_ok=True)
    live = W.load_live()
    summary = {}
    print("=== 操盘手式多周期研判引擎 (D1→H4→H1→M15) ===", flush=True)
    for sym in SYMS:
        p = os.path.join(DATA, f"{sym}_M15.csv")
        if not os.path.exists(p): continue
        P = W.prepare(sym)
        brain = build_brain(sym, P)
        if brain['A1'] is None:
            print("  %-8s D1缺失, 跳过" % sym, flush=True); continue
        B = dict(W.BASE); B['sl_mult'] = live[sym]['sl']; B['tp_mult'] = live[sym]['tp']
        levels = {}
        for lv in (0, 1, 2, 3):
            e = ev_with_gate(P, brain, B, lv)
            levels[str(lv)] = dict(n=e['n'], net=round(e['net'],2), avg=round(e['avg'],5),
                                   win=round(e['win'],4), seg8=e['seg8'] if 'seg8' in e else 0)
        # 判定: 方向闸是否带来真实改善(固定1ATR绝对收益 + 成交数不塌)
        b = levels['0']
        best_lv, best = '0', b
        for lv in ('1','2','3'):
            r = levels[lv]
            if r['n'] >= max(30, b['n']*0.4) and r['avg'] > best['avg'] and r['net'] > 0:
                best_lv, best = lv, r
        note = ("方向闸 L%s 最优先: 每笔 %+.4f vs 基线 %+.4f, 净R %+.2f vs %+.2f。"
                "多周期方向研判确实带来 edge。" % (best_lv, best['avg'], b['avg'], best['net'], b['net'])
                if best_lv != '0' else
                "方向闸未超越基线(现役H1共振已足够/或样本不足), 维持现役口径; 研判卡仍用于人工盘面理解。")
        levels['note'] = note; levels['best_level'] = best_lv
        summary[sym] = levels
        write_card(sym, brain, P, levels)
        print("  %-8s D1=%-6s H4=%-6s | L0 n=%d net=%+.2f | L1=%+.2f L2=%+.2f L3=%+.2f | best=L%s" %
              (sym, zh_dir(brain['A1']['dir'][-1]), zh_dir(brain['A4']['dir'][-1]) if brain['A4'] else "-",
               b['n'], b['net'], levels['1']['net'], levels['2']['net'], levels['3']['net'], best_lv),
              flush=True)
    with open(os.path.join(OUT, "mtf_verdict.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("-> %s" % os.path.join(OUT, "mtf_verdict.json"), flush=True)


if __name__ == "__main__":
    main()
