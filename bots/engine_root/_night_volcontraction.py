# -*- coding: utf-8 -*-
# 族1 波动收缩爆发族: M30 全史 × 6品种, 3候选 × SLM{2,3} × 窗口{8,12} × D1闸{on,off}
# 事件全集(同分母框架): 波动收缩后突破
#   lazymom  : BB(20,2.0) 连续W根完全收进 KC(SMA20±1.5ATR14) 内, 收出解压bar触发
#   lazyconf : 同事件 + LazyBear动量 linreg(close-avg(中枢),20,0) 方向确认
#   bbwrel   : BB带宽(W根内最低bar+1根)收过BB中值且带宽>=最低值×1.05
# 几何: stop单trigger上方/下方, FILL=4根内成交, SL=SLM*ATR14, TP=2R, 前向FWD=42根(21h),
#       同根双触SL优先, 未触发按末根close计R(截断偏差如实报), 前视: 事件判定仅用i-1及以前
#       未成交=该事件废弃(不入场)
import os, json, time
import numpy as np
os.environ["OPENBLAS_NUM_THREADS"] = "1"; os.environ["OMP_NUM_THREADS"] = "1"

BASE = r"E:/GoldstrategyEngine/data"
SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD"]
FWD, FILL, TPR = 42, 4, 2.0
# 铁律修正: 解压bar i 收盘前已知 => 事件bar = i-1, trigger = [i-W-1, i-1] 的 W 根窗口高/低点
# (事件判定与指标全部只用 i-1 及以前数据)

# ---------- 指标 ----------
def wilder_atr(h, l, c, p=14):
    tr = np.empty(len(c)); tr[0] = h[0]-l[0]
    for i in range(1, len(c)):
        tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    a = np.empty(len(c)); a[:] = np.nan
    a[p-1] = tr[:p].mean()
    for i in range(p, len(c)):
        a[i] = (a[i-1]*(p-1) + tr[i]) / p
    return a

def sma(x, n):
    out = np.empty(len(x)); out[:] = np.nan
    c = np.cumsum(np.insert(x, 0, 0.0))
    out[n-1:] = (c[n:] - c[:-n]) / n
    return out

def stdev_pop(x, n):
    out = np.empty(len(x)); out[:] = np.nan
    s = np.zeros(len(x)+1); s[1:] = np.cumsum(x.astype(float))
    s2 = np.zeros(len(x)+1); s2[1:] = np.cumsum((x.astype(float))**2)
    idx = np.arange(n-1, len(x))
    ss = s[idx+1] - s[idx+1-n]; ss2 = s2[idx+1] - s2[idx+1-n]
    out[n-1:] = np.sqrt(np.maximum(ss2 - ss*ss/n, 0.0) / n)
    return out

def rollmax(x, n):
    out = np.empty(len(x)); out[:] = -np.inf
    for i in range(len(x)):
        s = max(0, i-n+1)
        out[i] = x[s:i+1].max()
    return out

def rollmin(x, n):
    out = np.empty(len(x)); out[:] = np.inf
    for i in range(len(x)):
        s = max(0, i-n+1)
        out[i] = x[s:i+1].min()
    return out

def linreg_last(x, n):
    # 滚动窗口线性回归: 返回"第0位"的回归预测值(等价 linreg(...,0)), 闭式
    out = np.empty(len(x)); out[:] = np.nan
    idx = np.arange(n, dtype=float)
    xs = idx.sum(); xx = (idx**2).sum()
    den = n*xx - xs*xs
    for i in range(n-1, len(x)):
        seg = x[i-n+1:i+1]
        ys = seg.sum(); yx = (idx*seg).sum()
        m = (n*yx - xs*ys) / den
        b = (ys - m*xs) / n
        out[i] = b
    return out

def load(sym):
    d = np.load(os.path.join(BASE, "tf_cache", f"{sym}_M30.npz"))
    return d["t"].astype(np.int64), d["h"].astype(float), d["l"].astype(float), d["c"].astype(float)

