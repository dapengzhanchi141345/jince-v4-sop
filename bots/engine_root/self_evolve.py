"""
Goldstrategy Guild v6.1 — 自进化引擎
记录每笔交易 → 分析表现 → 自动调整参数
"""
import json, os, time, math
from datetime import datetime
from collections import deque
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EVOLVE_FILE = os.path.join(BASE_DIR, "data", "evolve_state.json")
TRADE_LOG = os.path.join(BASE_DIR, "data", "evolve_trades.json")

# ───────── 默认参数 ─────────
DEFAULT_PARAMS = {
    "BTCUSD": {"sl_atr": 1.5, "rr_ratio": 2.0, "min_adx": 20, "min_zone_strength": 1.5, "risk_percent": 1.0},
    "ETHUSD": {"sl_atr": 1.5, "rr_ratio": 2.0, "min_adx": 20, "min_zone_strength": 1.5, "risk_percent": 1.0},
    "XAUUSD": {"sl_atr": 1.2, "rr_ratio": 2.5, "min_adx": 22, "min_zone_strength": 1.8, "risk_percent": 1.0},
    "EURUSD": {"sl_atr": 1.0, "rr_ratio": 2.5, "min_adx": 18, "min_zone_strength": 1.5, "risk_percent": 1.0},
    "GBPUSD": {"sl_atr": 1.0, "rr_ratio": 2.5, "min_adx": 18, "min_zone_strength": 1.5, "risk_percent": 1.0},
}

PARAM_BOUNDS = {
    "sl_atr": (1.0, 3.0),
    "rr_ratio": (1.0, 4.0),
    "min_adx": (15, 35),
    "min_zone_strength": (1.0, 3.0),
}

