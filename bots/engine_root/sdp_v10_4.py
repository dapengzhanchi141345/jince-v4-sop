"""
v10.4 — 合体版: v10.1(黄金专精) + v10.2(渐进止盈+订单流)
优化:
  ✅ D1 EMA9/21 方向过滤 + 结构止损(取自 v10.1)
  ✅ 渐进止盈 0.5R→1R→2R (取自 v10.2)
  ✅ 订单流买卖压力过滤 (取自 v10.2)
  ✅ 黄金时段限制 15:00-00:00 (取自 v10.1)
  ✅ 新闻情感过滤 (取自 v10.1)
  ✅ 均值回归策略 外汇 (取自 v10.1)
  ✅ 5连败冷却 24h (取自 v10.2)
  ✅ 记忆系统升级 regime+zone+adx 多维匹配 (取自 v10.2)

@status: PRODUCTION — v10.4 合体版, 取代 v10.1
"""
import sys, os, time, json, warnings
import numpy as np, pandas as pd
from datetime import datetime
warnings.filterwarnings('ignore')
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

# ═══════ 审度司 v10.4 ═══════
MAX_LOT = 0.01
MAX_TRADES = 8
MAX_LOSS = 5.0
COOLDOWN_2L = 1800      # 2连败 → 30分钟
COOLDOWN_3L = 14400     # 3连败 → 4小时
COOLDOWN_5L = 86400     # 5连败 → 24小时 (v10.2升级)

EVENT_BLACKOUT = 30      # 经济事件前后不开单(分钟)

CORR_GROUPS = [
    ["BTCUSD", "ETHUSD"],
    ["EURUSD", "GBPUSD", "GBPJPY", "USDJPY"],
    ["XAUUSD"],
]
WD = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "BTCUSD", "ETHUSD"]
WE = ["BTCUSD", "ETHUSD"]
def gs():
    return WD if datetime.now().weekday() < 5 else WE

# 黄金时段: 伦敦/纽约盘(15:00-00:00), 占全天成交量73%
# 外汇/币: 24h
SESS = {
    "XAUUSD": [(15, 24)],
    "EURUSD": [(0, 23)], "GBPUSD": [(0, 23)], "USDJPY": [(0, 23)],
    "GBPJPY": [(0, 23)], "BTCUSD": [(0, 23)], "ETHUSD": [(0, 23)],
}
def ins(s):
    h = datetime.now().hour
    for a, b in SESS.get(s, [(0, 23)]):
        if a <= h < b:
            return True
    return False

# ═══════ 指标函数 ═══════
def catr(h, l):
    if len(h) < 15:
        return float(np.mean(h[-5:] - l[-5:]))
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(abs(h[1:] - l[:-1]), abs(l[1:] - h[:-1])))
    return float(pd.Series(tr).ewm(span=14).mean().iloc[-1])