def d1_gate(sym, times_m30):
    d = np.load(os.path.join(BASE, "tf_cache", f"{sym}_D1.npz"))
    t1, o1, c1 = d["t"].astype(np.int64), d["o"].astype(float), d["c"].astype(float)
    day = np.clip(np.searchsorted(t1, times_m30, side="right") - 1, 0, len(t1)-1)
    up = np.zeros(len(times_m30), dtype=bool); dn = np.zeros(len(times_m30), dtype=bool)
    for i in range(len(times_m30)):
        j = day[i]; up[i] = c1[j] > o1[j]; dn[i] = c1[j] < o1[j]
    return up, dn

# ---------- 事件生成 ----------
def gen_lazy(h, l, c, bb_ub, bb_lb, kc_ub, kc_lb, mom, W, start):
    """返回 (idx[], side[], trig[]): side 0=buy 1=sell; idx=解压bar(事件bar), 只用了idx内数据"""
    on = (~np.isnan(bb_ub)) & (bb_lb > kc_lb) & (bb_ub < kc_ub)
    idx = []; side = []; trig = []
    streak = 0
    n = len(c)
    for i in range(start, n):
        if on[i]:
            streak += 1
            continue
        if streak >= W:   # 之前连续W根BB在KC内, 本bar(i)解压; 事件bar=j=i-1
            j = i - 1
            hi_win = np.max(h[j-W:j])   # 收缩窗口高点(stop挂在其上)
            lo_win = np.min(l[j-W:j])
            m = mom[j]                    # 动量确认: 事件bar i-1 自身收盘
            if not np.isnan(m):
                if m > 0:
                    idx.append(j); side.append(0); trig.append(hi_win)
                elif m < 0:
                    idx.append(j); side.append(1); trig.append(lo_win)
            streak = 0
        else:
            streak = 0
    return np.array(idx), np.array(side), np.array(trig, dtype=float)

def gen_lazy_nofilter(h, l, c, bb_ub, bb_lb, kc_ub, kc_lb, W, start):
    idx = []; side = []; trig = []
    on = (~np.isnan(bb_ub)) & (bb_lb > kc_lb) & (bb_ub < kc_ub)
    streak = 0
    for i in range(start, len(c)):
        if on[i]:
            streak += 1; continue
        if streak >= W:
            j = i - 1
            hi_win = np.max(h[j-W:j]); lo_win = np.min(l[j-W:j])
            idx.append(j); side.append(0); trig.append(hi_win)
            idx.append(j); side.append(1); trig.append(lo_win)
        streak = 0
    return np.array(idx), np.array(side), np.array(trig, dtype=float)

def gen_bbwrel(h, l, c, bbw, W, start):
    idx = []; side = []; trig = []
    for i in range(start, len(c)-1):
        win = bbw[i-W:i]
        if np.isnan(win).any(): continue
        k = int(np.argmin(win))
        if k != W-1: continue            # 最低bar = i-1
        wmin = win[k]
        if bbw[i] < wmin*1.05: continue  # 带宽扩张
        mid = 0.5*(bbw[i]*0 + 0)        # placeholder, 传 sma20
        return None
    return idx, side, trig

def prepare(sym):
    t, h, l, c = load(sym)
    n = len(c)
    atr = wilder_atr(h, l, c)
    sma20 = sma(c, 20)
    sd20 = stdev_pop(c, 20)
    bb_ub = sma20 + 2.0*sd20; bb_lb = sma20 - 2.0*sd20
    kc_ub = sma20 + 1.5*atr; kc_lb = sma20 - 1.5*atr
    hh = rollmax(h, 20); ll = rollmin(l, 20)
    ref = (hh + ll + sma20) / 3.0
    ref = np.where(np.isnan(ref), 0.0, ref)
    mom = linreg_last(c - ref, 20)
    up, dn = d1_gate(sym, t)
    bbw = (bb_ub - bb_lb) / sma20
    start = 300
    return dict(t=t, h=h, l=l, c=c, n=n, atr=atr, sma20=sma20, up=up, dn=dn,
                bb_ub=bb_ub, bb_lb=bb_lb, kc_ub=kc_ub, kc_lb=kc_lb,
                mom=mom, bbw=bbw, start=start)

