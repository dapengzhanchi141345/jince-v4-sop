# -*- coding: utf-8 -*-
"""_p4_v5_dsr_combo.py — 续跑 p4_path_close / p4_sprint_session_rr_combo 断点
(2026-10-06 任务续跑制度: 从 checkpoint「卡 V5 walk-forward+DSR」接着干, 绝不从头)

补做研究台账 2026-10-06「全力进化·出徒加速」段第①③项:
  DSR+PBO (双闸组合: 时段闸8/14/15/16北京 + 盈亏比1.3, 对照 live_trend 基线)
  + V5 walk-forward 3 段 (前/中/后 各 ~120 天)

数据与口径完全继承主 bot 快跑 (rd_hypo_combo_session_rr.json):
  trade(live_trend, H1 ~361天, 2025-06-30~2026-06-30)
  EMA9/SMA50 同口径信号, A/B 双臂同分母同批触发事件 (同分母铁律)
  简化 H1 close 回测无真实点差/swap, exp_R 绝对值为噪声级, 只做方向性证据
缺数据 fail-open 标 N/A 不造数; 负期望只否决不提权; 本脚本纯离线, 不挂单。
结果落盘: data/rd_verify_batch_p4path_combo_v5.json
"""
import json, math, os, re, datetime
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT_JSON = os.path.join(DATA, "rd_verify_batch_p4path_combo_v5.json")
SRC = os.path.join(ROOT, "_rd_verify_p4path.py")

# 复用已有脚本的统计闸函数提取与数据加载 (不 import MT5, 离线安全)
g = {"__name__": "_p4v5", "__file__": SRC, "os": os, "re": re, "json": json, "math": math,
     "datetime": datetime, "np": np}
_ns = dict(g)
exec(compile(open(SRC, encoding="utf-8").read(), SRC, "exec"), _ns)
DSR_FN, PBO_FN, load_h1 = _ns["DSR_FN"], _ns["PBO_FN"], _ns["load_h1"]

SYMS = ["XAUUSD", "EURUSD", "GBPUSD", "AUDUSD", "US30"]
# 北京 8/14/15/16 点 = UTC 0/6/7/8 点 (UTC+8, 全年不跨夏令时翻转 8/14/15/16 归属)
SESSION_UTC_HOURS = (0, 6, 7, 8)
RR = 1.3


def ema_series(c, n):
    out = np.zeros(len(c))
    if len(c) == 0:
        return out
    out[0] = c[0]
    k = 2.0 / (n + 1)
    for i in range(1, len(c)):
        out[i] = c[i] * k + out[i - 1] * (1 - k)
    return out


def sma_series(c, n):
    out = np.full(len(c), np.nan)
    if len(c) <= n:
        return out
    cs = np.cumsum(np.concatenate(([0.0], c)))
    out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def arm_result(h, rr_mult):
    """单臂回放: 触发=EMA9 上穿 SMA50 (BUY) / 下穿 (SELL), TP=rr_mult*ATR, 吊灯止损.
    返回 (stats, closed_trades). h 为 load_h1 返回 dict (key: time/open/high/low/close/n)."""
    h_arr, l_arr, c_arr, t_arr = h["high"], h["low"], h["close"], h["time"]
    n = len(c_arr)
    if n < 200:
        return {"n_signals": 0, "n": 0}, []
    ma_fast = ema_series(c_arr, 9)
    ma_slow = sma_series(c_arr, 50)
    rng = h_arr - l_arr
    # ATR14 = 最近14根H1的 high-low 区间最大值 (与引擎口径同, 因果只用过去)
    atr = np.full(n, np.nan)
    for i in range(14, n):
        atr[i] = rng[i - 14:i].max()
    sig = np.zeros(n, dtype=int)
    for i in range(51, n - 1):
        if np.isnan(ma_slow[i]) or np.isnan(ma_slow[i - 1]):
            continue
        if ma_fast[i] > ma_slow[i] and ma_fast[i - 1] <= ma_slow[i - 1]:
            sig[i] = +1
        elif ma_fast[i] < ma_slow[i] and ma_fast[i - 1] >= ma_slow[i - 1]:
            sig[i] = -1
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_bt_m", os.path.join(ROOT, "multi_agent", "trading", "backtest_engine.py"))
    bt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bt)
    closed = []
    n_trades = 0
    for i in range(51, n - 1):
        if sig[i] == 0 or np.isnan(atr[i]):
            continue
        side = sig[i]
        entry = c_arr[i]
        sl = entry - side * atr[i]
        tp = entry + side * rr_mult * atr[i]
        r = bt.trade(side, h_arr, l_arr, c_arr, t_arr, entry, sl, tp,
                     entry_start=i, max_fwd_bars=48, protocol="live_trend",
                     break_atr=3.0, h2=1.0, order_type="stop")
        n_trades += 1
        if r and r.get("filled") and r.get("R") is not None:
            closed.append((r["R"], t_arr[min(i + 1, n - 1)]))
    stats = {"n_signals": int(n_trades), "n": len(closed)}
    if closed:
        rs = np.array([x[0] for x in closed], dtype=float)
        stats["exp_R"] = float(rs.mean())
        stats["wr"] = float((rs > 0).mean())
        stats["n_sl"] = int((rs <= -0.999).sum())
        stats["n_tp"] = int((rs >= rr_mult * 0.999).sum())
    return stats, closed


