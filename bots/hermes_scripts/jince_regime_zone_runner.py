# -*- coding: utf-8 -*-
r"""P2-2/P2-3 区计算 + regime 门 (确定性 0LLM, 15min cron runner)
① HVN/LVN 区: 读 l2proxy_ticks.jsonl 近 N 小时 tick, 分品种 20 桶直方图 -> HVN=最厚桶带, LVN=最薄桶带
   用途: 结构锚定法增位——TP 优先落 LVN(薄区走得快), SL 避开 HVN 内侧(厚区=止损坟场)。
② regime 门(ML regime 的确定性实现, 接口可热插真ML): M15 ADX + ATR 百分位(对5日滚动)
   HIGHVOL(ATR>=1.5x中位) > TREND(ADX>=40, 方向=D1 EMA50偏) > LOWVOL(ATR<=0.5x) > RANGE(ADX<20)
输出: data/l2proxy_zones.json + data/regime_state.json (带 ts, 引擎读取侧自带新鲜度闸, 过期=中性+红)。
自检: --selftest 用合成 tick 断言 HVN/LVN 单调正确。
"""
import json
import os
import time

DATA = r"E:\GoldstrategyEngine\data"
TICKS = os.path.join(DATA, "l2proxy_ticks.jsonl")
ZO = os.path.join(DATA, "l2proxy_zones.json")
RS = os.path.join(DATA, "regime_state.json")
WATCH = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "XAUUSD", "EURUSD", "GBPUSD", "US30"]
BUCKETS = 20
HOURS = 6


def zones_from_ticks(rows, sym, buckets=BUCKETS):
    """rows: [{sym, bid, v}...] 同品种; 返回 {lo, hi, hv: [lo,hi], lv: [lo,hi], hist:[counts]}"""
    xs = [(r["bid"], r.get("v", 0)) for r in rows if r.get("sym") == sym and r.get("bid")]
    if len(xs) < 20:
        return None
    lo, hi = min(x[0] for x in xs), max(x[0] for x in xs)
    if hi <= lo:
        return None
    w = (hi - lo) / buckets
    hist = [0] * buckets
    for p, v in xs:
        i = min(int((p - lo) / w), buckets - 1)
        hist[i] += int(v) if v else 1
    hv_i = max(range(buckets), key=lambda i: hist[i])
    lv_i = min(range(buckets), key=lambda i: hist[i])
    return {"lo": round(lo, 8), "hi": round(hi, 8),
            "hv": [round(lo + hv_i * w, 8), round(lo + (hv_i + 1) * w, 8)],
            "lv": [round(lo + lv_i * w, 8), round(lo + (lv_i + 1) * w, 8)],
            "hist": hist}


def load_tick_rows(hours=HOURS):
    import datetime
    cutoff = (datetime.datetime.now() - datetime.timedelta(hours=hours)).strftime("%F %T")
    rows = []
    if not os.path.exists(TICKS):
        return rows, False
    for line in open(TICKS, encoding="utf-8", errors="replace"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("ts", "") >= cutoff:
            rows.append(r)
    return rows, len(rows) > 0


def regime_of(symbol):
    """确定性 regime 状态机(ML 接口位: 后续可换 sklearn 实现, 返回结构不变)。
    [11-14 修] 主 cron 解释器(Hermes python)无 MetaTrader5 模块 -> regime全UNKNOWN('No module named' 23:30拍实证);
    改 ATE 专用解释器 spawn data/_regime_calc.py 算, 结果 merge 回原结构; ATE 不可用回退本地 import(旧行为)。"""
    import subprocess
    _ATE = "C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe"
    _CALC = os.path.join(DATA, "_regime_calc.py")
    if os.path.exists(_ATE) and os.path.exists(_CALC):
        try:
            _env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE")}
            _r = subprocess.run([_ATE, _CALC, symbol], capture_output=True, text=True, timeout=90, env=_env,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            _j = json.loads((_r.stdout or "").strip().splitlines()[-1])
            _j["ts"] = time.strftime("%F %T")
            return _j
        except Exception:
            pass  # ATE 不可用 -> 落回本地 import 旧逻辑(ATE 环境下才有 MT5 模块)
    """确定性 regime 状态机(ML 接口位: 后续可换 sklearn 实现, 返回结构不变)。"""
    import statistics
    try:
        import MetaTrader5 as mt5
        assert mt5.initialize()
        time.sleep(1)
        m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 120)
        d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 80)
        if m15 is None or len(m15) < 60:
            mt5.shutdown()
            return None
        c = [float(x["close"]) for x in m15]
        h = [float(x["high"]) for x in m15]
        l = [float(x["low"]) for x in m15]
        atrs = []
        for i in range(1, len(m15)):
            tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
            atrs.append(tr)
        atr = sum(atrs[-14:]) / 14
        # ADX14
        plus_d, minus_d = [], []
        for i in range(1, len(m15)):
            plus_d.append(max(h[i] - h[i - 1], 0) if (h[i] - h[i - 1]) > (l[i - 1] - l[i]) else 0)
            minus_d.append((l[i - 1] - l[i]) if (l[i - 1] - l[i]) > (h[i] - h[i - 1]) else 0)
        tr14 = atrs[-14:]
        sd_p = sum(plus_d[-14:]) / 14 / atr * 100 if atr else 0
        sd_m = sum(minus_d[-14:]) / 14 / atr * 100 if atr else 0
        adx = abs(sd_p - sd_m) / (sd_p + sd_m) * 100 if (sd_p + sd_m) else 0
        # ATR 百分位: 对 5 日滚动 M15 ATR 序列
        atrs_hist = []
        for j in range(14, len(c) - 13):
            atrs_hist.append(sum(atrs[j - 14:j]) / 14.0)
        atr_med = statistics.median(atrs_hist[-5:]) if atrs_hist else atr
        bias = None
        if d1 is not None and len(d1) >= 51:
            dc = [float(x["close"]) for x in d1]
            e = sum(dc[:50]) / 50
            for x in dc[49:]:
                e = x * 2 / 51 + e * 49 / 51
            bias = "多" if dc[-1] > e else "空"
        mt5.shutdown()
        if atr_med and atr >= 1.5 * atr_med:
            reg = "HIGHVOL"
        elif adx >= 40:
            reg = "TREND"
        elif atr_med and atr <= 0.5 * atr_med:
            reg = "LOWVOL"
        else:
            reg = "RANGE"
        return {"regime": reg, "adx15": round(adx, 1), "atr15": round(atr, 8),
                "atr_pct": round(atr / atr_med, 2) if atr_med else 1.0, "d1_bias": bias,
                "ts": time.strftime("%F %T")}
    except Exception as ex:
        return {"regime": "UNKNOWN", "err": str(ex)[:120], "ts": time.strftime("%F %T")}


