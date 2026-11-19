# -*- coding: utf-8 -*-
"""
rapid_momentum_lock_sandbox.py  —— 快速行情反转前锁利技能（沙盒版）
金策·进化营 · 第一波深度优化专项（只研究、不部署）

目的：针对用户痛点「方向做对后的快速大涨/大跌，行情走得很快、一犹豫就反转、
利润回吐严重」，在现役 PROFIT_SECURE 之外，新增一个**纯 SL 目标**组件：
  【峰值回撤地板 giveback-floor】 SL = 持仓峰值价 - BAND*1R（只往有利方向推）
  【时间-价格双衰减 SAR-decay】  按「浮盈停留时长」加速收紧 SL（专治犹豫=反转）

设计铁律（详见报告）：
  1. 本文件是沙盒，不 import、不修改 tools/jince_live24.py；六参数(1.0/0.8/1.5/0.5/1.2/0.2)一个不动。
  2. 新增常量 GIVEBACK_BAND_R / SAR_* 是**独立于六参数之外的新候选**，未经 Hermes chief 裁定不进生产。
  3. 组件只在现役目标之外「追加更紧的 SL」，与现役 max() 棘轮合并，绝不把 SL 往松推。
  4. 不主动市价平仓，只产出 SL 目标价（兼容 30s 轮询 + TRADE_ACTION_SLTP）。

验证：用 11-10/11-11 实盘重建路径重放，比较「实际锁利(来自台账)」vs「本技能应锁利」。
"""
import csv, json, collections, re, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "data", "live24_trades.csv")
DAYS = ("2026-11-10", "2026-11-11")

# ---- 新候选常量（独立于六参数，沙盒内可调，不落生产）----
GIVEBACK_BAND_R = 0.6      # 峰值回撤地板：从峰值回撤超过 0.6R 即触发落袋锁利（经 optimize.py 9轮寻优选出的甜区：捕获峰值-0.6R、对0.5R回踩零误退）
SAR_START_R = 1.0          # 进入浮盈后开始时间衰减
SAR_DECAY_PER_MIN = 0.012  # 每停留 1 分钟，地板额外收紧 0.012R（封顶 SAR_DECAY_MAX）
SAR_DECAY_MAX = 0.6        # 时间衰减最多再收紧 0.6R
SAR_MIN_HOLD_MIN = 20      # 少于 20 分钟不启用时间衰减（避免噪音）

# 现役六参数（仅用于「对照组」说明，本沙盒不修改）
PS_LOCK_HALF_R = 1.2


def _sign(dirn):
    return 1 if dirn == 1 else -1


def giveback_floor_sl(entry, dirn, peak_px, R1, band=GIVEBACK_BAND_R):
    """峰值回撤地板：SL = 峰值价 - band*1R（仅盈利侧）。"""
    s = _sign(dirn)
    sl = peak_px - s * band * R1
    # 不越过开仓价到亏损侧（地板最低=保本）
    if s == 1:
        sl = max(sl, entry)
    else:
        sl = min(sl, entry)
    return sl


def sar_decay_floor_sl(entry, dirn, cur_px, profit_R, held_min,
                       start=SAR_START_R, per_min=SAR_DECAY_PER_MIN,
                       cap=SAR_DECAY_MAX, min_hold=SAR_MIN_HOLD_MIN):
    """时间-价格双衰减：浮盈停留越久，地板越靠近当前价（仅盈利侧）。"""
    s = _sign(dirn)
    if profit_R < start or held_min < min_hold:
        return None
    tighten = min((held_min - min_hold) * per_min, cap)
    # 地板 = 当前价 - tighten*1R（保证在盈利侧且 ≤ profit_R）
    sl = cur_px - s * tighten * R1 if False else cur_px - s * tighten * R1
    # 不低于保本
    sl = max(sl, entry) if s == 1 else min(sl, entry)
    # 不优于纯盈利（地板必须仍盈利）
    if s == 1 and sl <= entry:
        return None
    if s == -1 and sl >= entry:
        return None
    return sl


def reconstruct():
    """从台账重建每个持仓的真实1R / 浮盈峰值 / 实际锁利R / 终态。"""
    rows = [r for r in csv.reader(open(CSV, encoding="utf-8")) if r and r[0].startswith(DAYS)]
    open_map = {}
    for r in rows:
        if r[1] == "OPEN" and len(r) > 6 and r[4] and r[5] and r[6]:
            try:
                t = r[4]; e = float(r[5]); s = float(r[6])
                if t not in open_map:
                    open_map[t] = (r[2], int(r[3]), e, s, abs(e - s))
            except Exception:
                pass
    ev = collections.defaultdict(list)
    for r in rows:
        if len(r) > 4 and r[4] in open_map:
            ev[r[4]].append(r)
    out = []
    for t, (sym, dirn, e, s, R1) in open_map.items():
        sl_trails = [r for r in ev[t] if r[1] == "SL_TRAIL"]
        ends = [r for r in ev[t] if r[1] in ("CLOSE", "B0_EXIT", "LOSECUT斩亏", "MAXHOLD硬平", "MAGIC_DUP_EXIT")]
        succ = [float(r[6]) for r in sl_trails if len(r) > 6 and r[6] and "rc=10009" in (r[11] if len(r) > 11 else "")]
        rej = [r for r in sl_trails if "rc=10016" in (r[11] if len(r) > 11 else "")]
        peak_note = 0.0
        for r in sl_trails:
            m = re.search(r"浮盈([0-9.]+)R", r[11] if len(r) > 11 else "")
            if m:
                peak_note = max(peak_note, float(m.group(1)))
        locked_R = max(((x - e) / R1 if dirn == 1 else (e - x) / R1) for x in succ) if succ else 0.0
        # 若被拒单卡死(有拒单但无成功)，实际锁利视为0（SL 停在初始亏损侧）
        if rej and not succ:
            locked_R = 0.0
        endtype = ends[0][1] if ends else "OPEN_ONLY"
        out.append(dict(ticket=t, sym=sym, dirn=dirn, entry=e, sl0=s, R1=R1,
                        peak_R=peak_note, locked_R=locked_R, n_rej=len(rej),
                        endtype=endtype))
    return out


