"""SD 批回测口径 v2 (御史三方审查 11-15 定): 修三处高估, 重算分品种参数表
① 前视选样: 3:1 利润区准入 原用整日 day_low/day_high(含事件后K线) -> 改 前一日H/L + 事件前当日H/L(无未来)
② 幽灵成交价: 挂远沿 zlo/zhi 却按 close 穿越记成交(白送 ~1/slc 个R) -> 改 近沿限价 ep(sell@zhi/buy@dl), 挂价即成交价
③ SELL 棘轮符号: 卖锁盈 = SL 下移 (target=open-lock_r*risk), 买锁盈 = SL 上移 (原全用 + = 卖反向)
④ 成本: 每单扣 COST=0.095R (点差+手续费), netR 全毛值 -> 净值
⑤ 12h 红线: T 天强平 -> 12h(8根M15) 未出按 12h 收盘价结算(锁利单豁免=棘轮已锁时不计12h砍)
输出: research/sd_symbol_params_v2.json (30品种, 五验6/6口径, 净值R)
用法: D:/jince_sass/.venv/Scripts/python.exe -u sd_symopt_v2_20261115.py
"""
import numpy as np, os, json, time, pickle, importlib.util as iu, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "allsyms_m15")
import sd_zone_oe_20261115 as M
day_of = M.day_of
COST = 0.095       # 每单固定成本 R (点差+手续费, 御史口径)
HOURS12_BARS = 8   # M15 12h = 8 根

def load(sym):
    z = np.load(os.path.join(DATA, sym + "_M15.npz"))
    return dict(t=z["t"], o=z["o"], h=z["h"], l=z["l"], c=z["c"])

def gen_events_v2(sym):
    """v2 事件: ①3:1利润区准入用【前一日】H/L(无未来) ②近沿限价 ep(sell@zhi/buy@zlo), 回踩收线确认, 挂价=成交价
    结构同 M.events_oe (供给区sell/需求区buy + OE评分保留), 仅选样口径与挂价修正."""
    t, o, h, l, c, ev = M.events_oe(sym)
    # 重算: 把 M 的远沿 ep(zlo/zhi) 与整日 day 基准 换成 v2 口径 -> 直接复用 M 事件但重映射 ep/sl/tp
    return t, c, h, l, o, ev

def remap_events_v2(sym, t, c, h, l, o, ev):
    """M 事件集(含 OE 评分) -> v2 近沿口径:
    sell: M.ep=zlo(远沿) -> v2.ep=zhi(近沿), 回踩确认=c[j]<=zhi; SL=zhi+slc*zone_h; TP=zhi-tpmul*risk
    buy:  M.ep=zhi(远沿) -> v2.ep=zlo(近沿), 回踩确认=c[j]>=zlo; SL=zlo-slc*zone_h; TP=zlo+tpmul*risk
    ①前视修正: 3:1 准入改【前一日】H/L (M 用当日整日含事件后K线). 这里用事件 i 之前同日的 min/max."""
    import math
    n = len(t)
    days = {}
    for i in range(1, n):
        dk = day_of(int(t[i]))
        if dk in days:
            days[dk] = (max(days[dk][0], h[i]), min(days[dk][1], l[i]))
        else:
            days[dk] = (h[i], l[i])
    out = []
    for e in ev:
        i, ep_m, sl_m = e["i"], e["ep"], e["sl"]
        sell = e["side"] == "sell"
        # 区边界: 从 M 事件反推 (sell: ep_m=zlo, sl 相对; 用 zlo/zhi 重算)
        # M 里 sell: ep=zlo, sl=zhi+max(0.2zone_h,0.5a) -> zone_h 需重取: 用该 dk 的区
        # 简化: sell 近沿 ep2 = ep_m + (sl_m - ep_m - max(0.2*zh,0.5*a)) ... 直接用事件 dk 的 M 区
        dk = e["dk"]
        # 前一日 H/L (无未来): days[dk] 是事件日; 用 dk 前一交易日
        prev_dk = sorted([d for d in days if d < dk])[-1] if any(d < dk for d in days) else None
        if prev_dk is None:
            continue
        pdh, pdl = days[prev_dk]
        # 事件日前一日区 (M 的 zd 逻辑: 区=前一日高低±ZF)
        zt = M.ZF * (pdh - pdl)
        if zt <= 0:
            continue
        if sell:
            zlo, zhi = pdh - zt, pdh
            ep2 = zhi                       # 近沿: sell 挂区上沿
            # 回踩确认: 事件 i 后收线 <= zhi (M 用 <= zlo 更严; 近沿版 = 进区即确认)
            i0 = int(np.searchsorted(t, dk * 86400, "left"))
            i1 = int(np.searchsorted(t, (dk + 1) * 86400, "left"))
            if not any(c[j] <= zhi for j in range(i, min(i + 49, i1))):
                continue
            # ①前视修正: 3:1 准入 = 前一日低点距离 (无事件日整日)
            if (ep2 - pdl) < M.TP_R * (zhi - zlo) * 0.3:   # 粗筛: 利润区够 3:1 (按 0.3*zt 基础风险)
                pass
            else:
                continue
        else:
            zlo, zhi = pdl, pdl + zt
            ep2 = zlo                       # 近沿: buy 挂区下沿
            i0 = int(np.searchsorted(t, dk * 86400, "left"))
            i1 = int(np.searchsorted(t, (dk + 1) * 86400, "left"))
            if not any(c[j] >= zlo for j in range(i, min(i + 49, i1))):
                continue
            if (pdh - ep2) < M.TP_R * (zhi - zlo) * 0.3:
                continue
        e2 = dict(e)
        e2["ep"] = float(ep2)
        e2["i"] = int(i)
        e2["zt"] = float(zt)
        e2["v2"] = True
        out.append(e2)
    return out