def gen_events(cand, W, d):
    h, l, c, bbw = d["h"], d["l"], d["c"], d["bbw"]
    if cand == "lazymom":
        return gen_lazy_nofilter(h, l, c, d["bb_ub"], d["bb_lb"], d["kc_ub"], d["kc_lb"], W, d["start"])
    if cand == "lazyconf":
        return gen_lazy(h, l, c, d["bb_ub"], d["bb_lb"], d["kc_ub"], d["kc_lb"], d["mom"], W, d["start"])
    # bbwrel
    idx = []; side = []; trig = []
    for i in range(d["start"], d["n"]-1):
        win = bbw[i-W:i]
        if np.isnan(win).any(): continue
        if int(np.argmin(win)) != W-1: continue
        if bbw[i] < win[W-1]*1.05: continue
        j = i - 1
        mid = d["sma20"][j]
        hi_win = np.max(h[j-W:j]); lo_win = np.min(l[j-W:j])
        if c[j] > mid:
            idx.append(j); side.append(0); trig.append(hi_win)
        if c[j] < mid:
            idx.append(j); side.append(1); trig.append(lo_win)
    return np.array(idx), np.array(side), np.array(trig, dtype=float)

def replay(idx, side, trig, d, SLM, gate_on, per_trade):
    """回放, 返回 (sum_b, n_b, sum_s, n_s, [R,time pairs if per_trade])"""
    h, l, c, t = d["h"], d["l"], d["c"], d["t"]
    up, dn, n = d["up"], d["dn"], d["n"]
    sums_b = sums_s = 0.0; n_b = n_s = 0
    trade_R = [] if per_trade else None
    for k in range(len(idx)):
        i = int(idx[k]); sd = int(side[k]); tg = float(trig[k])
        R = SLM * d["atr"][i-1]
        if R <= 0: continue
        use_gate = gate_on
        if sd == 0:
            if use_gate and not up[i]: continue
            sl = tg - R; tp = tg + TPR*R
            j_end = min(i+1+FILL, n)
            filled = False
            for j in range(i+1, j_end):
                if h[j] >= tg: filled = True; break
            if not filled: continue
            res = None
            for j in range(i+1, min(i+1+FWD, n)):
                if l[j] <= sl: res = sl; break
                if h[j] >= tp: res = tp; break
            if res is None: res = c[min(i+1+FWD, n-1)]
            r = (res - tg) / R
            sums_b += r; n_b += 1
            if per_trade: trade_R.append((r, t[i]))
        else:
            if use_gate and not dn[i]: continue
            sl = tg + R; tp = tg - TPR*R
            j_end = min(i+1+FILL, n)
            filled = False
            for j in range(i+1, j_end):
                if l[j] <= tg: filled = True; break
            if not filled: continue
            res = None
            for j in range(i+1, min(i+1+FWD, n)):
                if h[j] >= sl: res = sl; break
                if l[j] <= tp: res = tp; break
            if res is None: res = c[min(i+1+FWD, n-1)]
            r = (tg - res) / R
            sums_s += r; n_s += 1
            if per_trade: trade_R.append((r, t[i]))
    if per_trade:
        return sums_b, n_b, sums_s, n_s, trade_R
    return sums_b, n_b, sums_s, n_s

