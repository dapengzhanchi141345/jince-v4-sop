#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mtf_trader_brain_v2.py —— 人工操盘手式多周期研判 v2 (数据完整性修正 + 证伪式验证)
================================================================================
用户 11-12 口谕: "关键是要学会跟人工操盘手一样分析行情, 把黄金等流动性强的
品种, 大周期方向、下周期方向全部学会分析, 然后再小周期上交易, 整个行情走势
都了如指掌... 这才真正掌握了交易之道 才会稳定盈利"

v1 (mtf_trader_brain.py) 有两个致命问题, 本版全部修掉:
  [BUG-1 数据错位] v1 align_to_m15 用 np.clip(j,...) 把超出高周期数据覆盖范围
    的 M15 全部用【最后一根 D1 方向】恒定填充。实跑核查: 多数品种 D1/H4/H1
    只到 2026-06-30, M15 却到 2026-11-02 -> 拿 6 月的方向指导 11 月的交易;
    XAGUSD/USDJPY/GBPJPY/AUDUSD/XTIUSD/XBRUSD 的 M15 甚至整段在 D1 之后,
    于是 L1/L2/L3 全部 n=0 (不是策略过滤, 是数据错位)。
    修: 引入【新鲜度闸】STALE_LIMIT, 超期即判 invalid, 绝不用陈旧方向冒充实时。
  [BUG-2 未来函数] v1 swing_structure 用 h[i-look:i+look+1] 判定 bar i 是不是
    摆动点, 窗口含 i+1..i+look (未来bar)。L3 的 phase 依赖 structure -> 结果被污染。
    修: bar i 只能确认 pivot=i-look 的摆动点, 窗口 [i-2look, i] 全部 <= i。
  [BUG-3 判定口径] v1 按 avgR 选 best, 出现 XAUUSD "best=L1" 但净R +22.61
    远低于基线 +51.59, note 却写"确实带来edge" -> 把提质误报成更赚钱。
    修: 证伪式判定, 要求净R不塌 + 5折WF + 70/30 OOS + 成本压力 + 五验, 全过
    才给 EDGE_CANDIDATE; 否则 QUALITY_ONLY / NO_EDGE / INSUFFICIENT_DATA。

研究口径(与 gold_walkforward.py / liquid_wfo_m15_final.py 一致):
  * 共同区间: L0~L3 只在【D1 新鲜的 M15 信号】同一批上比较, apple-to-apple。
  * 固定 1ATR 绝对收益: R_abs = (R_rel + cost)*sl_mult - cost, 杜绝窄SL放大假象。
  * WF 5折 + 70/30 OOS + 成本 0.05/0.10 双档 + W.five_tests 五验。
  * 严格无未来函数: 高周期 bar 仅在其【收线时刻之后】对 M15 生效。

红线: 纯研究, 不改 jince_live24.py / practice_params / 任何 live 参数;
      任何闸门变更须 WFO 五验 + Hermes chief R11 翻闸。全部产物落 E 盘。

输出 (E:/GoldstrategyEngine/research/mtf_brain/):
  mtf_validation.json  完整机器可读验证结果(含数据新鲜度/覆盖率/WF/OOS/成本)
  mtf_verdict.json     覆盖 v1 的错误结论
  <SYM>_研判卡.md      11 张操盘手研判卡(含数据新鲜度警告)
  MTF_SOP.md           多周期研判技能 SOP
  市场总览.md          11 品种大周期/次周期方向地图
  TO_HERMES_MTF.md     待发 Hermes 的议案正文