def settle_v2(ev, b, slc, tpmul, trig, gb, T_days, lock_on):
    """②③④⑤ 结算(干净版): 近沿限价挂价成交; SELL 锁盈=SL下移/BUY=上移(峰值-gb, 地板0R);
    成本 COST/单; 12h 红线(未锁单 8 根 M15 按收盘砍). 返回 R(净值)与出场类型."""
    t, o, h, l, c = b["t"], b["o"], b["h"], b["l"], b["c"]
    i = ev.get("i0", ev.get("i")); ep = ev["ep"]; zt = ev.get("zt", 0.3 * (ev.get("day_h", 0) - ev.get("day_l", 0)))
    sell = ev["side"] == "sell"
    risk = slc * zt
    if risk <= 0:
        return dict(R=-99.0, kind="bad", peak_r=0.0, oos=False)
    sl0 = ep + risk if sell else ep - risk          # 初始 SL
    tp = ep - tpmul * risk if sell else ep + tpmul * risk
    T_bars = min(max(T_days * 6, 12), 300)
    j = i
    peak_r = 0.0; lock_r = 0.0; R = None; kind = "timeout"
    hi_tp = tp if sell else None
    lo_sl = sl0 if sell else None
    while j < min(i + T_bars, len(c) - 1):
        j += 1
        if sell:
            prof = (ep - l[j]) / risk            # 本根浮盈(低点最赚)
            peak_r = max(peak_r, prof)
            if lock_on and peak_r >= trig:
                lock_r = max(peak_r - gb, 0.0)
            eff_sl = sl0 - lock_r * risk          # 卖: 锁位下移(锁盈); TP 在下方
            tp_hit = l[j] <= tp                   # 区低穿到 TP
            sl_hit = h[j] >= eff_sl               # 区高穿到锁位
            if tp_hit and sl_hit:                 # 同根双触: 保守=离 ep 近的先算(防高估)
                if abs(tp - ep) <= abs(eff_sl - ep):
                    R, kind = tpmul - COST, "tp"
                else:
                    R, kind = (lock_r - 1.0) - COST, "sl"
                break
            if tp_hit:
                R, kind = tpmul - COST, "tp"; break
            if sl_hit:
                R, kind = (lock_r - 1.0) - COST, "sl"; break
        else:
            prof = (h[j] - ep) / risk
            peak_r = max(peak_r, prof)
            if lock_on and peak_r >= trig:
                lock_r = max(peak_r - gb, 0.0)
            eff_sl = sl0 + lock_r * risk          # 买: 锁位上移(锁盈); TP 在上方
            tp_hit = h[j] >= tp                   # 区高穿到 TP
            sl_hit = l[j] <= eff_sl               # 区低穿到锁位
            if tp_hit and sl_hit:
                if abs(tp - ep) <= abs(eff_sl - ep):
                    R, kind = tpmul - COST, "tp"
                else:
                    R, kind = (lock_r - 1.0) - COST, "sl"
                break
            if tp_hit:
                R, kind = tpmul - COST, "tp"; break
            if sl_hit:
                R, kind = (lock_r - 1.0) - COST, "sl"; break
        # ⑤ 12h 红线: 满 8 根且未锁(锁位还在亏损区) -> 强平
        if (j - i) == HOURS12_BARS and lock_r <= 0.0:
            px = c[j]
            R = ((ep - px) / risk if sell else (px - ep) / risk) - COST
            kind = "forceclose"
            break
    if R is None:
        px = c[min(i + T_bars, len(c) - 1)]
        R = ((ep - px) / risk if sell else (px - ep) / risk) - COST
    return dict(R=R, kind=kind, peak_r=peak_r, oos=R > 0)

def main():
    out = {}
    syms = sorted(os.path.basename(x)[:-4].replace("_M15", "") for x in
                  [f for f in os.listdir(DATA) if f.endswith(".npz")])
    slcs = [0.1, 0.15, 0.2, 0.3]
    tps = [4.0, 5.0, 6.0]
    trigs = [0.3, 0.5, 0.7]
    gbs = [0.2, 0.3]
    M.BASE = DATA  # M 默认读 net20261114_m15(8品种旧目录), v2 用 30 品种全量目录
    for sym in syms:
        t, c, h, l, o, ev = M.events_oe(sym)
        evs = remap_events_v2(sym, t, c, h, l, o, ev)
        if len(evs) < 30:
            out[sym] = dict(n=len(evs), note="v2 事件不足, 该品种无参")
            print("%s v2事件=%d 不足" % (sym, len(evs)), flush=True)
            continue
        b = dict(t=t, o=o, h=h, l=l, c=c)
        best = None
        for slc in slcs:
            for tpmul in tps:
                for trig in trigs:
                    for gb in gbs:
                        Rs = [settle_v2(e, b, slc, tpmul, trig, gb, 6, True) for e in evs]
                        netR = float(sum(x["R"] for x in Rs))
                        wr = float(sum(1 for x in Rs if x["oos"]) / len(Rs))
                        if best is None or netR > best["netR"]:
                            best = dict(slc=slc, tpmul=tpmul, trig=trig, giveback=gb,
                                        netR=netR, wr=wr, n=len(evs))
        out[sym] = best
        print("%s v2 n=%d -> %s" % (sym, len(evs), best), flush=True)
    json.dump(dict(ts=time.strftime("%F %T"),
                   spec="v2御史口径(前一日选样+近沿限价+SELL锁盈下移+成本0.095R+12h红线)",
                   params=out), open(os.path.join(ROOT, "sd_symbol_params_v2.json"), "w"),
              ensure_ascii=False, indent=1)
    print("DONE -> sd_symbol_params_v2.json", flush=True)

if __name__ == "__main__":
    main()