class SelfEvolve:
    """自进化引擎 — 从交易中学习"""
    
    def __init__(self):
        self.trades = deque(maxlen=200)  # 保留最近200笔
        self.params = {}
        self.load()
    
    def load(self):
        """加载状态"""
        self.params = {}
        for sym in DEFAULT_PARAMS:
            self.params[sym] = dict(DEFAULT_PARAMS[sym])
        
        try:
            with open(EVOLVE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for sym in data.get("params", {}):
                    if sym in self.params:
                        self.params[sym].update(data["params"][sym])
        except: pass
        
        try:
            with open(TRADE_LOG, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                for t in saved[-200:]:
                    self.trades.append(t)
        except: pass
    
    def save(self):
        """保存状态"""
        try:
            os.makedirs(os.path.dirname(EVOLVE_FILE), exist_ok=True)
            with open(EVOLVE_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "params": self.params,
                    "last_update": datetime.now().isoformat(),
                }, f, indent=2)
            with open(TRADE_LOG, 'w', encoding='utf-8') as f:
                json.dump(list(self.trades), f, indent=2)
        except: pass
    
    def record_open(self, symbol, direction, price, sl, tp, zone_type, zone_strength, 
                    h1_trend, adx, atr_val):
        """记录开单"""
        self.trades.append({
            "type": "OPEN",
            "time": time.time(),
            "symbol": symbol,
            "direction": direction,
            "price": price,
            "sl": sl,
            "tp": tp,
            "zone_type": zone_type,
            "zone_strength": zone_strength,
            "h1_trend": h1_trend,
            "adx": adx,
            "atr": atr_val,
        })
        self.save()
    
    def record_close(self, symbol, profit, close_price, close_reason="SL/TP"):
        """记录平仓，并触发学习"""
        # 找到最近的未平仓记录
        for t in reversed(self.trades):
            if t["type"] == "OPEN" and t["symbol"] == symbol and "close_time" not in t:
                t["close_time"] = time.time()
                t["profit"] = profit
                t["close_price"] = close_price
                t["close_reason"] = close_reason
                t["duration"] = t["close_time"] - t["time"]
                break
        self.save()
        
        # 触发进化分析
        self.evolve()
    
    def get_stats(self, symbol, n=20):
        """获取近期交易统计"""
        recent = [t for t in self.trades 
                  if t["type"] == "OPEN" and t["symbol"] == symbol 
                  and "profit" in t][-n:]
        
        if not recent:
            return {"win_rate": 0, "avg_profit": 0, "total": 0, "wins": 0, "losses": 0}
        
        wins = sum(1 for t in recent if t.get("profit", 0) > 0)
        losses = sum(1 for t in recent if t.get("profit", 0) < 0)
        profits = [t.get("profit", 0) for t in recent]
        avg_profit = np.mean(profits) if profits else 0
        
        # 按市场条件分拆
        conditions = {}
        for t in recent:
            prof = t.get("profit", 0)
            cond = f"{t.get('h1_trend','?')}|ADX>{t.get('adx',0):.0f}|{t.get('zone_type','?')}"
            if cond not in conditions: conditions[cond] = {"wins": 0, "losses": 0, "total": 0}
            if prof > 0: conditions[cond]["wins"] += 1
            else: conditions[cond]["losses"] += 1
            conditions[cond]["total"] += prof
        
        best_cond = max(conditions.items(), key=lambda x: x[1]["total"]) if conditions else ("N/A", {})
        
        return {
            "win_rate": wins / len(recent) if recent else 0,
            "avg_profit": avg_profit,
            "total": len(recent),
            "wins": wins,
            "losses": losses,
            "best_condition": best_cond[0],
            "best_condition_win_rate": best_cond[1].get("wins", 0) / max(1, best_cond[1].get("wins", 0) + best_cond[1].get("losses", 0)),
            "conditions": conditions,
        }
    
    def evolve(self):
        """核心进化逻辑：根据近期表现调参"""
        for sym in DEFAULT_PARAMS:
            stats = self.get_stats(sym, n=15)  # 最近15笔
            
            if stats["total"] < 3:
                continue  # 数据太少，不调整
            
            wr = stats["win_rate"]
            avg_p = stats["avg_profit"]
            p = self.params[sym]
            
            # ─── 调参规则 ───
            
            # 胜率<30% → 收紧所有参数（更保守）
            if wr < 0.30 and stats["total"] >= 3:
                p["sl_atr"] = min(PARAM_BOUNDS["sl_atr"][1], p["sl_atr"] + 0.3)
                p["min_adx"] = min(PARAM_BOUNDS["min_adx"][1], p["min_adx"] + 3)
                p["min_zone_strength"] = min(PARAM_BOUNDS["min_zone_strength"][1], p["min_zone_strength"] + 0.3)
                reason = f"胜率{wr*100:.0f}%过低→收紧: SL{ p['sl_atr']:.1f}ATR ADX>{p['min_adx']}"
            
            # 胜率>70% → 略微放宽
            elif wr > 0.70 and stats["total"] >= 5:
                p["sl_atr"] = max(PARAM_BOUNDS["sl_atr"][0], p["sl_atr"] - 0.2)
                p["min_adx"] = max(PARAM_BOUNDS["min_adx"][0], p["min_adx"] - 2)
                p["min_zone_strength"] = max(PARAM_BOUNDS["min_zone_strength"][0], p["min_zone_strength"] - 0.2)
                reason = f"胜率{wr*100:.0f}%高→放宽: SL{p['sl_atr']:.1f}ATR ADX>{p['min_adx']}"
            
            # 盈亏比不佳（平均亏损>平均盈利）→ 提高RR
            elif avg_p < 0 and stats["total"] >= 5:
                p["rr_ratio"] = min(PARAM_BOUNDS["rr_ratio"][1], p["rr_ratio"] + 0.3)
                reason = f"平均亏损${abs(avg_p):.2f}→提高RR至{p['rr_ratio']:.1f}"
            
            else:
                continue  # 表现正常，不调整
            
            # 记录进化
            from datetime import datetime
            log_msg = f"[EVOLVE][{sym}] {reason} (近{stats['total']}笔: {stats['wins']}W/{stats['losses']}L WR={wr*100:.0f}%)"
            print(log_msg, flush=True)
            
            # 写入evolve日志
            try:
                with open(os.path.join(BASE_DIR, "logs", "evolve.log"), 'a', encoding='utf-8') as f:
                    f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {log_msg}\n")
            except: pass
        
        self.save()
    
    def get_params(self, symbol):
        """获取当前参数"""
        return self.params.get(symbol, DEFAULT_PARAMS[symbol])
    
    def get_report(self):
        """生成报表"""
        lines = ["=== 自进化状态报告 ==="]
        for sym in DEFAULT_PARAMS:
            p = self.params[sym]
            stats = self.get_stats(sym)
            lines.append(f"  {sym}:")
            lines.append(f"    SL={p['sl_atr']:.1f}ATR RR=1:{p['rr_ratio']:.1f} ADX>{p['min_adx']} Zone>{p['min_zone_strength']}")
            lines.append(f"    近{stats['total']}笔: {stats['wins']}W/{stats['losses']}L WR={stats['win_rate']*100:.0f}%")
        return "\n".join(lines)