def ensure_collector():
    """采集器自愈: pid 死或 tick 最后行 >5min = 脱离式拉起新采集器, 返回状态串。"""
    import subprocess
    import datetime
    pid_ok = False
    try:
        pid = int(open(PIDF).read().strip())
        ps = ("powershell", "-NoProfile", "-Command",
              "if (Get-Process -Id %d -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" % pid)
        subprocess.run(ps, check=True, capture_output=True)
        pid_ok = True
    except Exception:
        pid_ok = False
    last_ts = ""
    try:
        with open(TICKS, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    last_ts = json.loads(line).get("ts", "")
                except Exception:
                    pass
        # [11-14 修] "%F %T"是shell变量非Python strptime指令(潜雷: last_ts首次非空即爆ValueError, 23:00拍exit1根因); 改全指令+畸形ts防呆
        try:
            age = (datetime.datetime.now() - datetime.datetime.strptime(last_ts, "%Y-%m-%d %H:%M:%S")).total_seconds() if last_ts else 9999
            if age > 300:
                pid_ok = False
        except ValueError:
            pid_ok = False  # 畸形ts=fail-safe判死, 下拍自愈不崩
    except FileNotFoundError:
        pid_ok = False
    if pid_ok:
        return "collector alive"
    coll = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jince_l2proxy_collector.py")
    p2 = subprocess.Popen(["C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe", coll],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          start_new_session=True,
                          creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    return "collector 重启 pid=%d" % p2.pid


def main():
    import sys
    if "--selftest" in sys.argv:
        rows = []
        for i in range(80):
            rows.append({"sym": "T", "bid": 100 + (i % 2), "v": 300 if i % 40 < 20 else 10})
        z = zones_from_ticks(rows, "T")
        assert z is not None and len(z["hist"]) == BUCKETS
        imax = z["hist"].index(max(z["hist"]))
        hv_idx = int((z["hv"][0] - z["lo"]) / (z["hi"] - z["lo"]) * BUCKETS)
        assert max(z["hist"]) > 0 and imax == hv_idx and 0 <= imax < BUCKETS
        print("zones selftest: 合成 tick -> HVN/LVN 计算 PASS (max桶=%d)" % max(z["hist"]))
        return
    cs = ensure_collector()
    rows, fresh = load_tick_rows(HOURS)
    zones = {"ts": time.strftime("%F %T"), "fresh": fresh, "n_rows": len(rows), "collector": cs}
    for s in WATCH:
        z = zones_from_ticks(rows, s)
        if z:
            zones[s] = z
    json.dump(zones, open(ZO, "w", encoding="utf-8"), ensure_ascii=False)
    reg = {"ts": time.strftime("%F %T")}
    for s in WATCH:
        r = regime_of(s)
        if r:
            reg[s] = r
    json.dump(reg, open(RS, "w", encoding="utf-8"), ensure_ascii=False)
    red = []
    if not fresh:
        red.append("tick流空(采集器%s)" % cs)
    dicts = [v for v in reg.values() if isinstance(v, dict)]
    if dicts and all(v.get("regime") == "UNKNOWN" for v in dicts):
        red.append("regime全UNKNOWN(ATE异常?)")
    if red:
        print("⚠️ [L2代理/regime] %s" % "; ".join(red))


if __name__ == "__main__":
    main()