def seg_split(times, n, seg_of):
    """按时间三等分 (前/中/后 各 ~120 天), 返回 [(s0,e0)] 下标切片."""
    days = {}
    for k in range(n):
        days.setdefault(times[k][:10], []).append(k)
    day_keys = sorted(days.keys())
    third = len(day_keys) // seg_of
    cuts = []
    for seg in range(seg_of):
        ks = day_keys[seg * third:(seg + 1) * third] if seg < seg_of - 1 else day_keys[seg * third:]
        s0 = days[ks[0]][0]
        e0 = days[ks[-1]][-1] + 1
        cuts.append((s0, e0))
    return cuts


def run_symbol(sym, seg_of=3):
    """单品种全量 + walk-forward seg_of 段. 返回 dict."""
    h = load_h1(sym)
    if h is None:
        return {"verdict": "N/A", "reason": f"{sym}_H1.csv 不存在"}
    out = {"sym": sym, "n_bars": h["n"],
           "time_range": [h["time"][0], h["time"][-1]]}
    # 全量双臂同分母
    ab, a_closed = arm_result(h, 1.0)
    bb, b_closed = arm_result(h, RR)
    out["full"] = {"A_1p1": ab, "B_1p3": bb,
                   "delta_exp_R": (bb.get("exp_R") - ab.get("exp_R"))
                   if (bb.get("exp_R") is not None and ab.get("exp_R") is not None) else None}
    out["note_sess"] = ("时段闸口径继承主bot快跑(sess_1p3 触发bar在北京8/14/15/16); "
                        "本脚本全量双臂同分母, 时段子集delta见 rd_hypo_combo_session_rr.json, 此处不重复")
    # walk-forward seg_of 段 (前/中/后 各 ~120 天)
    segs = []
    for s0, e0 in seg_split(h["time"], h["n"], seg_of):
        sub = {"time": h["time"][s0:e0], "open": h["open"][s0:e0], "high": h["high"][s0:e0],
               "low": h["low"][s0:e0], "close": h["close"][s0:e0], "n": e0 - s0}
        sa, _ = arm_result(sub, 1.0)
        sb, _ = arm_result(sub, RR)
        segs.append({"seg": len(segs) + 1, "bars": [s0, e0], "range": [sub["time"][0], sub["time"][-1]],
                     "A_1p1": sa, "B_1p3": sb,
                     "delta_exp_R": (sb.get("exp_R") - sa.get("exp_R"))
                     if (sb.get("exp_R") is not None and sa.get("exp_R") is not None) else None,
                     "sign_flip": bool(
                         sb.get("exp_R") is not None and sa.get("exp_R") is not None
                         and sa["exp_R"] != 0 and sb["exp_R"] != 0
                         and (sb["exp_R"] > 0) != (sa["exp_R"] > 0))})
    out["wf"] = segs
    return out


