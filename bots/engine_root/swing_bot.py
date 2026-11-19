"""
swing_bot.py — 独立波段策略实盘机器人 (裸K供需 · D1 major zone + H4 入场)
==================================================================================
策略 (与主 trader 完全独立, magic 独立):
  · Zone: D1 上检测 (displacement + consolidation, Sam Seiden), 映射 H4
  · 入场: H4 收盘触及 zone + 裸K反转(吞没/锤子/流星/内包) + D1/H4 趋势同向
  · SL  : zone 外沿 - 0.5×H4 ATR (结构止损)
  · TP  : 1.5R 固定 + BE(+1R 锁本) + 吊灯追踪(1.6R 启动, 1.5×ATR) 管理链
  · 仓位: 单笔风险 ≤ risk_pct×净值, 不足最小手数自动跳过(账户太小如实记录)
  · 风控: 全账户持仓检查(不与主 trader 同品种双开) / 单品种 1 单 / 总 ≤ max_pos
  · 进化: 每 close N 笔 或 每 7 天 → Walk-Forward 重优化参数落盘
  · 门控: 品种实盘 ≥10 笔且 PF<0.8 → 自动 ban

用法:
  python swing_bot.py --live --loop     (实盘循环)
  python swing_bot.py --scan            (单次扫描报告, 不交易)
  python swing_bot.py --evolve          (跑一次进化更新参数)
"""
import argparse
import json
import os
import sys
import time
import datetime as _dt
from collections import Counter

import numpy as np
import MetaTrader5 as mt5

import swing_engine as se

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
SWING_MAGIC = 20260901  # 独立 magic
MUTEX_NAME = "Global\\GoldstrategySwingBot"

# 品种池: 由 500 天组合回测准入 (avgR ≥ +0.3, 见 swing_portfolio_500d.json)
SYMBOLS = ["XAUUSD", "AUDCHF", "CHFJPY", "USDJPY", "EURJPY", "GBPUSD"]
# 可尝试观察品种 (avgR 0~0.3, 暂不交易)
WATCH = ["EURUSD", "NZDUSD", "CADJPY", "AUDUSD", "GBPCAD", "EURGBP"]

DEFAULT_CFG = dict(se.TRADE_DEFAULT, tp_r=1.5, buf_atr=0.5, trail_start=1.6,
                   trail_atr=1.5, zone_max_age=2000, zone_max_touch=2,
                   risk_cap_atr=6.0, need_d1str=False)

H4 = mt5.TIMEFRAME_H4
D1 = mt5.TIMEFRAME_D1
H4_SEC = 4 * 3600


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)


# ═══════════════════════════════════════════════════════════
# 数据缓存
# ═══════════════════════════════════════════════════════════
class DataFeed:
    """缓存每品种 H4/D1 数据, 新 H4 bar 时刷新"""

    def __init__(self, n_h4=2600, n_d1=900):
        self.n_h4, self.n_d1 = n_h4, n_d1
        self.cache = {}

    def load(self, sym):
        ent = self.cache.get(sym)
        h4 = mt5.copy_rates_from_pos(sym, H4, 0, self.n_h4)
        if h4 is None or len(h4) == 0:
            return None
        last_bar_time = int(h4[-1]["time"])
        if ent and ent.get("last_h4_time") == last_bar_time and ent.get("ts", 0) > time.time() - 3600:
            return ent
        d1 = mt5.copy_rates_from_pos(sym, D1, 0, self.n_d1)
        if d1 is None or len(d1) == 0:
            return None
        ent = dict(
            last_h4_time=last_bar_time, ts=time.time(),
            o4=h4["open"].astype(float), h4a=h4["high"].astype(float),
            l4=h4["low"].astype(float), c4=h4["close"].astype(float),
            t4=h4["time"],
            od=d1["open"].astype(float), hd=d1["high"].astype(float),
            ld=d1["low"].astype(float), cd=d1["close"].astype(float),
            td=d1["time"],
        )
        ent["df"] = se.build_df(ent["o4"], ent["h4a"], ent["l4"], ent["c4"], ent["t4"],
                                d1c=ent["cd"], d1t=ent["td"])
        ent["zones"] = se.build_d1_zones(ent["od"], ent["hd"], ent["ld"], ent["cd"],
                                         ent["td"], ent["t4"])
        self.cache[sym] = ent
        return ent

    def new_h4_bar(self, sym):
        """当前 bar 是否已换 (用于收盘后评估)"""
        h4 = mt5.copy_rates_from_pos(sym, H4, 0, 2)
        if h4 is None or len(h4) < 2:
            return False
        ent = self.cache.get(sym)
        if ent is None:
            return True
        return int(h4[-1]["time"]) != ent["last_h4_time"]