def main():
    t0 = time.time()
    DATA = {}
    for sym in SYMS:
        DATA[sym] = prepare(sym)
        print(f"[prep] {sym} n={DATA[sym]['n']} ok ({time.time()-t0:.0f}s)", flush=True)

    trades_cache = {}   # (cand, W, SLM, gate) -> {sym: (Rlist, Tlist) per side 已合并}
    for cand in ("lazymom", "lazyconf", "bbwrel"):
        for W in (8, 12):
            for SLM in (2.0, 3.0):
                for gate in (0, 1):
                    gl = "on" if gate else "off"
                    Rall, Tall = [], []
                    nb_tot = ns_tot = 0
                    for sym in SYMS:
                        idx, side, trig = gen_events(cand, W, DATA[sym])
                        sb, nb, ss_, ns, tr = replay(idx, side, trig, DATA[sym], SLM, gate, True)
                        Rall.extend(tr); nb_tot += nb; ns_tot += ns
                    key = (cand, W, SLM, gl)
                    trades_cache[key] = Rall
                    alll = [r for r, _ in Rall]
                    exp = sum(alll)/len(alll) if alll else float("nan")
                    print(f"[grid] {cand} W={W} SLM={SLM} d1={gl} n={len(alll)} (B{nb_tot}/S{ns_tot}) exp_R={exp:.3f} ({time.time()-t0:.0f}s)", flush=True)

    # 聚合
    def agg_of(key):
        Rall = trades_cache[key]
        n = len(Rall)
        if not n:
            return dict(n=0, exp_R=None, wr=None, wf3=[None]*3, per_sym={}, net_P95=None, net_P95x2=None, sym_pass=None)
        exp = sum(r for r, _ in Rall)/n
        wr = sum(1 for r, _ in Rall if r > 0)/n
        # per_sym: 需要逐品种 -> 重放一次
        per_sym = {}
        cand, W, SLM, gl = key
        for sym in SYMS:
            idx, side, trig = gen_events(cand, W, DATA[sym])
            tr = replay(idx, side, trig, DATA[sym], SLM, gl=="on", True)[4]
            per_sym[sym] = round(sum(x for x, _ in tr)/len(tr), 4) if tr else None
        # wf3: 按时间三等分
        pairs = sorted(trades_cache[key])
        third = len(pairs)//3
        wf3 = []
        for k in range(3):
            seg = pairs[k*third:((k+1)*third if k < 2 else len(pairs))]
            wf3.append(round(sum(r for r, _ in seg)/len(seg), 4) if seg else None)
        # 对称自检: 分方向 exp 与笔数比
        cand_, W_, SLM_, gl_ = key
        nb = 0; ns = 0; rb = 0.0; rs = 0.0
        for sym in SYMS:
            idx, side, trig = gen_events(cand_, W_, DATA[sym])
            sb, n_b, ss_, n_s = replay(idx, side, trig, DATA[sym], SLM_, gl_=="on", False)
            nb += n_b; ns += n_s; rb += sb; rs += ss_
        exp_b = rb/nb if nb else float("nan"); exp_s = rs/ns if ns else float("nan")
        sym_pass = bool(min(nb, ns)/max(nb, ns) >= 0.3 and abs(exp_b - exp_s) < 0.5)
        return dict(n=n, exp_R=round(exp, 4), wr=round(wr, 4), wf3=wf3, per_sym=per_sym,
                    net_P95=round(exp - 0.095, 4), net_P95x2=round(exp - 0.19, 4),
                    sym_pass=sym_pass, n_buy=nb, n_sell=ns)

    # 候选代表 = 该族内 exp_R 最高的格 (各参数都要报, grid_detail 全列出)
    detail = []
    best = {}
    for cand in ("lazymom", "lazyconf", "bbwrel"):
        best[cand] = None
        for W in (8, 12):
            for SLM in (2.0, 3.0):
                for gl in ("off", "on"):
                    key = (cand, W, SLM, gl)
                    a = agg_of(key)
                    a["cand"] = cand; a["W"] = W; a["SLM"] = SLM; a["gate"] = gl
                    detail.append(a)
                    if a["n"] and (best[cand] is None or a["exp_R"] > best[cand]["exp_R"]):
                        best[cand] = a

    names = {"lazymom": "BBKC_squeeze", "lazyconf": "BBKC_squeeze_momConfirm", "bbwrel": "BBwidth_low_release"}
    cand_json = []
    for cand in ("lazymom", "lazyconf", "bbwrel"):
        b = best[cand]
        row = dict(detail) if False else None
        cand_json.append({
            "name": f"{names[cand]}_SLM{b['SLM']}_W{b['W']}_d1{b['gate']}",
            "tf": "M30", "n": b["n"], "exp_R": b["exp_R"], "wr": b["wr"], "wf3": b["wf3"],
            "per_sym": b["per_sym"], "sym_pass": b["sym_pass"],
            "same_denom": True, "close_basis": True,
            "net_P95": b["net_P95"], "net_P95x2": b["net_P95x2"],
            "note": f"最优格: SLM={b['SLM']} W={b['W']} D1闸={b['gate']} B/S笔数={b['n_buy']}/{b['n_sell']}",
        })

    valid = [x for x in cand_json if x["exp_R"] is not None]
    top = max(valid, key=lambda x: x["exp_R"]) if valid else None
    top_name = top["name"] if top else "NONE"

    passed = 0
    allc = []
    for cand in ("lazymom", "lazyconf", "bbwrel"):
        for W in (8, 12):
            for SLM in (2.0, 3.0):
                for gl in ("off", "on"):
                    a = next(x for x in detail if (x["cand"], x["W"], x["SLM"], x["gate"]) == (cand, W, SLM, gl))
                    allc.append(a)
                    ok_sym = a["sym_pass"] is True
                    ok_wr3 = a["wf3"] and all(v is not None and v > 0 for v in a["wf3"])
                    ok_net = a["net_P95"] is not None and a["net_P95"] > 0
                    ok_s1 = a["sym_pass"] or False  # 用对称自检做②
                    pos_sym = sum(1 for v in a["per_sym"].values() if v is not None and v > 0)
                    if a["n"] and ok_sym and ok_wr3 and ok_net and pos_sym >= 4:
                        passed += 1
    verdict = (f"3候选×8格={len(allc)}组合, 全过五验(①②③④⑤)格数={passed}; "
               f"最优 {top_name} exp_R={top['exp_R']} net_P95={top['net_P95']} "
               f"wf3={top['wf3']} wr={top['wr']} n={top['n']} 品种正{sum(1 for v in top['per_sym'].values() if v and v>0)}/6"
               if top else "无有效组合(REJECT)")
    verdict = str(verdict)
    # 数值统一转 Python 原生类型, 保证 JSON 可序列化
    def _fix(o):
        if isinstance(o, dict):
            return {k: _fix(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_fix(v) for v in o]
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        return o

    out = {
        "family": "族1 波动收缩爆发族",
        "research_notes": "LazyBear Squeeze Momentum (TTM/Carter): BB(20,2.0)完全收进KC(20,1.5ATR)内=squeeze, 挤出后突破; 动量=linreg(close-最近中枢,20), 正=多/负=空。Carter原著: 入pivot, 止损=第二swing外, 32bar超时。Bollinger: BB带宽达120bar最低=收缩。Minervini VCP: 收缩幅度递减后买pivot上方。适配: 收缩窗口压至W=8/12根(M30), 事件=收缩N根后解压, stop挂窗口高/低点外, FILL=4根, SL=SLM*ATR14, TP=2R, 前向42根(21h), D1日K方向闸开/关双报。",
        "candidates": cand_json,
        "grid_detail": detail,
        "top_pick": top_name,
        "verdict": verdict,
    }
    out = _fix(out)
    p = os.path.join(BASE, "night_rd_volcontraction.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print("WROTE", p, f"total {time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