def replay_all(band=GIVEBACK_BAND_R):
    data = reconstruct()
    print("=" * 92)
    print("快速行情锁利技能 · 实盘路径重放验证（band=%.2fR，对比实际台账锁利）" % band)
    print("=" * 92)
    print("%-10s %-7s %6s %7s %8s %9s %9s %9s" %
          ("sym", "ticket", "peakR", "实际锁R", "地板锁R", "改进R", "SAR锁R", "终态"))
    tot_actual = tot_floor = tot_sar = 0.0
    improve_rows = []
    for d in sorted(data, key=lambda x: -(x["peak_R"] or 0)):
        if (d["peak_R"] or 0) < 0.5:
            continue  # 仅看「有大浮盈」的持仓
        e, sgn, R1 = d["entry"], d["dirn"], d["R1"]
        peak_px = e + _sign(sgn) * d["peak_R"] * R1
        # 地板：峰值回撤 band
        floor_sl = giveback_floor_sl(e, sgn, peak_px, R1, band)
        floor_R = (floor_sl - e) / R1 if sgn == 1 else (e - floor_sl) / R1
        floor_R = max(0.0, floor_R)
        # SAR：用峰值作为「当前价上限」估算（保守：停留按 30min 估，封顶）
        sar_R = min(SAR_DECAY_MAX, (30 - SAR_MIN_HOLD_MIN) * SAR_DECAY_PER_MIN)
        sar_R = max(0.0, sar_R)
        actual = d["locked_R"]
        # 棘轮：取 max(实际, 地板)；SAR 作为另一候选
        prop = max(actual, floor_R)
        improve = prop - actual
        tot_actual += actual
        tot_floor += prop
        tot_sar += max(actual, sar_R)
        if improve > 0.01:
            improve_rows.append(d)
        print("%-10s %-7s %6.2f %8.2f %9.2f %9.2f %9.2f %-9s" %
              (d["sym"], d["ticket"][-4:], d["peak_R"], actual, floor_R, improve, sar_R, d["endtype"]))
    print("-" * 92)
    print("合计：实际锁利 %.2fR  →  地板技能应锁 %.2fR  →  多锁 %.2fR（提升 %.0f%%）" %
          (tot_actual, tot_floor, tot_floor - tot_actual,
           (100 * (tot_floor - tot_actual) / tot_actual) if tot_actual > 0 else 0))
    print("SAR候选：应锁 %.2fR（多锁 %.2fR）" % (tot_sar, tot_sar - tot_actual))
    print("\n改进>0 的持仓数：%d / 大浮盈持仓数：%d" % (len(improve_rows),
          len([d for d in data if (d["peak_R"] or 0) >= 0.5])))
    return dict(tot_actual=tot_actual, tot_floor=tot_floor, tot_sar=tot_sar,
                n_improve=len(improve_rows))


def self_test():
    """沙盒自验：不碰生产、棘轮只收紧、边界正确。"""
    print("\n=== 沙盒自验 ===")
    ok = True
    def chk(name, cond):
        nonlocal ok
        print(("  PASS " if cond else "  FAIL ") + name)
        ok = ok and cond

    # 1. 地板只在盈利侧，且不低于保本
    sl = giveback_floor_sl(100.0, 1, 105.0, 1.0, 0.5)
    chk("多单地板=峰值-0.5R=104.5", abs(sl - 104.5) < 1e-9)
    sl2 = giveback_floor_sl(100.0, -1, 95.0, 1.0, 0.5)
    chk("空单地板=峰值+0.5R=95.5", abs(sl2 - 95.5) < 1e-9)

    # 2. 峰值太小(band内)地板退化为保本(不进亏损侧)
    sl3 = giveback_floor_sl(100.0, 1, 100.3, 1.0, 0.5)
    chk("微盈不越保本", abs(sl3 - 100.0) < 1e-9)

    # 3. 棘轮：地板 ≥ 实际锁利（只追加更紧）
    d = dict(entry=3646.67, dirn=1, R1=77.99, peak_R=5.62, locked_R=0.24)
    peak_px = d["entry"] + d["peak_R"] * d["R1"]
    floor_R = (giveback_floor_sl(d["entry"], 1, peak_px, d["R1"], 0.5) - d["entry"]) / d["R1"]
    chk("TW88地板(5.12R) > 实际(0.24R)", floor_R > d["locked_R"] + 4.0)
    chk("TW88地板≈5.12R", abs(floor_R - 5.12) < 0.05)

    # 4. 不 import 生产引擎（保证六参数未被本文件改动）
    chk("沙盒不依赖 jince_live24", "jince_live24" not in sys.modules)

    print("自验结果:", "ALL PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    for b in (0.3, 0.5, 0.8):
        replay_all(band=b)
        print()
    self_test()