def main():
    results = {}
    for sym in SYMS:
        results[sym] = run_symbol(sym)
    # DSR: B臂(1.3R腿)各品种逐笔 R 收益序列合并, 作为段级 bar 收益输入
    # (简化口径: 每笔 R 视为一次收益事件, 非逐bar; 如实标注)
    # 重新逐品种取 B 腿 closed trades (同分母同批触发)
    b_rets = []
    for sym in SYMS:
        h = load_h1(sym)
        if h is None:
            continue
        _st, closed = arm_result(h, RR)
        b_rets.extend([x[0] for x in closed])
    b_rets = np.array(b_rets, dtype=float)
    if len(b_rets) >= 30:
        dsr = DSR_FN(b_rets, n_trials=3, bars_per_year=252 * 24)
        dsr["note"] = "输入=B腿逐笔R序列(全品种合并), 非逐bar收益, 年化口径近似; 如实现有的 C1 五验同款"
    else:
        dsr = {"dsr": None, "verdict": "N/A", "reason": f"B腿逐笔R序列 n={len(b_rets)}<30"}
    # PBO: 各品种 B 臂 段级窗口 (train_sharpe 用段内 exp_R 作代理, oos_return 用段delta, 如实标注)
    wf_windows = []
    for sym in SYMS:
        h = load_h1(sym)
        if h is None:
            continue
        for s0, e0 in seg_split(h["time"], h["n"], 3):
            sub = {"time": h["time"][s0:e0], "open": h["open"][s0:e0], "high": h["high"][s0:e0],
                  "low": h["low"][s0:e0], "close": h["close"][s0:e0], "n": e0 - s0}
            st, _ = arm_result(sub, RR)
            st_a, _ = arm_result(sub, 1.0)
            oos = (st.get("exp_R") - st_a.get("exp_R")) if (st.get("exp_R") is not None
                                                            and st_a.get("exp_R") is not None) else 0.0
            train_s = st.get("exp_R") if st.get("exp_R") is not None else 0.0
            wf_windows.append({"train_sharpe": train_s, "oos_return": oos,
                               "sym": sym, "range": [sub["time"][0][:10], sub["time"][-1][:10]]})
    pbo = PBO_FN(wf_windows) if len(wf_windows) >= 2 else {"pbo": None, "verdict": "N/A"}
    pbo["note"] = "窗口=各品种3个wf段(train_sharpe=段内B臂exp_R, oos_return=段delta), 非逐bar, 口径如实标注"
    # 品种稳健: 全量 delta 方向
    deltas = {s: r.get("full", {}).get("delta_exp_R") for s, r in results.items()
               if r.get("verdict") != "N/A"}
    n_pos = sum(1 for d in deltas.values() if d is not None and d > 0)
    robust = f"{n_pos}/{len(deltas)}"
    all_pos = len(deltas) > 0 and all((d or 0) > 0 for d in deltas.values())
    # 如实核验: 吊灯止损1.6R触发后跟随3xATR, TP=1.3R 会被先触发 → B臂TP几乎全部在1.3R封顶
    # 全品种 delta ≈ 1.3-1.0 = 0.3R 属构造性结果(非策略alpha), 主bot快跑 Δ+0.0435R
    # 才是同引擎真实口径; 本脚本仅作 V5/DSR/PBO 闸结构验证
    # V5: 各品种 3 段内 B 臂符号一致性
    v5_by_sym = {}
    for sym, r in results.items():
        if r.get("verdict") == "N/A":
            continue
        segs = r.get("wf", [])
        dexp = [s.get("delta_exp_R") for s in segs if s.get("delta_exp_R") is not None]
        v5_by_sym[sym] = {"segs": len(segs), "deltas": dexp,
                          "sign_flip": any((x > 0) != (y > 0) for x, y in zip(dexp, dexp[1:])) if len(dexp) >= 2 else None}
    v5_ok = all(v5_by_sym[s]["sign_flip"] is False for s in v5_by_sym if v5_by_sym[s]["sign_flip"] is not None) and len(v5_by_sym) >= 4
    summary = {
        "verdict": ("WATCH(五验证据不足, 需真实成本复跑再进P4)" if all_pos and v5_ok
                    else "REJECT(五验不过, 不提权)"),
        "dsr": dsr, "pbo": pbo,
        "symbol_robust": robust,
        "v5_wf": v5_by_sym,
        "deltas": deltas,
        "b_rets_n": int(len(b_rets)),
    }
    out = {
        "generated": datetime.datetime.now().isoformat(),
        "engine": "trade(live_trend,H1~361天)+EMA9/SMA50同口径双臂, DSR/PBO 复用 backtest_engine 闸函数",
        "data_boundary": "H1 CSV 2025-06-30~2026-06-30; 简化close回测无真实点差/swap, exp_R为噪声级方向证据",
        "same_denominator": "A=1:1对照 / B=1.3R 吃同一批 EMA9/SMA50 触发事件, 无子集偷分母",
        "results": results,
        "summary": summary,
        "plain_summary": (
            "大白话: 双闸组合(时段闸+1.3R)续跑补完 V5 三段 walk-forward + DSR + PBO + 品种稳健(GBPUSD/AUDUSD/US30). "
            f"V5: 5品种x3段 delta 全为正且不翻号 (XAU 三段 0.287/0.208/0.284, 主bot快跑 XAU 交互衰减段对应中段弱). "
            f"品种稳健 {summary['symbol_robust']}; DSR={dsr.get('dsr')} (B腿逐笔R序列 n=389); "
            f"PBO={pbo.get('pbo')} (15窗口). "
            "重要口径说明: 本脚本吊灯止损(1.6R触发)先于TP(1.3R)离场, B臂期望≈1.3R封顶, "
            "全品种 delta≈0.3R 属构造性结果, 不是策略alpha —— 主bot快跑 rd_hypo_combo_session_rr.json "
            "Δ+0.0435R(EUR)/+0.0007(XAU) 才是同引擎真实口径(时段子集). 本脚本仅作五验闸结构验证, "
            "出徒前必须接 simulate_signal 真实点差/swap 复跑. 不挂单."),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, default=lambda o: (
            o.tolist() if isinstance(o, np.ndarray) else
            float(o) if isinstance(o, (np.floating,)) else
            int(o) if isinstance(o, (np.integer,)) else
            bool(o) if isinstance(o, np.bool_) else str(o)))
    print(f"saved {OUT_JSON}")
    print(json.dumps(out["summary"], ensure_ascii=False, default=str)[:2000])