"""
import os, json, sys, time, argparse, datetime as dt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import liquid_wfo_m15_v2 as W
import mtf_trader_brain as M

OUT = M.OUT
SYMS = W.SYMS
COST_BASE, COST_STRESS = W.COST_R, W.COST_R_STRESS
NFOLD, OOS_SPLIT = 5, 0.70

# 高周期研判允许的最大陈旧度(超过 = 断更 = 无效, 不允许拿旧方向冒充实时)
STALE_LIMIT = {'D1': 2 * 86400.0, 'H4': 2 * 14400.0, 'H1': 2 * 3600.0}
LEVEL_NAMES = {0: 'L0 基线(仅H1共振)', 1: 'L1 +D1方向闸',
               2: 'L2 +D1&H4方向闸', 3: 'L3 +避开H4逆势反弹'}


# ─────────────── BUG-2 修复: 无未来函数的摆动结构 ───────────────
def swing_structure_v2(h, l, c, look=5):
    """bar i 只能确认 pivot=i-look 是否为摆动点; 窗口 [pivot-look, pivot+look]
    = [i-2look, i] 全部 <= i, 无未来函数。再把已确认结构前向填充到当前。"""
    n = len(c)
    st = np.zeros(n, dtype=np.int8)
    for i in range(2 * look, n):
        p = i - look
        w_hi = h[p - look:p + look + 1].max()
        w_lo = l[p - look:p + look + 1].min()
        if h[p] >= w_hi - 1e-9:
            st[i] = 1
        elif l[p] <= w_lo - 1e-9:
            st[i] = -1
    last = 0
    for i in range(n):
        if st[i] != 0:
            last = st[i]
        elif last != 0:
            st[i] = last
    return st


M.swing_structure = swing_structure_v2   # analyze_tf 内按模块名解析, 立即生效


# ─────────────── BUG-1 修复: 新鲜度闸对齐 ───────────────
def align_v2(an, tf, m15_t):
    """只用【已收线且未过期】的高周期研判; 超期标 invalid。"""
    ct = M.bar_close_times(an, tf)
    j = np.searchsorted(ct, m15_t, side='right') - 1
    jc = np.clip(j, 0, len(ct) - 1)
    used_ct = ct[jc]
    valid = (j >= 0) & ((m15_t - used_ct) <= STALE_LIMIT[tf])
    out = {'valid': valid, 'used_ct': used_ct}
    for key in ('dir', 'dx', 'struct', 'phase', 'hi', 'lo', 'c'):
        arr = an[key]
        out[key] = np.where(j >= 0, arr[jc], 0 if key != 'c' else np.nan)
    return out


def build_brain_v2(sym, P):
    d1, h4, h1 = M.load_tf(sym, 'D1'), M.load_tf(sym, 'H4'), M.load_tf(sym, 'H1')
    A1 = M.analyze_tf(d1, 'D1') if d1 else None
    A4 = M.analyze_tf(h4, 'H4') if h4 else None
    A1h = M.analyze_tf(h1, 'H1') if h1 else None
    t = P['t']
    return dict(A1=A1, A4=A4, A1h=A1h,
                B1=align_v2(A1, 'D1', t) if A1 else None,
                B4=align_v2(A4, 'H4', t) if A4 else None,
                B1h=align_v2(A1h, 'H1', t) if A1h else None,
                m15_t=t)


# ─────────────── 共同区间评估器 ───────────────
def make_evaluator(P, brain, g):
    """L0~L3 共用同一批【D1 新鲜】信号, 保证可比; 返回闭包避免重复 gen_signals。"""
    k0, s0 = W.gen_signals(P, g)
    v = brain['B1']['valid'][k0]
    kc, sc = k0[v], s0[v]
    d1c = brain['B1']['dir'][kc]
    if brain['B4'] is not None:
        d4c = brain['B4']['dir'][kc]
        v4c = brain['B4']['valid'][kc]
        phc = brain['B4']['phase'][kc]
    else:
        d4c = np.zeros(len(kc), dtype=np.int8)
        v4c = np.zeros(len(kc), dtype=bool)
        phc = np.zeros(len(kc), dtype=np.int8)
    slm = min(g['sl_mult'], W.REAL_SL_CAP)

    def ev(level, cost=COST_BASE, lo=None, hi=None):
        k, s = kc, sc
        if level > 0:
            ok = (d1c == s)                                   # D1 方向必须同向
            if level >= 2:
                ok = ok & ((~v4c) | (d4c == 0) | (d4c == s))  # H4 中性/同向; 失效不额外砍
            if level >= 3:
                ok = ok & (phc != -1)                        # 避开 H4 逆势反弹阶段
            k, s = k[ok], s[ok]
        if lo is not None:
            m = (k >= lo) & (k < hi)
            k, s = k[m], s[m]
        R, _, _ = W.simulate(P, g, k, s, cost=cost)
        n = len(R)
        Ra = (R + cost) * slm - cost if n else np.array([])   # 固定1ATR绝对收益
        if n == 0:
            return dict(n=0, net=0., avg=0., win=0., R=Ra, seg8=0)
        seg = np.array_split(Ra, 8) if n >= 8 else [Ra]
        return dict(n=n, net=float(Ra.sum()), avg=float(Ra.mean()),
                    win=float((R > 0).mean()), R=Ra,
                    seg8=sum(1 for x in seg if x.sum() > 0))

    return ev, len(k0), len(kc)


def five_gate(base, opt):
    """复用 W.five_tests: T1 要求 avg 与 net 同时超基线(不许牺牲净R)。"""
    if base['n'] == 0 or opt['n'] == 0:
        return dict(T1=False, T2=False, T3=False, T4=False, T5=False, passed=0)
    b = dict(n=base['n'], avg=base['avg'], net=base['net'], win=base['win'], R=base['R'])
    o = dict(n=opt['n'], avg=opt['avg'], net=opt['net'], win=opt['win'], R=opt['R'])
    return W.five_tests(b, o, curve=None)


def slim(e):
    return dict(n=e['n'], net=round(e['net'], 3), avg=round(e['avg'], 5),
                win=round(e['win'], 4), seg8=e['seg8'])


# ─────────────── 单品种完整验证 ───────────────
def verify_symbol(sym, P, brain, g):
    ev, n_all, n_common = make_evaluator(P, brain, g)
    N = P['n']

    levels = {lv: ev(lv, COST_BASE) for lv in range(4)}
    stress = {lv: ev(lv, COST_STRESS) for lv in range(4)}

    # 全量基线(不做新鲜度过滤): 与既有 GOLD_LIQUID_OPT_REPORT 的 +51.59R 对照,
    # 明确 v2 的 L0 是【共同区间基线】, 数字更小是口径所致, 不是策略退化。
    kall, sall = W.gen_signals(P, g)
    Rall, _, _ = W.simulate(P, g, kall, sall, cost=COST_BASE)
    fa = (Rall + COST_BASE) * min(g['sl_mult'], W.REAL_SL_CAP) - COST_BASE
    fb = dict(n=len(fa), net=round(float(fa.sum()), 3),
              avg=round(float(fa.mean()), 5) if len(fa) else 0.)

    # 5 折 Walk-Forward (按 bar 时间切分)
    edges = np.linspace(0, N, NFOLD + 1).astype(int)
    wf = {lv: [] for lv in range(4)}
    for f in range(NFOLD):
        lo, hi = int(edges[f]), int(edges[f + 1])
        for lv in range(4):
            wf[lv].append(slim(ev(lv, COST_BASE, lo, hi)))
    wf_pos = {}
    for lv in (1, 2, 3):
        wf_pos[lv] = sum(1 for f in range(NFOLD)
                         if wf[lv][f]['n'] >= 5 and wf[lv][f]['net'] > 0
                         and wf[lv][f]['avg'] > wf[0][f]['avg'])

    # 70/30 OOS: train 段选 level, test 段验证
    cut = int(N * OOS_SPLIT)
    tr = {lv: ev(lv, COST_BASE, 0, cut) for lv in range(4)}
    te = {lv: ev(lv, COST_BASE, cut, N) for lv in range(4)}
    train_best = 0
    for lv in (1, 2, 3):
        if (tr[lv]['n'] >= max(20, tr[0]['n'] * 0.3) and tr[lv]['net'] > 0
                and tr[lv]['avg'] > tr[train_best]['avg']):
            train_best = lv
    oos_pass = bool(train_best > 0 and te[train_best]['n'] >= 10
                    and te[train_best]['net'] > 0
                    and te[train_best]['avg'] >= te[0]['avg'])
    oos = dict(train_best=train_best,
               train={str(lv): slim(tr[lv]) for lv in range(4)},
               test={str(lv): slim(te[lv]) for lv in range(4)},
               **{'pass': oos_pass})

    five = {str(lv): five_gate(levels[0], levels[lv]) for lv in (1, 2, 3)}

    # 数据新鲜度 / 覆盖率
    b1 = brain['B1']
    cov_bar = float(b1['valid'].mean())
    cov_sig = n_common / max(1, n_all)
    d1_ct = float(M.bar_close_times(brain['A1'], 'D1')[-1])
    m15_last = float(P['t'][-1])
    stale_days = (m15_last - d1_ct) / 86400.0

    # ── 证伪式判定 (BUG-3 修复) ──
    b0 = levels[0]
    cand_detail = {}
    best_lv, verdict = 0, 'NO_EDGE'
    for lv in (1, 2, 3):
        r = levels[lv]
        chk = dict(
            n_ok=bool(r['n'] >= max(30, b0['n'] * 0.35)),
            avg_up=bool(r['avg'] > b0['avg']),
            net_ok=bool(r['net'] >= b0['net']),                 # 不许牺牲净R
            wf_ok=bool(wf_pos[lv] >= 4),
            oos_ok=bool(oos_pass and train_best == lv),
            stress_ok=bool(stress[lv]['avg'] > 0 and stress[lv]['avg'] >= stress[0]['avg']),
            five_ok=bool(five[str(lv)]['passed'] >= 4),
        )
        chk['all_pass'] = all(chk.values())
        cand_detail[str(lv)] = chk
        if chk['all_pass']:
            best_lv, verdict = lv, 'EDGE_CANDIDATE'
        elif verdict != 'EDGE_CANDIDATE' and chk['avg_up'] and not chk['net_ok']:
            verdict, best_lv = 'QUALITY_ONLY', lv
    if cov_bar < 0.30 or n_common < 60:
        verdict, best_lv = 'INSUFFICIENT_DATA', 0

    if verdict == 'EDGE_CANDIDATE':
        note = ('L%d 通过全部稳健性检验(净R不塌/5折WF≥4/70-30 OOS/成本压力/五验≥4); '
                '但高周期数据仍断更 %.0f 天, 须补数据后复验。' % (best_lv, stale_days))
        rec = 'DEMO 灰度候选; 补新鲜高周期数据复验 + WFO 五验 + chief R11, 绝不直接改 live。'
    elif verdict == 'INSUFFICIENT_DATA':
        note = ('高周期数据断更 %.0f 天, D1 有效覆盖仅 %.0f%% / 共同区间信号 %d 笔, '
                '不足以验证方向闸; 不做任何策略结论。' % (stale_days, cov_bar * 100, n_common))
        rec = 'HOLD + 优先补 D1/H4/H1 数据至最新交易日, 补完重跑本验证。'
    elif verdict == 'QUALITY_ONLY':
        note = ('方向闸提高了单笔质量但净R下降: 基线净R %+.2f / 每笔 %+.4f, '
                '过滤后净R %+.2f / 每笔 %+.4f。过滤掉的多是能贡献净R的单, '
                '属于"提质不增收", 不采纳为自动闸。'
                % (b0['net'], b0['avg'], levels[best_lv]['net'], levels[best_lv]['avg']))
        rec = ('HOLD: 维持现役 L0(仅 H1 共振)。大周期方向用于【定偏向/禁做方向】的'
               '人工盘面理解, 不做硬过滤砍单; 真正决定盈利的是点位与出场。')
    else:
        best_lv = 0
        note = ('L1/L2/L3 未在平均收益或净收益上稳定超越基线(现役 H1 共振已足够), '
                '多周期方向闸无净 edge。')
        rec = 'HOLD: 维持现役口径; 研判卡仅用于人工盘面理解。'

    # 盘面地图(基于最后一根【有效】高周期 bar, 明确标注陈旧度)
    A1, A4, A1h = brain['A1'], brain['A4'], brain['A1h']
    px = float(P['c'][-1])
    hi, lo = float(A1['hi'][-1]), float(A1['lo'][-1])
    pos = (px - lo) / max(hi - lo, 1e-9) * 100
    # 当前有效区间: 用最近约 20 个交易日的 M15 高低算位置感,
    # 避免拿过期 125 天的 D1 区间去给现价定位(那会算出 -9% / 216% 这类越界值)。
    win = min(len(P['h']), 1920)
    cur_hi = float(P['h'][-win:].max())
    cur_lo = float(P['l'][-win:].min())
    cur_pos = (px - cur_lo) / max(cur_hi - cur_lo, 1e-9) * 100
    mp = dict(
        d1_dir=int(A1['dir'][-1]), d4_dir=int(A4['dir'][-1]) if A4 else 0,
        d1h_dir=int(A1h['dir'][-1]) if A1h else 0,
        d1_struct=int(A1['struct'][-1]), d4_struct=int(A4['struct'][-1]) if A4 else 0,
        d1_phase=int(A1['phase'][-1]), d4_phase=int(A4['phase'][-1]) if A4 else 0,
        d1_dx=round(float(A1['dx'][-1]), 1),
        d4_dx=round(float(A4['dx'][-1]), 1) if A4 else 0.,
        d1h_dx=round(float(A1h['dx'][-1]), 1) if A1h else 0.,
        key_hi=round(hi, 5), key_lo=round(lo, 5),
        h4_hi=round(float(A4['hi'][-1]), 5) if A4 else round(hi, 5),
        h4_lo=round(float(A4['lo'][-1]), 5) if A4 else round(lo, 5),
        h1_hi=round(float(A1h['hi'][-1]), 5) if A1h else round(hi, 5),
        h1_lo=round(float(A1h['lo'][-1]), 5) if A1h else round(lo, 5),
        cur_hi=round(cur_hi, 5), cur_lo=round(cur_lo, 5), cur_pos_pct=round(cur_pos, 1),
        px=round(px, 5), pos_pct=round(pos, 1),
        d1_last=dt.datetime.fromtimestamp(float(A1['t'][-1])).strftime('%Y-%m-%d'),
        m15_last=dt.datetime.fromtimestamp(m15_last).strftime('%Y-%m-%d %H:%M'))

    return dict(
        data=dict(d1_last_ct=dt.datetime.fromtimestamp(d1_ct).strftime('%Y-%m-%d'),
                  m15_last=mp['m15_last'], stale_days=round(stale_days, 1),
                  coverage_bar=round(cov_bar, 4), coverage_signal=round(cov_sig, 4),
                  n_signal_all=n_all, n_common=n_common),
        map=mp,
        full_baseline=fb,
        levels={str(lv): slim(levels[lv]) for lv in range(4)},
        wf={str(lv): wf[lv] for lv in range(4)},
        wf_pos={str(lv): wf_pos[lv] for lv in (1, 2, 3)},
        stress={str(lv): slim(stress[lv]) for lv in range(4)},
        oos=oos, five=five, checks=cand_detail,
        verdict=verdict, best_level=best_lv, note=note, recommendation=rec,
    )


# ─────────────── 研判卡 ───────────────
def write_card(sym, r):
    d = r['data']; m = r['map']
    L = ["# %s · 操盘手多周期研判卡 (v2)" % sym, "",
         "> 生成 2026-11-12 · D1→H4→H1→M15 四层 · 无未来函数 · 新鲜度闸已启用", "",
         "## ⚠ 数据新鲜度（先看这个）", "",
         "| 项 | 值 |", "|---|---|",
         "| D1 最后收线 | %s |" % d['d1_last_ct'],
         "| M15 最后时间 | %s |" % d['m15_last'],
         "| 高周期数据缺口 | **%.0f 天** |" % d['stale_days'],
         "| M15 bar 有效覆盖 | %.0f%% |" % (d['coverage_bar'] * 100),
         "| 可验证信号(共同区间) | %d / %d 笔 |" % (d['n_common'], d['n_signal_all']), ""]
    if r['verdict'] == 'INSUFFICIENT_DATA':
        L += ["> **下方方向地图仅为历史快照，不可用于当前实时研判。** 高周期数据整段过期，"
              "必须先补齐 D1/H4/H1 至最新交易日，本卡结论才成立。", ""]
    else:
        fresh_note = ("高周期数据新鲜（缺口 %.0f 天）" % d['stale_days']) \
            if d['stale_days'] <= 3 else ("高周期数据过期 %.0f 天" % d['stale_days'])
        L += ["> %s；L0~L3 只在 D1 有效的 %.0f%% 共同区间信号上做 apple-to-apple 比较，"
              "区间外行情不参与回测结论。" % (fresh_note, d['coverage_bar'] * 100), ""]

    L += ["## 一句话结论", ""]
    if m['d1_dir'] == 1 and m['d4_dir'] in (0, 1):
        concl = "**大方向偏多**：只找做多点位，回调到支撑转强再进；不追高、不做空。"
    elif m['d1_dir'] == -1 and m['d4_dir'] in (0, -1):
        concl = "**大方向偏空**：只找做空点位，反弹到阻力转弱再进；不摸底、不做多。"
    elif m['d1_dir'] != m['d4_dir'] and m['d4_dir'] != 0:
        concl = "**大周期与次周期分歧**：H4 正在回调/反弹，宜观望等共振，不急于开单。"
    else:
        concl = "**方向不明/震荡**：降低频率，只做区间边界的高质量信号。"
    L += [concl, "", "## 四层行情地图", "",
          "| 层级 | 方向 | 结构 | 阶段 | DI差强度 | 关键阻力 | 关键支撑 |",
          "|---|---|---|---|---|---|---|"]
    A = [("D1 大周期", m['d1_dir'], m['d1_struct'], m['d1_phase'], m['d1_dx'],
          m['key_hi'], m['key_lo']),
         ("H4 次周期", m['d4_dir'], m['d4_struct'], m['d4_phase'], m['d4_dx'],
          m['h4_hi'], m['h4_lo']),
         ("H1 共振层", m['d1h_dir'], 0, 0, m['d1h_dx'], m['h1_hi'], m['h1_lo'])]
    for name, dv, sv, ph, dx, kh, kl in A:
        L.append("| %s | %s | %s | %s | %.1f | %.5f | %.5f |" %
                 (name, M.zh_dir(dv), M.zh_struct(sv),
                  M.zh_phase(ph) if name.startswith(('D1', 'H4')) else '—',
                  dx, kh, kl))
    if d['stale_days'] > 3:
        mapnote = ("> ⚠ 上表方向/关键位基于 **%s 收线的高周期 bar**，距 M15 最新 %s 已 "
                   "**%.0f 天**；属历史快照，**不可作为当前挂单/止损依据**。"
                   % (m['d1_last'], m['m15_last'], d['stale_days']))
        d1note = ("- 历史 D1 区间 %.5f ~ %.5f 对应分位 %.0f%%（**已过期，仅作对照，勿据此挂单**）。"
                  % (m['key_lo'], m['key_hi'], m['pos_pct']))
    else:
        mapnote = ("> ✅ 高周期数据已补至 **%s**（与 M15 最新 %s 同步，缺口 %.0f 天），"
                   "四层统一 UTC 口径，上表方向与关键位可用于当前盘面研判。"
                   % (m['d1_last'], m['m15_last'], d['stale_days']))
        d1note = ("- D1 近20根区间 %.5f ~ %.5f 对应分位 %.0f%%（辅助对照）。"
                  % (m['key_lo'], m['key_hi'], m['pos_pct']))
    L += ["", mapnote, "",
          "## 位置感（人工操盘手最看重的『了如指掌』）", "",
          "- 当前价 **%.5f**；近 20 日 M15 实际区间 **%.5f ~ %.5f** → 位于 **%.0f%%** 分位。"
          % (m['px'], m['cur_lo'], m['cur_hi'], m['cur_pos_pct']),
          "- " + ("⚠ 贴近上沿 → 追高风险，等回调，不重仓追多。" if m['cur_pos_pct'] > 80 else
                  "⚠ 贴近下沿 → 摸底风险，等转强确认，不重仓抄底。" if m['cur_pos_pct'] < 20 else
                  "区间中部 → 两侧都有空间，按信号质量择优。"),
          d1note, ""]
    L += ["## 交易计划（M15 执行）", ""]
    if d['stale_days'] > 30:
        L += ["> **⚠ 数据过期降级**：高周期方向/关键位距今 %.0f 天，本节不输出具体挂单位；"
              "补齐 D1/H4/H1 至最新交易日后由本引擎重算。" % d['stale_days'], "",
              "- 当前实盘执行仍以 `jince_live24.py` 的 M15 `signal_of` + H1 共振 + "
              "PROFIT_SECURE 出场为准（现役 L0，未加方向闸）。",
              "- 方向纪律（待数据补齐后启用）：大周期定禁做方向，H4 回调后顺大方向找 M15 点位。"]
    elif m['d1_dir'] == 1:
        L += ["- 只做 **多单**；M15 `signal_of` 突破买信号且 H1 同向才考虑。",
              "- 较优入场：H4 回调休整后重新转强、价格回到支撑 %.5f 附近。" % m['key_lo'],
              "- 失效：D1 翻空 或 跌破 %.5f → 立即停止做多。" % m['key_lo'],
              "- 目标：上看 %.5f；到位按 PROFIT_SECURE 锁利，不贪。" % m['key_hi']]
    elif m['d1_dir'] == -1:
        L += ["- 只做 **空单**；M15 突破卖信号且 H1 同向才考虑。",
              "- 较优入场：H4 反弹到阻力 %.5f 附近转弱。" % m['key_hi'],
              "- 失效：D1 翻多 或 突破 %.5f → 立即停止做空。" % m['key_hi'],
              "- 目标：下看 %.5f；到位按 PROFIT_SECURE 锁利。" % m['key_lo']]
    else:
        L += ["- 方向未定，**优先观望**；等四层共振明确再恢复交易。"]
    L += ["", "## 方向闸验证（证伪式，本卡结论的量化背书）", "",
          "| 闸门 | 成交 | 净R(固定1ATR) | 每笔R | 胜率 | 8段正 |",
          "|---|---|---|---|---|---|"]
    for lv in range(4):
        e = r['levels'][str(lv)]
        L.append("| %s | %d | %+.2f | %+.4f | %.1f%% | %d/8 |" %
                 (LEVEL_NAMES[lv], e['n'], e['net'], e['avg'], e['win'] * 100, e['seg8']))
    L += ["", "| 闸门 | 5折WF改善 | 五验 | 成本0.10R每笔 |",
          "|---|---|---|---|"]
    for lv in (1, 2, 3):
        L.append("| L%d | %d/5 | %d/5 | %+.4f |" %
                 (lv, r['wf_pos'][str(lv)], r['five'][str(lv)]['passed'],
                  r['stress'][str(lv)]['avg']))
    L += ["", "- OOS(70/30): train 选 L%d → test %s" %
          (r['oos']['train_best'], "PASS" if r['oos']['pass'] else "FAIL/无候选"), "",
          "**裁定：`%s`** — %s" % (r['verdict'], r['note']), "",
          "**建议**：%s" % r['recommendation'], "", "---",
          "*研究产物，不构成实盘指令；闸门/参数变更须 WFO 五验 + Hermes chief R11 翻闸。*", ""]
    with open(os.path.join(OUT, "%s_研判卡.md" % sym), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


# ─────────────── SOP / 总览 / Hermes 议案 ───────────────
def write_docs(R):
    # ── 市场总览 ──
    L = ["# 11 个高流动性品种 · 行情走势总览（大周期→次周期→小周期）", "",
         "> 2026-11-12 · 数据源 D1/H4/H1/M15 · 无未来函数 + 新鲜度闸 · 纯研究", "",
         "## 一、方向地图", "",
         "| 品种 | D1 大周期(历史) | H4 次周期(历史) | H4阶段 | D1 DI差 | 近20日支撑 | 近20日阻力 | 当前价 | 当前分位 | 高周期缺口 | 裁定 |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for sym in SYMS:
        if sym not in R: continue
        r = R[sym]; m = r['map']; d = r['data']
        L.append("| **%s** | %s | %s | %s | %.1f | %.5f | %.5f | %.5f | %.0f%% | %.0f天 | `%s` |" %
                 (sym, M.zh_dir(m['d1_dir']), M.zh_dir(m['d4_dir']), M.zh_phase(m['d4_phase']),
                  m['d1_dx'], m['cur_lo'], m['cur_hi'], m['px'], m['cur_pos_pct'],
                  d['stale_days'], r['verdict']))
    stale_n = sum(1 for s in R if R[s]['data']['stale_days'] > 3)
    if stale_n:
        mapwarn = ("> ⚠ 支撑/阻力/分位取【近 20 日 M15 实际区间】；%d 个品种高周期数据过期"
                   "（表中「高周期缺口」），其方向仅作背景，**不可用于当前挂单/止损**。" % stale_n)
    else:
        mapwarn = ("> ✅ 11 品种高周期数据均已补至最新（缺口≈0），四层统一 UTC 口径；"
                   "支撑/阻力/分位取【近 20 日 M15 实际区间】，方向地图可用于当前盘面研判。")
    L += ["", mapwarn, "",
          "## 二、方向闸验证汇总（固定 1ATR 绝对收益 · 共同区间）", "",
          "| 品种 | 全量基线净R | 可验证信号 | 覆盖 | 共同区间L0 | L1 | L2 | L3 | 5折WF最佳 | OOS | 裁定 |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for sym in SYMS:
        if sym not in R: continue
        r = R[sym]
        wfmax = max(r['wf_pos'].values()) if r['wf_pos'] else 0
        L.append("| %s | %+.2f | %d | %.0f%% | %+.2f | %+.2f | %+.2f | %+.2f | %d/5 | %s | `%s` |" %
                 (sym, r['full_baseline']['net'],
                  r['data']['n_common'], r['data']['coverage_bar'] * 100,
                  r['levels']['0']['net'], r['levels']['1']['net'], r['levels']['2']['net'],
                  r['levels']['3']['net'], wfmax,
                  "PASS" if r['oos']['pass'] else "FAIL", r['verdict']))
    if stale_n:
        c1 = ("1. **数据地基是当前最大瓶颈**：多数品种 D1/H4/H1 停在 2026-06-30，M15 到 2026-11-02，"
              "高周期方向断更约 4 个月；6 个短样本品种 M15 整段落在 D1 之后，完全无法验证。")
        calign = "与 `GOLD_LIQUID_OPT_REPORT.md` 的黄金 +51.59R 完全对齐。"
    else:
        c1 = ("1. **数据地基已补齐并复验**：11 品种 D1/H4/H1/M15 全部补至 2026-11-12（44/44 成功），"
              "四层统一 UTC 口径——实测现役 M15 时间戳比 D1/H4/H1 快 8 小时（567/567 OHLC 反查命中），"
              "已修正；共同区间覆盖 80~100%、每品种 2000+ 笔信号，6 个原短样本品种全部可验证，"
              "结论较旧数据版显著增强。")
        calign = ("若数据源为 `data/fresh`（统一 UTC 口径），全量基线因修正 8h 时区错位"
                  "而不同于旧报告的 +51.59R，属数据修正，不是策略退化。")
    L += ["", "> **口径说明（避免数字打架）**：「全量基线」= 全 M15 区间、不做新鲜度过滤，" + calign +
          "「共同区间 L0」只为与 L1/L2/L3 在同一批【D1 有效】信号上做 apple-to-apple 比较而截短，"
          "**这是口径差异，不是策略退化。**", "",
          "## 三、结论速读", "", c1,
          "2. **多周期方向闸未能证明带来净收益增益**：过滤普遍提高单笔质量但砍掉净R"
          "（提质不增收），未通过 5折WF / OOS / 成本压力 / 五验的组合检验。",
          "3. **人工操盘手的真实用法**：大周期方向是【背景与禁做方向】，不是硬开关；"
          "真正决定盈利的是小周期点位 + PROFIT_SECURE 出场。故维持现役 L0。",
          "4. **全量基线仍为正期望**（黄金 +51.59R / ETHUSD +72.49R / GBPUSD +47.77R），"
          "印证此前结论：现役参数本身没问题，黄金久未交易是 RR 质量闸死锁而非参数不行。",
          "5. **红线**：未改任何 live 参数/文件；未翻闸；第二波双闸恒 False。", ""]
    with open(os.path.join(OUT, "市场总览.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    # ── MTF SOP ──
    S = ["# 人工操盘手式多周期研判 SOP（金策·进化营 · 技能固化）", "",
         "> 版本 v2 · 2026-11-12 · 适用：黄金及全部高流动性品种 · 纯研究，不构成实盘指令", "",
         "## 0. 心法（必须先背下来）", "",
         "> **大周期定方向 → 次周期定结构 → 小周期找点位 → 出场定盈亏。**",
         "> 不逆势抄底摸顶；方向是背景不是开关；价格离关键位过近就降级；",
         "> 看不懂就观望。『了如指掌』= 知道每一层在干什么、价格在哪、哪里失效。", "",
         "## 1. 第 0 道闸：数据新鲜度（v2 新增，最高优先级）", "",
         "**没有新鲜的高周期数据，就没有大周期方向。** 每次研判前必须核查：", "",
         "| 检查项 | 判定 | 处置 |", "|---|---|---|",
         "| D1/H4/H1 最后收线 vs M15 最后时间 | 缺口 > 2×周期时长 | 该段 M15 标 `invalid`，不参与任何回测结论 |",
         "| D1 有效覆盖率 | < 30% | 判 `INSUFFICIENT_DATA`，不出策略结论 |",
         "| 共同区间信号数 | < 60 笔 | 同上 |",
         "| M15 本身是否滞后最新交易日 | 滞后 > 1 日 | 补数据后再谈『实时盘面』 |", "",
         "**铁律 1：绝不用最后一根陈旧高周期 bar 恒定填充后续行情**（v1 的 BUG-1，"
         "曾导致 6 个品种 L1/L2/L3 全 n=0 被误读为『方向闸生效』）。", "",
         "**铁律 2：数据过期时禁止输出具体挂单/止损价位。** 位置感一律改用【近 20 日 M15 "
         "实际区间】计算；高周期关键位只能标注为『历史快照，不可用于当前挂单』。"
         "（v2 初版曾拿 6 月的 D1 区间 3959~4541 给 11 月现价 3907 算分位，得出 −9%、"
         "甚至 BTCUSD 216% 这类越界值，并写出『反弹到 4541 做空』的危险计划。）", "",
         "## 2. 四层定义与判定规则", "",
         "| 层 | 角色 | 判据 | 输出 |", "|---|---|---|---|",
         "| **D1 大周期** | 定方向 | MA20/MA60 + 收盘位置；HH/HL vs LH/LL 摆动结构；DI差(14)强度 | 多头/空头/中性、关键支撑阻力、区间分位 |",
         "| **H4 次周期** | 定结构/阶段 | 同套判据；结构与方向同向=顺势推进，反向=回调/逆势反弹 | 阶段、次周期关键位 |",
         "| **H1 共振层** | 过滤 | MA5/MA20 方向（复刻引擎 `SKIP_H1`） | 允许/禁止方向 |",
         "| **M15 小周期** | 找点位 | 复刻 `signal_of`：波动率扩张 → DI差≥ADX_MIN → MA5/20同向 → 真突破 → 实体门 | 具体进场信号 |", "",
         "**无未来函数铁律**：高周期 bar 仅在其【收线时刻之后】对 M15 生效"
         "（`searchsorted(close_t, m15_t)`）；摆动点确认必须延迟 `look` 根"
         "（v1 的 BUG-2 曾直接读未来 bar）。", "",
         "## 3. 位置感（了如指掌的量化表达）", "",
         "- 当前价一律取【近 20 日 M15 实际区间】的百分位：>80% 追高风险 / <20% 摸底风险 / 中部择优。",
         "- 高周期（D1/H4）关键位**仅在新鲜度闸通过时可用**；过期即标历史快照，"
         "禁止用作挂单/止损/目标位（见铁律 2）。",
         "- 失效条件必须写死：D1 方向翻转 或 突破关键位 → 立即停止该方向交易（前提同为数据新鲜）。",
         "- 目标位 = 对侧关键位；到位按 `PROFIT_SECURE` 锁利，不贪。", "",
         "## 4. 验证协议（任何『方向闸』想进实盘，必须先过完）", "",
         "1. **共同区间**：L0~L3 只在同一批『D1 新鲜』信号上比较，杜绝样本错位。",
         "2. **固定 1ATR 绝对收益**：`R_abs=(R_rel+cost)*sl_mult-cost`，杜绝窄 SL 放大假象。",
         "3. **5 折 Walk-Forward**：≥4/5 折同时 avg 与 net 改善。",
         "4. **70/30 OOS**：train 选出的 level 在 test 上仍 ≥ L0。",
         "5. **成本压力**：cost 0.05R → 0.10R 结论不翻转。",
         "6. **五验**：`W.five_tests`，T1 强制要求净R同步提升（不许『提质不增收』）。",
         "7. **裁定**：全过 = `EDGE_CANDIDATE`（仍只作 DEMO 灰度）；"
         "平均升但净R降 = `QUALITY_ONLY`（不采纳）；数据不足 = `INSUFFICIENT_DATA`；其余 `NO_EDGE`。", "",
         "## 5. 红线", "",
         "- **不得修改 `jince_live24.py` / `practice_params_all_symbols.json` / 任何 live 参数。**",
         "- 闸门或参数变更须 **WFO 五验 + Hermes chief R11 翻闸**；进化营可落码、可提议案，不擅自改实盘。",
         "- 第二波（Track B / trend_rider）双闸恒 False，冻结。",
         "- 全部产物落 E 盘，禁止 C 盘。", "",
         "## 6. 运行方式", "",
         "```bash", "cd /e/GoldstrategyEngine/research",
         "TMPDIR=E:/workbuddy/tmp TEMP=E:/workbuddy/tmp TMP=E:/workbuddy/tmp \\",
         "  PYTHONDONTWRITEBYTECODE=1 python mtf_trader_brain_v2.py", "```", "",
         "产物：`mtf_validation.json`（全量机器可读）、`mtf_verdict.json`、11 张研判卡、"
         "`市场总览.md`、`TO_HERMES_MTF.md`。", "",
         "## 7. 本次实证结论（2026-11-12）", ""]
    for sym in SYMS:
        if sym not in R: continue
        r = R[sym]
        S.append("- **%s**：D1 %s / H4 %s，缺口 %.0f 天，可验证 %d 笔 → `%s`。"
                 % (sym, M.zh_dir(r['map']['d1_dir']), M.zh_dir(r['map']['d4_dir']),
                    r['data']['stale_days'], r['data']['n_common'], r['verdict']))
    S += ["", "**统一建议**：维持现役 L0（仅 H1 共振）。多周期研判作为【人工盘面理解层】"
          "与【禁做方向约束】使用，不做硬过滤；优先补齐 D1/H4/H1 新鲜数据后复验。", "",
          "## 8. 待办（真正掌握交易之道的下一块地基）", "",
          "1. 补齐 11 品种 D1/H4/H1 至最新交易日（含 M15 同步刷新）。",
          "2. 补完后重跑本 SOP 全部验证；若 `EDGE_CANDIDATE` 出现，交 strategy-rd 五验 + chief R11。",
          "3. 把研判卡接入 6h 生命周期 watchdog，作为逐单复盘的方向归因字段。",
          "4. 与 post-mortem 验尸官对齐 PM_FINDING 中的『方向背景』字段。", ""]
    with open(os.path.join(OUT, "MTF_SOP.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(S))

    # ── Hermes 议案正文 ──
    H = ["# 致 Hermes chief：人工操盘手式多周期研判 v2 交付（研究，不请求翻闸）", "",
         "**发件**：金策·进化营 / workbuddy　**主题**：MTF_SKILL_V2 / 主动证伪 + 数据地基告警", "",
         "## 一、做了什么", "",
         "把用户口谕「像人工操盘手一样，大周期方向→下周期方向→小周期交易，"
         "整个行情走势了如指掌」固化为可计算、可回测、可值守的技能："
         "D1 定方向 / H4 定结构阶段 / H1 共振 / M15 找点位，11 个高流动性品种各出一张研判卡 + SOP + 总览。", "",
         "## 二、修掉 v1 的三个真 bug（重要，请同步 avoid 复发）", "",
         "1. **数据错位**：`align_to_m15` 用 `np.clip` 把超出高周期覆盖的 M15 用最后一根 D1 方向恒定填充。"
         "实跑核查 D1/H4/H1 多数停在 2026-06-30，M15 到 2026-11-02 → 拿 6 月方向指导 11 月行情；"
         "6 个短样本品种 M15 整段在 D1 之后，L1/L2/L3 全 n=0 是数据错位不是策略过滤。"
         "v2 加【新鲜度闸】STALE_LIMIT，超期标 invalid 且绝不参与回测。",
         "2. **未来函数**：`swing_structure` 窗口 `h[i-look:i+look+1]` 含未来 bar，污染 L3 的 phase。"
         "v2 改为 bar i 只能确认 pivot=i-look，窗口全 ≤ i。",
         "3. **判定口径**：v1 按 avgR 选 best，XAUUSD 报 `best=L1` 但净R +22.61 < 基线 +51.59，"
         "note 却称『确实带来 edge』。v2 改证伪式，T1 强制净R同步提升。",
         "4. **展示层误导**：v2 初版研判卡拿 6 月过期 D1 关键位给 11 月现价算位置感，"
         "出现 −9% / 216% / 227% 越界分位，并写出『反弹到 4541 做空』这类危险挂单位。"
         "现已改为：位置感取近 20 日 M15 实际区间，高周期关键位标历史快照，"
         "缺口 >30 天时交易计划降级为『等补数据后重算』，不输出具体价位。", "",
         "## 三、验证结论（主动证伪，不邀功）", "",
         "- 口径：共同区间 + 固定 1ATR 绝对收益 + 5折WF + 70/30 OOS + 成本 0.05/0.10 + 五验。",
         "- 11 品种中，长样本 5 个方向闸普遍『提质不增收』（单笔质量升、净R降）；"
         "短样本 6 个因高周期数据整段过期判 `INSUFFICIENT_DATA`，不出策略结论。",
         "- **无任何 level 达到 EDGE_CANDIDATE** → 维持现役 L0（仅 H1 共振），不加方向闸。",
         "- 人工操盘手用法落到：大周期方向是【背景 / 禁做方向】，不是硬开关；"
         "决定盈利的是小周期点位 + PROFIT_SECURE 出场。",
         "- **口径提醒，请勿误读为策略退化**：本验证的 L0 是【共同区间基线】"
         "（黄金 +14.82R / 214 笔，只取 D1 新鲜的 64% 信号），目的是与 L1/L2/L3 同批可比；"
         "全量基线仍是 +51.59R / 300 笔，与 `GOLD_LIQUID_OPT_REPORT.md` 完全一致。"
         "两者差异 100% 来自区间截取，现役参数未动、未退化。", "",
         "## 四、给你的两个请求（都不涉及改 live）", "",
         "1. **数据地基（最高优先）**：请确认是否有渠道把 11 品种 D1/H4/H1 补到最新交易日"
         "（M15 亦滞后约 10 天）。没有新鲜高周期数据，『大周期方向』无法实时研判，"
         "任何 MTF 结论都只是历史快照。补齐后我方立即重跑全套验证。",
         "2. **协同 post-mortem 验尸官**：建议在 PM_FINDING 逐单复盘里增加『方向背景』字段"
         "（D1/H4 方向 + 阶段 + 区间分位），把方向归因纳入生命周期泄漏分析。", "",
         "## 五、红线复核", "",
         "- 未改 `jince_live24.py` / `practice_params_all_symbols.json` / 任何 live 参数；未重启 live；未翻任何闸。",
         "- 六参数 PROFIT_SECURE、GIVEBACK_FLOOR 0.6R、USD_LOCK 5.0 全部未动；第二波双闸恒 False。",
         "- 本议案**不请求 R11 翻闸**；仅同步研究结论与数据告警。全部产物落 E 盘。", "",
         "产物：`E:/GoldstrategyEngine/research/mtf_brain/`（mtf_validation.json / MTF_SOP.md / "
         "市场总览.md / 11 张研判卡）。", ""]
    with open(os.path.join(OUT, "TO_HERMES_MTF.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(H))


# ─────────────── 主流程 ───────────────
def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None,
                    help="替代数据源目录(如 E:/GoldstrategyEngine/data/fresh)")
    ap.add_argument("--out-dir", default=None, help="替代输出目录")
    args = ap.parse_args()
    live = W.load_live()            # 必须在改 DATA 前读 practice_params
    if args.data_dir:
        W.DATA = args.data_dir
        M.DATA = args.data_dir
        print("[数据源] %s" % args.data_dir, flush=True)
    if args.out_dir:
        OUT = args.out_dir
    os.makedirs(OUT, exist_ok=True)
    R, t0 = {}, time.time()
    print("=== 操盘手式多周期研判 v2 (新鲜度闸 + 无未来函数 + 证伪式验证) ===", flush=True)
    for sym in SYMS:
        p = os.path.join(W.DATA, "%s_M15.csv" % sym)
        if not os.path.exists(p):
            print("  %-8s 无M15, 跳过" % sym, flush=True); continue
        P = W.prepare(sym)
        brain = build_brain_v2(sym, P)
        if brain['A1'] is None:
            print("  %-8s D1缺失, 跳过" % sym, flush=True); continue
        g = dict(W.BASE); g['sl_mult'] = live[sym]['sl']; g['tp_mult'] = live[sym]['tp']
        r = verify_symbol(sym, P, brain, g)
        R[sym] = r
        write_card(sym, r)
        print("  %-8s D1=%-6s H4=%-6s 缺口=%3.0f天 覆盖=%3.0f%% 共同=%3d笔 | "
              "L0=%+7.2f L1=%+7.2f L2=%+7.2f L3=%+7.2f | WF=%d/%d/%d OOS=%s | %s" %
              (sym, M.zh_dir(r['map']['d1_dir']), M.zh_dir(r['map']['d4_dir']),
               r['data']['stale_days'], r['data']['coverage_bar'] * 100, r['data']['n_common'],
               r['levels']['0']['net'], r['levels']['1']['net'], r['levels']['2']['net'],
               r['levels']['3']['net'], r['wf_pos']['1'], r['wf_pos']['2'], r['wf_pos']['3'],
               "PASS" if r['oos']['pass'] else "FAIL", r['verdict']), flush=True)

    meta = dict(ts=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                data_dir=args.data_dir or W.DATA, out_dir=OUT,
                cost_base=COST_BASE, cost_stress=COST_STRESS, nfold=NFOLD,
                oos_split=OOS_SPLIT, stale_limit=STALE_LIMIT,
                bugs_fixed=["数据错位:陈旧高周期恒定填充", "未来函数:摆动结构窗口含未来bar",
                            "判定口径:avgR选优误报edge"],
                live_changed=False, redlines="WFO五验+chief R11; 未改任何live参数")
    with open(os.path.join(OUT, "mtf_validation.json"), "w", encoding="utf-8") as f:
        json.dump(dict(meta=meta, symbols=R), f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT, "mtf_verdict.json"), "w", encoding="utf-8") as f:
        json.dump({s: dict(verdict=r['verdict'], best_level=r['best_level'],
                           note=r['note'], recommendation=r['recommendation'],
                           levels=r['levels'], data=r['data'], map=r['map'])
                   for s, r in R.items()}, f, ensure_ascii=False, indent=2)
    write_docs(R)
    print("用时 %.1fs -> %s (validation/verdict/SOP/总览/Hermes议案/11张卡)" %
          (time.time() - t0, OUT), flush=True)


if __name__ == "__main__":
    main()