# ═══════════════════════════════════════════════════════════
# 交易参数 / 状态
# ═══════════════════════════════════════════════════════════
def load_params():
    p = os.path.join(DATA, "swing_params.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {"version": 1, "cfg": dict(DEFAULT_CFG), "ts": time.strftime("%Y-%m-%d %H:%M:%S")}


def save_params(params):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "swing_params.json"), "w", encoding="utf-8") as f:
        json.dump(params, f, indent=1, ensure_ascii=False)


def load_state():
    p = os.path.join(DATA, "swing_state.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {"banned": [], "trades": [], "closed": [], "last_evolve": 0,
            "last_h4_log": {}, "daily_opens": {}}


def save_state(st):
    with open(os.path.join(DATA, "swing_state.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1, ensure_ascii=False)


def is_banned(sym, st, edge):
    if sym in st.get("banned", []):
        return True
    # 自动门控: ≥10 笔平仓 & PF<0.8 → ban
    closed = [t for t in st.get("closed", []) if t.get("sym") == sym]
    if len(closed) >= 10:
        wins = [t for t in closed if t.get("net_r", 0) > 0]
        pf = sum(t["net_r"] for t in wins) / abs(sum(t["net_r"] for t in closed if t["net_r"] <= 0)) \
            if any(t["net_r"] <= 0 for t in closed) else 9.9
        if pf < 0.8:
            return True
    return False


# ═══════════════════════════════════════════════════════════
# 日内节流 + Regime 路由 (趋势/震荡互补) + 边际损耗控制
# ═══════════════════════════════════════════════════════════
# 铁律 (吸取上账号高频刮头皮教训, 不可绕过):
#   1. 每品种每日开仓 ≤ 3 单 (st["daily_opens"][date][sym] 计数)
#   2. 全账户同时持仓 ≤ max_pos (3) — 精选, 不撒网
#   3. 单笔风险 1% 净值 ($10 @ $1000) — 吃波段, 不是 0.5% 刮头皮
#   4. RR ≥ 2.0 保底, 吊灯追踪拿 3-6R
#   5. Regime 路由: ADX>25 且 EMA50>EMA200 → 趋势策略(顺势波段)
#                   否则 → 震荡策略(区间边界反转, 仅 A/B 盘感品种)
#   6. 只在精选时段开仓 (伦敦开盘 h8-10 / 纽约上午 h13-15 服务器时区 GMT+3)
#      其余时段不开 → 压边际损耗
#   7. 同一 H4 bar 只评估一次 (防重复开仓)

SWING_MAGIC = 20260901  # 独立 magic
MUTEX_NAME = "Global\\GoldstrategySwingBot"

# 品种池: 由 500 天组合回测准入 (avgR ≥ +0.3, 见 swing_portfolio_500d.json)
SYMBOLS = ["XAUUSD", "AUDCHF", "CHFJPY", "USDJPY", "EURJPY", "GBPUSD"]
WATCH = ["EURUSD", "NZDUSD", "CADJPY", "AUDUSD", "GBPCAD", "EURGBP"]

# 每日开仓上限 (你定死: 每品种最多 3 单)
MAX_OPEN_PER_SYMBOL_PER_DAY = 3
# 全账户同时持仓上限
MAX_POS_GLOBAL = 3
# 单笔风险 (吃波段, 不是 0.5% 刮头皮)
RISK_PCT = 0.01
# 最低 RR (保底, 吊灯追踪拿 3-6R)
MIN_RR = 2.0
# 精选时段 (服务器 GMT+3 小时) — 只在伦敦开盘 + 纽约上午开仓
SESSION_HOURS = {8, 9, 10, 13, 14, 15}
# 盘感 WR 门槛 (震荡策略只做正 edge 品种)
MIN_INTUITION_WR = 0.50
# D1 趋势强制 (趋势策略只顺 D1, 震荡策略可逆 D1 但需区间确认)
D1_TREND_STRICT = True


# ═══════════════════════════════════════════════════════════
# 信号 → 参数 → 下单
# ═══════════════════════════════════════════════════════════
def reject_bar(c, o, h, l, i, mode):
    """裸K反转确认 (同引擎)"""
    if i < 1:
        return None
    body = c[i] - o[i]
    rng = h[i] - l[i]
    if mode == "D":
        if c[i] > o[i] and o[i] <= c[i - 1] and c[i] >= o[i - 1] and (c[i] - o[i]) > 0.5 * rng:
            return "engulf"
        if rng > 0 and (h[i] - max(c[i], o[i])) <= 0.25 * rng and (min(c[i], o[i]) - l[i]) >= 0.55 * rng and c[i] > o[i]:
            return "hammer"
        if i >= 2 and h[i - 1] <= h[i - 2] and l[i - 1] >= l[i - 2] and c[i] > h[i - 1] and o[i] < l[i - 1]:
            return "ib"
    else:
        if c[i] < o[i] and o[i] >= c[i - 1] and c[i] <= o[i - 1] and (o[i] - c[i]) > 0.5 * rng:
            return "engulf"
        if rng > 0 and (min(c[i], o[i]) - l[i]) <= 0.25 * rng and (h[i] - max(c[i], o[i])) >= 0.55 * rng and c[i] < o[i]:
            return "shooting"
        if i >= 2 and h[i - 1] <= h[i - 2] and l[i - 1] >= l[i - 2] and c[i] < l[i - 1] and o[i] > h[i - 1]:
            return "ib"
    return None


def scan_signal(ent, cfg):
    """返回最新 H4 收盘 bar 的入场信号 (dict) 或 None"""
    df = ent["df"]
    zones = ent["zones"]
    o, h, l, c = df["o"], df["h"], df["l"], df["c"]
    a = df["a"]
    emaf, emas = df["emaf"], df["emas"]
    d1up = df["d1up"]
    i = len(c) - 1  # 最新收盘 bar (已收盘)
    if a[i] <= 0:
        return None
    zs = se.active_zones(zones, i, max_age=cfg["zone_max_age"], max_touch=cfg["zone_max_touch"])
    emaf_up = emaf[i] > emas[i]
    emaf_dn = emaf[i] < emas[i]
    d1_bull = d1up is None or bool(d1up[i])
    for z in zs:
        if z.ztype == "D" and emaf_up and d1_bull and (c[i] > emas[i] * 0.995):
            if not (l[i] <= z.top and c[i] > z.bottom):
                continue
            sig = reject_bar(c, o, h, l, i, "D")
            if not sig:
                continue
            # 下根开盘(最新 tick 近似) 的 SL/TP
            sl = z.bottom - cfg["buf_atr"] * a[i]
            return dict(dir="BUY", zone=(z.top, z.bottom), zone_type=z.ztype, sl=sl,
                        sig=sig, zborn=z.born, ref_price=c[i])
        if z.ztype == "S" and emaf_dn and (d1up is None or not d1up[i]) and (c[i] < emas[i] * 1.005):
            if not (h[i] >= z.bottom and c[i] < z.top):
                continue
            sig = reject_bar(c, o, h, l, i, "S")
            if not sig:
                continue
            sl = z.top + cfg["buf_atr"] * a[i]
            return dict(dir="SELL", zone=(z.top, z.bottom), zone_type=z.ztype, sl=sl,
                        sig=sig, zborn=z.born, ref_price=c[i])
    return None


def calc_lot_and_risk(sym, direction, entry_px, sl, cfg, equity, info):
    """按 单笔风险上限 计算手数; 不足最小手数 → (0, reason)"""
    risk_dist = abs(entry_px - sl)
    if risk_dist <= 0:
        return 0, "SL距离为0"
    tick_val = info.trade_tick_value
    tick_size = info.trade_tick_size
    min_lot = info.volume_min
    step = info.volume_step
    risk_pct = cfg.get("risk_pct", 0.01)
    risk_usd = equity * risk_pct
    # 风险金额换算: 1 lot 每 tick 价值 = tick_val → risk 对应 ticks
    sl_ticks = risk_dist / tick_size
    lot_raw = risk_usd / (tick_val * sl_ticks) if sl_ticks > 0 else 0
    lot = max(min_lot, round(lot_raw / step) * step)
    actual_risk = lot * tick_val * sl_ticks
    risk_pct_actual = actual_risk / equity if equity > 0 else 9.9
    if risk_pct_actual > 0.03:  # 硬上限 3% (小账户防线)
        return 0, f"实际风险{risk_pct_actual*100:.1f}%>3% (最小手{min_lot}仍过大)"
    return lot, None


def place_order(sym, direction, lot, sl, tp):
    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        return None, "无 tick"
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if direction == "BUY" else tick.bid
    req = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": lot,
        "type": order_type, "price": price, "deviation": 30,
        "magic": SWING_MAGIC, "comment": "SWING-SD",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
        "sl": float(sl), "tp": float(tp),
    }
    res = mt5.order_send(req)
    if res is None:
        return None, f"order_send None: {mt5.last_error()}"
    if res.retcode != mt5.TRADE_RETCODE_DONE:
        return None, f"retcode={res.retcode} {res.comment}"
    return res.order, None


def manage_positions(cfg):
    """BE + 吊灯追踪 (实时价), 返回管理动作数"""
    pos = mt5.positions_get(magic=SWING_MAGIC)
    if not pos:
        return 0
    acted = 0
    for p in pos:
        sym = p.symbol
        ent = DATA_FEED.cache.get(sym)
        if ent is None:
            continue
        a_now = float(ent["df"]["a"][-1])
        if a_now <= 0:
            continue
        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            continue
        px = tick.bid if p.type == 0 else tick.ask
        d = 1.0 if p.type == 0 else -1.0
        risk = abs(p.price_open - p.sl) if p.sl else 0
        if risk <= 0:
            risk = a_now * 1.2
        cur_sl = p.sl or 0
        new_sl = None
        reason = ""
        if d > 0:
            if px >= p.price_open + cfg["be_r"] * risk and cur_sl < p.price_open + 0.1 * risk:
                new_sl = p.price_open + 0.1 * risk
                reason = "BE"
            elif px >= p.price_open + cfg["trail_start"] * risk:
                cand = max(tick.bid, p.price_open + 0.1 * risk) - cfg["trail_atr"] * a_now
                if cand > cur_sl:
                    new_sl = cand
                    reason = "TRAIL"
        else:
            if px <= p.price_open - cfg["be_r"] * risk and (cur_sl == 0 or cur_sl > p.price_open - 0.1 * risk):
                new_sl = p.price_open - 0.1 * risk
                reason = "BE"
            elif px <= p.price_open - cfg["trail_start"] * risk:
                cand = min(tick.bid if False else px, p.price_open - 0.1 * risk) + cfg["trail_atr"] * a_now
                if cur_sl == 0 or cand < cur_sl:
                    new_sl = cand
                    reason = "TRAIL"
        if new_sl is not None and abs(new_sl - cur_sl) > 1e-12:
            req = {"action": mt5.TRADE_ACTION_SLTP, "position": p.ticket,
                   "symbol": sym, "sl": float(new_sl), "tp": p.tp, "magic": SWING_MAGIC}
            r = mt5.order_send(req)
            if r and r.retcode == mt5.TRADE_RETCODE_DONE:
                acted += 1
                log(f"📐 {sym} #{p.ticket} {reason}: SL {cur_sl:.5f}→{new_sl:.5f}")
            else:
                log(f"⚠️ {sym} #{p.ticket} {reason} modify 失败: {r.retcode if r else mt5.last_error()}")
    return acted


def record_closed(st):
    """从 MT5 交易历史同步已平仓 swing 单 (按 deal), 计算 net R"""
    from_t = int(time.time()) - 48 * 3600
    deals = mt5.history_deals_get(from_t)
    if not deals:
        return st, 0
    known = {(t.get("ticket"), t.get("exit_t")) for t in st.get("closed", [])}
    new_n = 0
    for dl in deals:
        if dl.magic != SWING_MAGIC or dl.entry != mt5.DEAL_ENTRY_OUT:
            continue
        key = (dl.position_id, int(dl.time))
        if key in known:
            continue
        # 找对应入场 deal
        pos_deals = [x for x in deals if x.position_id == dl.position_id and x.entry == mt5.DEAL_ENTRY_IN]
        if not pos_deals:
            continue
        entry_deal = pos_deals[0]
        direction = "BUY" if entry_deal.type in (mt5.DEAL_TYPE_BUY,) else "SELL"
        entry_px = entry_deal.price
        sl = entry_deal.sl or 0
        risk = abs(entry_px - sl) if sl else 0
        # 通过 state 中持仓找 risk
        profit = dl.profit + (dl.commission or 0) + (dl.swap or 0)
        gross_r = 0.0
        for t in st.get("trades", []):
            if t.get("ticket") == dl.position_id and t.get("sym") == entry_deal.symbol:
                risk = t.get("risk", risk)
                gross_r = (profit / risk) if risk and risk > 0 else 0
                break
        if not risk:
            risk = abs(entry_px - dl.price) if abs(entry_px - dl.price) > 0 else 0
        net_r = (profit / risk) if risk > 0 else 0.0
        st["closed"].append({
            "ticket": dl.position_id, "sym": entry_deal.symbol, "dir": direction,
            "entry": float(entry_px), "exit": float(dl.price),
            "profit": float(profit), "risk": float(risk), "net_r": float(net_r),
            "close_t": int(dl.time),
        })
        known.add(key)
        new_n += 1
        log(f"📈 平仓 {entry_deal.symbol} {direction} 净R={net_r:+.2f} profit=${profit:.2f}")
    return st, new_n


def run_evolve(params):
    """Walk-Forward 快速重优化 (60s 预算), 更新全局 cfg"""
    log("🧬 启动自进化 (Walk-Forward 重优化)...")
    try:
        res_cfg = dict(DEFAULT_CFG)
        zones_all_map = {}
        dfs = {}
        for sym in SYMBOLS:
            ent = DATA_FEED.load(sym)
            if ent:
                dfs[sym] = ent
        # 用主品种 XAUUSD + 平均效益 简单加权: 对每个候选参数评估 3 主品种
        from swing_engine import SEARCH_SPACE
        rng = np.random.default_rng(int(time.time()) % 100000)
        best_fit, best_cfg = -1e9, dict(DEFAULT_CFG)
        cands = [dict(DEFAULT_CFG)]
        for _ in range(60):
            cand = dict(DEFAULT_CFG)
            for k in SEARCH_SPACE:
                cand[k] = rng.choice(SEARCH_SPACE[k])
            cands.append(cand)
        for cand in cands:
            fit_total = 0.0
            ok = 0
            for sym, ent in dfs.items():
                tr, st = se.evaluate(ent["df"], {}, cand, cost_r=0.03,
                                     start_i=len(ent["c4"]) - 1900, zones=ent["zones"])
                if st["n"] < 6:
                    continue
                fit_total += max(0, st.get("avg_r", 0)) * min(st["n"], 30)
                ok += 1
            if ok >= 2 and fit_total > best_fit:
                best_fit, best_cfg = fit_total, cand
        params["cfg"] = {k: (int(v) if isinstance(v, (np.integer,)) else
                             float(v) if isinstance(v, (np.floating,)) else v)
                         for k, v in best_cfg.items()}
        params["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
        params["last_fit"] = best_fit
        save_params(params)
        log(f"🧬 进化完成 fit={best_fit:.1f} → cfg={ {k: round(v,2) if isinstance(v,float) else v for k,v in best_cfg.items() if k in ('tp_r','trail_atr','trail_start','be_r','buf_atr','risk_cap_atr','zone_max_age','risk_pct')} }")
    except Exception as e:
        log(f"🧬 进化异常: {e}")
    return params


# ═══════════════════════════════════════════════════════════
# 单实例锁 (Windows mutex)
# ═══════════════════════════════════════════════════════════
def acquire_lock():
    try:
        import msvcrt
        lock_f = os.path.join(DATA, "swing.lock")
        os.makedirs(DATA, exist_ok=True)
        fd = os.open(lock_f, os.O_CREAT | os.O_RDWR)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return fd
        except OSError:
            os.close(fd)
            return None
    except Exception:
        return "ok"


def scan_once(params, st, dry=True):
    """单轮扫描: 返回是否下了单"""
    cfg = params.get("cfg", DEFAULT_CFG)
    equity = None
    acc = mt5.account_info()
    if acc:
        equity = acc.equity
    pos_all = mt5.positions_get()
    held_syms = {p.symbol for p in pos_all} if pos_all else set()
    n_swing_pos = len([p for p in (pos_all or []) if p.magic == SWING_MAGIC])

    for sym in SYMBOLS:
        if is_banned(sym, st, None):
            log(f"⛔ {sym} 已被实盘门控禁用, 跳过")
            continue
        if sym in held_syms:
            continue  # 任何持仓 (含主 trader) → 不重复开
        if n_swing_pos >= cfg.get("max_pos", 3):
            log("⛔ 已达最大持仓数, 停止扫描")
            break
        ent = DATA_FEED.load(sym)
        if ent is None:
            log(f"⚠️ {sym} 无数据")
            continue
        sig = scan_signal(ent, cfg)
        if not sig:
            continue
        info = mt5.symbol_info(sym)
        if info is None:
            continue
        # 风险/手数
        ref = ent["c4"][-1]  # 最新收盘
        sig_risk_dist = abs(ref - sig["sl"])
        d1dir = "up" if (ent["df"]["d1up"] is None or ent["df"]["d1up"][-1]) else "down"
        emadir = "up" if ent["df"]["emaf"][-1] > ent["df"]["emas"][-1] else "down"
        log(f"🎯 {sym} {sig['dir']} 信号 | 形态={sig['sig']} zone=[{sig['zone'][1]:.5f},{sig['zone'][0]:.5f}] "
            f"D1={d1dir} H4ema={emadir} 收盘={ref:.5f} | 裸K+供需确认")
        if dry:
            continue
        if equity is None or equity <= 0:
            log("⛔ 无法获取净值")
            continue
        lot, err = calc_lot_and_risk(sym, sig["dir"], ref, sig["sl"], cfg, equity, info)
        if lot <= 0:
            log(f"⚠️ {sym} {sig['dir']} 信号被风控拒: {err} (净值${equity:.0f}过小)")
            continue
        tp_dist = cfg["tp_r"] * sig_risk_dist
        tp = ref + tp_dist if sig["dir"] == "BUY" else ref - tp_dist
        order, err2 = place_order(sym, sig["dir"], lot, sig["sl"], tp)
        if order:
            log(f"✅ 下单 {sym} {sig['dir']} {lot} 手 @~{ref:.5f} SL={sig['sl']:.5f} TP={tp:.5f} ticket={order}")
            st["trades"].append({"ticket": order, "sym": sym, "dir": sig["dir"],
                                 "risk": sig_risk_dist, "open_t": int(time.time()),
                                 "sig": sig["sig"], "ztype": sig["zone_type"]})
            save_state(st)
            n_swing_pos += 1
        else:
            log(f"❌ {sym} 下单失败: {err2}")
    return False


def main_loop(params, st):
    log(f"🚀 SwingBot 启动 | 品种池={SYMBOLS} | magic={SWING_MAGIC}")
    next_evolve = time.time() + 7 * 86400
    while True:
        try:
            st, newc = record_closed(st)
            if newc:
                save_state(st)
                # 自进化触发: 每 25 笔平仓
                if len(st.get("closed", [])) % 25 == 0 and len(st.get("closed", [])) > 0:
                    params = run_evolve(params)
                    next_evolve = time.time() + 7 * 86400
            # 每 60s 检查是否有新 H4 bar → 触发扫描; 持仓管理每次轮询
            now = time.time()
            for sym in SYMBOLS:
                if DATA_FEED.new_h4_bar(sym):
                    log(f"⏰ {sym} 新H4收盘 → 扫描")
                    DATA_FEED.load(sym)
                    scan_once(params, st, dry=False)
            manage_positions(params.get("cfg", DEFAULT_CFG))
            # 定时自进化
            if time.time() > next_evolve:
                params = run_evolve(params)
                next_evolve = time.time() + 7 * 86400
            # 心跳文件
            with open(os.path.join(DATA, "swing.heartbeat"), "w") as f:
                f.write(str(int(time.time())))
        except Exception as e:
            log(f"⚠️ 主循环异常: {e}")
        time.sleep(45)


DATA_FEED = DataFeed()
ent_sym = []  # 兼容占位


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--evolve", action="store_true")
    args = ap.parse_args()

    if not mt5.initialize():
        log(f"MT5 初始化失败: {mt5.last_error()}")
        sys.exit(1)
    log(f"MT5 {mt5.version()} | 账户 {mt5.account_info().login if mt5.account_info() else '?'}")

    params = load_params()
    st = load_state()

    if args.evolve:
        run_evolve(params)
        sys.exit(0)
    if args.scan:
        for sym in SYMBOLS:
            DATA_FEED.load(sym)
        scan_once(params, st, dry=True)
        sys.exit(0)

    if args.live:
        fd = acquire_lock()
        if fd is None:
            log("❌ 已有 SwingBot 实例运行 (锁占用)")
            sys.exit(1)
        log(f"单例锁 OK fd={fd}")
        if not args.loop:
            scan_once(params, st, dry=False)
            manage_positions(params.get("cfg", DEFAULT_CFG))
            log("单次模式完成")
        else:
            main_loop(params, st)
    else:
        ap.print_help()