def cadx(h, l, c):
    if len(c) < 28:
        return 0
    p = 14
    tr = np.maximum(h[1:] - l[1:],
                    np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    u = h[1:] - h[:-1]
    d = l[:-1] - l[1:]
    pdi = 100 * pd.Series(np.where((u > d) & (u > 0), u, 0)).ewm(span=p).mean() / (pd.Series(tr).ewm(span=p).mean() + 1e-10)
    mdi = 100 * pd.Series(np.where((d > u) & (d > 0), d, 0)).ewm(span=p).mean() / (pd.Series(tr).ewm(span=p).mean() + 1e-10)
    return float((100 * abs(pdi - mdi) / (pdi + mdi + 1e-10)).ewm(span=p).mean().iloc[-1])

# ═══════ 订单流 (取自 v10.2) ═══════
def calc_order_flow(sym):
    """计算买卖不平衡指标: >0 = 买压, <0 = 卖压"""
    import MetaTrader5 as mt5
    ticks = mt5.copy_ticks_from(sym, datetime.now(), 200)
    if ticks is None or len(ticks) < 50:
        return 0
    last_prices = [t[3] for t in ticks[-50:]]  # bid
    changes = np.diff(last_prices)
    up = sum(1 for c in changes if c > 0)
    down = sum(1 for c in changes if c < 0)
    total = up + down
    if total == 0:
        return 0
    return (up - down) / total  # -1~1, >0=买压

# ═══════ 经济日历 ═══════
def check_calendar_block():
    """检查是否在重大经济事件附近"""
    n = datetime.now()
    hm = n.hour * 60 + n.minute
    # 非农: 每月第一个周五 20:30 GMT+8
    if n.weekday() == 4 and n.day <= 7 and abs(hm - (20 * 60 + 30)) <= EVENT_BLACKOUT:
        return True, "NFP"
    # CPI: 每月公布日 20:30
    if n.day <= 15 and abs(hm - (20 * 60 + 30)) <= EVENT_BLACKOUT:
        return True, "CPI"
    return False, ""

# ═══════ 记忆系统 v10.4 (升级版: regime+zone+adx匹配) ═══════
MEM_FILE = os.path.join(BASE, "data", "v10_memory.json")

class TradeMemory:
    def __init__(self):
        self.mem = {}
        self.load()

    def load(self):
        if os.path.exists(MEM_FILE):
            try:
                with open(MEM_FILE, 'r', encoding='utf-8') as f:
                    self.mem = json.load(f)
            except:
                self.mem = {}

    def save(self):
        os.makedirs(os.path.dirname(MEM_FILE), exist_ok=True)
        with open(MEM_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.mem, f, indent=2)

    def record(self, sym, conditions, profit):
        if sym not in self.mem:
            self.mem[sym] = []
        self.mem[sym].append({
            **conditions,
            "profit": round(profit, 2),
            "time": datetime.now().isoformat()
        })
        if len(self.mem[sym]) > 500:
            self.mem[sym] = self.mem[sym][-500:]
        self.save()

    def should_skip(self, sym, conditions):
        """升级版记忆过滤: regime+zone+adx+方向 多维匹配 (取自v10.2)"""
        if sym not in self.mem or len(self.mem[sym]) < 15:
            return False

        recent = self.mem[sym][-80:]
        closed = [t for t in recent if t.get("profit", 0) != 0]
        if len(closed) < 8:
            return False

        adx = conditions.get("adx", 0)
        dr = conditions.get("direction", "")
        zt = conditions.get("zone", "")
        tf = conditions.get("trend", "")
        rg = conditions.get("regime", "")

        # 多维匹配: v10.2升级版
        hits = []
        for t in closed:
            score = 0
            if t.get("direction") == dr:
                score += 2
            if t.get("zone") == zt:
                score += 1
            if t.get("trend") == tf:
                score += 1
            if t.get("regime") == rg:
                score += 2
            if abs(t.get("adx", 0) - adx) < 4:
                score += 2
            if score >= 5:  # v10.2: 更高匹配阈值
                hits.append(t)

        if len(hits) < 3:
            return False

        wins = sum(1 for t in hits if t.get("profit", 0) > 0)
        wr = wins / len(hits)

        # 胜率<20% → 跳过
        if wr < 0.20:
            return True

        # 近5笔全SL → 跳过
        last5 = [t for t in closed[-5:] if t.get("close_reason") == "SL"]
        if len(last5) == 5:
            return True

        return False

    def get_stats(self, sym):
        if sym not in self.mem:
            return {"trades": 0, "wr": 0, "profit": 0}
        closed = [t for t in self.mem[sym] if t.get("profit") is not None and t.get("profit") != 0]
        if not closed:
            return {"trades": 0, "wr": 0, "profit": 0}
        wins = sum(1 for t in closed if t.get("profit", 0) > 0)
        total = sum(t.get("profit", 0) for t in closed)
        return {
            "trades": len(closed),
            "wr": round(wins / len(closed) * 100, 1),
            "profit": round(total, 2),
            "skip": sum(1 for t in self.mem[sym] if t.get("skipped", False)),
        }

# ═══════ 品种策略配置 ═══════
OPT_CFG = {
    "BTCUSD": {"s": "zone",      "sl": 1.2, "rr": 2.0, "adx": 16, "fast": 12, "slow": 26, "zm": 1.0},
    "ETHUSD": {"s": "zone",      "sl": 1.5, "rr": 2.0, "adx": 16, "fast": 10, "slow": 20, "zm": 1.0},
    "XAUUSD": {"s": "zone_gold", "sl": 1.5, "rr": 2.5, "adx": 22, "fast": 14, "slow": 28, "zm": 1.2},
    "EURUSD": {"s": "revert",    "sl": 0.8, "rr": 2.0, "adx": 12, "bb_period": 20, "bb_std": 2.0, "rsi_period": 14},
    "GBPUSD": {"s": "revert",    "sl": 0.8, "rr": 2.0, "adx": 12, "bb_period": 20, "bb_std": 2.0, "rsi_period": 14},
    "USDJPY": {"s": "revert",    "sl": 0.5, "rr": 2.0, "adx": 12, "bb_period": 20, "bb_std": 2.0, "rsi_period": 14},
    "GBPJPY": {"s": "revert",    "sl": 0.5, "rr": 2.0, "adx": 12, "bb_period": 20, "bb_std": 2.0, "rsi_period": 14},
}

MAGIC = {
    "BTCUSD": 20261030, "ETHUSD": 20261031, "XAUUSD": 20261032,
    "EURUSD": 20261033, "GBPUSD": 20261034, "USDJPY": 20261035, "GBPJPY": 20261036,
}


# ═══════════════════════════════════════════════
# 主引擎 v10.4
# ═══════════════════════════════════════════════
class SDPv104:
    """v10.4 合体引擎 — 黄金专精 × 渐进止盈 × 订单流"""

    def __init__(self):
        import MetaTrader5 as m
        self.m = m
        self.sd = None
        self.dp = 0.0
        self.dt = 0
        self.cd = 0          # cooldown until (time.time)
        self.cl = 0          # consecutive losses
        self.td = datetime.now().date()
        self._ld = None      # last deal id
        self.mem = TradeMemory()
        self._open_conds = {}  # ticket -> conditions
        self.ns = None       # NewsSentiment instance

    # ─── 连接 ───
    def conn(self):
        m = self.m
        for p in [
            r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe",
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
        ]:
            if os.path.exists(p) and m.initialize(path=p):
                break
        else:
            m.initialize()
        if not m.login(60043976, password="", server="TradeMaxGlobal-Demo"):
            return False
        for s in gs():
            m.symbol_select(s, True)
        return True

    # ─── 相关性互斥 ───
    def check_corr(self, sym):
        for grp in CORR_GROUPS:
            if sym not in grp:
                continue
            for sib in grp:
                if sib != sym and self.m.positions_get(symbol=sib):
                    return False
        return True

    # ═══════ 渐进止盈 (取自 v10.2) ═══════
    def manage_positions_advanced(self):
        """渐进止盈: 0.5R保本→1R锁50%→2R锁75%"""
        m = self.m
        for s in gs():
            p = m.positions_get(symbol=s)
            if not p:
                continue
            x = p[0]
            e = float(x.price_open)
            cu = float(x.price_current)
            sd = 1 if x.type == 0 else -1
            d_ = (cu - e) * sd
            sl = float(x.sl)
            tp = float(x.tp)
            r_ = abs(e - sl)
            if r_ <= 0:
                continue
            mult = d_ / r_

            # 渐进止盈里程碑
            if mult > 2.0:
                b = e + 1.5 * r_ * sd  # 锁75%利润
                if (sd == 1 and sl < b) or (sd == -1 and sl > b):
                    m.order_send({
                        "action": m.TRADE_ACTION_SLTP, "symbol": s,
                        "position": x.ticket, "sl": round(b, 2), "tp": tp,
                    })
            elif mult > 1.0:
                b = e + 0.5 * r_ * sd  # 锁50%利润
                if (sd == 1 and sl < b) or (sd == -1 and sl > b):
                    m.order_send({
                        "action": m.TRADE_ACTION_SLTP, "symbol": s,
                        "position": x.ticket, "sl": round(b, 2), "tp": tp,
                    })
            elif mult > 0.5:
                # 保本
                if (sd == 1 and sl < e) or (sd == -1 and sl > e):
                    m.order_send({
                        "action": m.TRADE_ACTION_SLTP, "symbol": s,
                        "position": x.ticket, "sl": round(e, 2), "tp": tp,
                    })

    # ═══════ 分析决策 (v10.1 + v10.2 融合) ═══════
    def analyze(self, sym):
        """
        融合分析流程:
        ① 经济日历过滤
        ② 订单流过滤 (v10.2)
        ③ H1 ADX/EMA/ATR
        ④ 市场状态 (regime)
        ⑤ 策略分叉: zone_gold(XAUUSD) / zone(BTC/ETH) / revert(外汇)
        ⑥ 新闻情感过滤 (v10.1)
        ⑦ 记忆过滤 (v10.2升级版)
        """
        m = self.m
        c = OPT_CFG[sym]

        # ── ① 经济日历过滤 ──
        blocked, _ = check_calendar_block()
        if blocked:
            return None

        # ── ② 订单流过滤 (v10.2) ──
        of = calc_order_flow(sym)

        # ── ③ H1 数据 ──
        h1 = m.copy_rates_from_pos(sym, m.TIMEFRAME_H1, 0, 60)
        if h1 is None or len(h1) < 30:
            return None
        h1d = pd.DataFrame(h1)
        h1c = h1d["close"].values
        h1h = h1d["high"].values
        h1l = h1d["low"].values
        cp = h1c[-1]
        atr = catr(h1h, h1l)
        adx = cadx(h1h[-30:], h1l[-30:], h1c[-30:])
        if adx < c["adx"]:
            return None

        # EMA趋势
        fast_ema = pd.Series(h1c).ewm(span=c["fast"]).mean().iloc[-1]
        slow_ema = pd.Series(h1c).ewm(span=c["slow"]).mean().iloc[-1]
        trend = "UP" if fast_ema > slow_ema else "DOWN"

        # ── ④ 市场状态 ──
        h4_full = m.copy_rates_from_pos(sym, m.TIMEFRAME_H4, 0, 40)
        h4_adx = 0
        if h4_full is not None and len(h4_full) > 30:
            h4d_full = pd.DataFrame(h4_full)
            h4_adx = cadx(
                h4d_full["high"].iloc[-30:].values,
                h4d_full["low"].iloc[-30:].values,
                h4d_full["close"].iloc[-30:].values,
            )
        regime = "trend"
        if h4_adx < 20 and adx < 20:
            regime = "ranging"
        if h4_adx > 35:
            regime = "strong_trend"
        atr_hist = []
        for j in range(max(0, 30 - 40), 30):
            haj = catr(h1h[max(0, j - 14):j + 1], h1l[max(0, j - 14):j + 1])
            atr_hist.append(haj)
        if atr_hist and atr > np.mean(atr_hist) * 1.8:
            regime = "volatile"

        # Regime自适应参数
        sl_mult = c["sl"]
        rr_mult = c["rr"]
        if regime == "ranging":
            sl_mult = min(sl_mult * 0.7, 0.8)
            rr_mult = max(rr_mult * 0.8, 1.5)
        elif regime == "strong_trend":
            sl_mult = max(sl_mult * 1.2, 1.0)
            rr_mult = rr_mult * 1.2
        elif regime == "volatile":
            return None

        # ── ⑤ 策略分叉 ──
        if c["s"] == "zone" or c["s"] == "zone_gold":
            # 路径A: H4供需区
            h4 = m.copy_rates_from_pos(sym, m.TIMEFRAME_H4, 0, 40)
            if h4 is None or len(h4) < 20:
                return None
            h4d = pd.DataFrame(h4)
            h4a = catr(h4d["high"].values, h4d["low"].values)
            from strategies.supply_demand import SupplyDemandSMC
            if self.sd is None:
                self.sd = SupplyDemandSMC({
                    "slb": 15, "bmb": 2, "bmx": 10, "rmn": 0.20, "rmx": 0.85
                })
            zo = self.sd.detect_zones(h4d.iloc[-30:])
            price = cp
            zm = c["zm"]
            zc = None
            zt = None
            flip = False

            for z in zo.get("demand", []):
                if z.strength >= zm and price > z.top and price - z.top < h4a * 3:
                    zc, zt = z, "D"
                    break
            if not zc:
                for z in zo.get("supply", []):
                    if z.strength >= zm and price < z.bottom and z.bottom - price < h4a * 3:
                        zc, zt = z, "S"
                        break
            if not zc:
                for z in zo.get("supply", []):
                    if price > z.top:
                        zc, zt = z, "D"
                        flip = True
                        break
            if not zc:
                for z in zo.get("demand", []):
                    if price < z.bottom:
                        zc, zt = z, "S"
                        flip = True
                        break
            if not zc:
                return None

            # zone_gold: D1方向过滤 + 结构止损
            if c["s"] == "zone_gold":
                d1_g = m.copy_rates_from_pos(sym, m.TIMEFRAME_D1, 0, 60)
                d1_t = "UP"
                if d1_g is not None and len(d1_g) >= 30:
                    d1d = pd.DataFrame(d1_g)
                    d1c = d1d["close"].values
                    d1e9 = pd.Series(d1c).ewm(span=9).mean().iloc[-1]
                    d1e21 = pd.Series(d1c).ewm(span=21).mean().iloc[-1]
                    d1_t = "UP" if d1e9 > d1e21 else "DOWN"

                dr = "BUY" if d1_t == "UP" and zt == "D" else "SELL" if d1_t == "DOWN" and zt == "S" else None
                if not dr:
                    return None

                # 📌 结构止损: 区边界外 + 缓冲 (v10.1黄金专精)
                buf = max(h4a * 0.1, 0.5)
                sl = zc.bottom - buf if dr == "BUY" else zc.top + buf
                tp = cp + (cp - sl) * c["rr"] if dr == "BUY" else cp - (sl - cp) * c["rr"]
                zone_tag = ("F" if flip else zt) + "G"
            else:
                # 普通zone
                dr = "BUY" if trend == "UP" and zt == "D" else "SELL" if trend == "DOWN" and zt == "S" else None
                if not dr:
                    return None
                sl = cp - atr * sl_mult
                tp = cp + (cp - sl) * rr_mult if dr == "BUY" else cp - (sl - cp) * rr_mult
                zone_tag = "F" if flip else zt

        elif c["s"] == "revert":
            # 路径B: 均值回归 (外汇)
            if regime == "strong_trend":
                return None
            sma = pd.Series(h1c).rolling(c["bb_period"]).mean().iloc[-1]
            std = pd.Series(h1c).rolling(c["bb_period"]).std().iloc[-1]
            bb_up = sma + c["bb_std"] * std
            bb_lw = sma - c["bb_std"] * std
            delta = np.diff(np.concatenate([[h1c[0]], h1c[-30:]]))
            gain = np.where(delta > 0, delta, 0)
            loss = np.where(delta < 0, -delta, 0)
            ag = pd.Series(gain).rolling(14).mean().iloc[-1]
            al = pd.Series(loss).rolling(14).mean().iloc[-1]
            rsi_val = 100 - (100 / (1 + ag / (al + 1e-10)))
            dr = None
            if cp < bb_lw and rsi_val < 35:
                dr = "BUY"
            elif cp > bb_up and rsi_val > 65:
                dr = "SELL"
            if not dr:
                return None
            sl = cp - atr * sl_mult if dr == "BUY" else cp + atr * sl_mult
            tp = cp + (cp - sl) * rr_mult if dr == "BUY" else cp - (sl - cp) * rr_mult
            zone_tag = "BB"
        else:
            return None

        # ── 📌 订单流增强过滤 (v10.2) ──
        # 买卖压力与方向一致才做
        if of > 0.3 and dr == "SELL":
            return None  # 买压强却要做空 → 放弃
        if of < -0.3 and dr == "BUY":
            return None  # 卖压强却要做多 → 放弃

        # ── ⑥ 新闻情感过滤 (v10.1) ──
        try:
            if self.ns is None:
                from news_sentiment import NewsSentiment
                self.ns = NewsSentiment()
            ns_skip, ns_reason = self.ns.should_skip_for_news(sym, dr)
            if ns_skip:
                return None
        except Exception:
            pass

        # ── ⑦ 记忆过滤 (v10.2升级版) ──
        conds = {
            "direction": dr,
            "adx": round(adx, 1),
            "trend": trend,
            "atr": round(atr, 1),
            "regime": regime,
            "h4_adx": round(h4_adx, 1),
            "strategy": c["s"],
            "symbol": sym,
            "orderflow": round(of, 2),
            "zone": zt if not flip else f"F{zt}",
        }
        if self.mem.should_skip(sym, conds):
            conds["skipped"] = True
            self.mem.record(sym, conds, 0)
            return None

        # ── 开单参数 ──
        t = m.symbol_info_tick(sym)
        if not t:
            return None
        entry = t.ask if dr == "BUY" else t.bid
        # 重新计算SL/TP (如非结构止损)
        if c["s"] != "zone_gold":
            if dr == "BUY":
                sl = entry - atr * sl_mult
                tp = entry + (entry - sl) * rr_mult
            else:
                sl = entry + atr * sl_mult
                tp = entry - (sl - entry) * rr_mult

        return {
            "sym": sym,
            "d": dr,
            "p": entry,
            "sl": sl,
            "tp": tp,
            "r": f"V{regime[0].upper()}{zone_tag}",
            "c": conds,
        }

    # ─── 执行 ───
    def exec(self, sig):
        m = self.m
        s = sig["sym"]
        c = MAGIC[s]
        t = m.symbol_info_tick(s)
        if not t:
            return False
        p = t.ask if sig["d"] == "BUY" else t.bid
        ot = m.ORDER_TYPE_BUY if sig["d"] == "BUY" else m.ORDER_TYPE_SELL
        sl = round(sig["sl"], 2)
        tp = round(sig["tp"], 2)
        for f in [m.ORDER_FILLING_IOC, m.ORDER_FILLING_FOK]:
            r = m.order_send({
                "action": m.TRADE_ACTION_DEAL, "symbol": s,
                "volume": MAX_LOT, "type": ot, "price": p,
                "sl": sl, "tp": tp, "deviation": 200,
                "magic": c, "comment": "v10.4",
                "type_time": m.ORDER_TIME_GTC, "type_filling": f,
            })
            if r and r.retcode == m.TRADE_RETCODE_DONE:
                self._open_conds[r.order] = sig["c"]
                return True
        return False

    # ─── 主循环 ───
    def run(self):
        m = self.m
        log = lambda x: print(f"[{datetime.now().strftime('%H:%M:%S')}] {x}", flush=True)
        wd = "周末" if datetime.now().weekday() >= 5 else "工作日"
        log(f"v10.4 合体版 | {wd} | {len(gs())}品种")
        log(f"  融合: D1方向+结构止损+时段限制(黄金专精)")
        log(f"  融合: 渐进止盈+订单流过滤+5连败冷却(24h)")

        while True:
            try:
                n = datetime.now()
                if n.date() != self.td:
                    self.td = n.date()
                    self.dt = 0
                    self.dp = 0.0
                if time.time() < self.cd:
                    time.sleep(5)
                    continue

                # ── 渐进止盈 (v10.2) ──
                self.manage_positions_advanced()

                # ── 平仓→记忆记录 ──
                h = m.history_deals_get(n.replace(hour=0, minute=0, second=0), n)
                if h:
                    for d in h[-10:]:
                        if "v10.4" in (d.comment or "") and d.profit != 0 and d.ticket != self._ld:
                            self._ld = d.ticket
                            cr = "TP" if d.profit > 0 else "SL"
                            conds = self._open_conds.pop(d.ticket, {})
                            conds["close_reason"] = cr
                            self.mem.record(d.symbol, conds, d.profit)
                            if d.profit < 0:
                                self.cl += 1
                                # v10.4: 三档冷却 (v10.2升级)
                                if self.cl >= 5:
                                    self.cd = time.time() + COOLDOWN_5L
                                elif self.cl >= 3:
                                    self.cd = time.time() + COOLDOWN_3L
                                elif self.cl >= 2:
                                    self.cd = time.time() + COOLDOWN_2L
                            else:
                                self.cl = 0
                            st = self.mem.get_stats(d.symbol)
                            log(f"[CLOSE] {d.symbol} {'W' if d.profit > 0 else 'L'} ${d.profit:.2f} | "
                                f"{st['trades']}笔WR{st['wr']}%")

                if self.dt >= MAX_TRADES or time.time() < self.cd:
                    time.sleep(5)
                    continue

                # ── 交易 ──
                for s in gs():
                    if m.positions_get(symbol=s):
                        continue
                    if not ins(s):
                        continue
                    if not self.check_corr(s):
                        continue
                    sig = self.analyze(s)
                    if sig and self.exec(sig):
                        self.dt += 1
                        log(f"[TRADE] {s} {sig['d']} @ ${sig['p']:.2f} | {sig['r']}")

                time.sleep(10)
            except KeyboardInterrupt:
                log("停止")
                break
            except Exception as e:
                log(f"[ERR] {e}")
                time.sleep(30)
        m.shutdown()


if __name__ == "__main__":
    e = SDPv104()
    if e.conn():
        e.run()