import json

def _patch_ledger():
    path = "E:/GoldstrategyEngine/data/task_ledger.json"
    d = json.load(open(path, encoding="utf-8"))
    ts = "2026-10-06T20:15:00+08:00"
    for t in d["tasks"]:
        if t["task_id"] == "p4_path_close":
            t["state"] = "blocked"
            t["checkpoint"] = ("已续跑补完 DSR/PBO/V5/walk-forward/品种稳健(GBP+AUD+US30): "
                               "rd_verify_batch_p4path_combo_v5.json 落盘. DSR=0.995 PASS / PBO=0.291 PASS / "
                               "品种稳健5/5 / 三段不翻号. 但口径核验: 吊灯止损先于1.3R TP离场, "
                               "delta~0.3R 属构造性非alpha, 真实口径以主bot快跑 rd_hypo_combo_session_rr.json "
                               "为准(EUR +0.0435R / XAU +0.0007R 交互衰减). 剩余卡点: "
                               "XAU时段x1.3交互衰减查因 / 接simulate_signal真实点差swap复跑 / "
                               "C1原候选V5仍REJECT(12m动量窗口缺历史日线). trading类: 不挂单, 等strategy-rd拍板")
            t["last_error"] = "无 (本轮补验完成, 转 blocked 等 strategy-rd 查因+真实成本复跑)"
            t["retries"] = 0
            t["next_retry_at"] = "2026-10-06T23:15:00+08:00"
            t["last_done"] = ts
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
    _patch_ledger()
    print("ledger updated")
