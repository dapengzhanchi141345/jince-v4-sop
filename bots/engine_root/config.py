"""
金策宗师团 — 全局配置
Goldstrategy Guild — Configuration
"""

import os

# ──────────────────────────────────────────
# MT5 连接配置
# ──────────────────────────────────────────
MT5_CONFIG = {
    #⚠ 账号已于 2026-10-03 切换为 60137964，旧值 60043976 已废弃
    #   依据：data/ACCOUNT_60043976_REPORT.md 顶部废弃声明
    "server": "TradeMaxGlobal-Demo",  # 模拟盘（切勿改为实盘服务器名）
    "login": 60137964,                 # 当前练手 demo 账号
    "password": "",                    # P0: 明文凭证已剔除，凭证不入库
    "path": r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe",  # MT5终端路径
    "timeout": 60000,                  # 连接超时(ms)
}

# ───────── 实盘硬锁（防止误连真仓） ─────────
# account_info().trade_mode 语义：0=REAL, 1=DEMO, 2=CONTEST
# TradeMaxGlobal 的 Demo 账号历史实测trade_mode 也返回 0，因此不能只信该字段，
# 改为「trade_mode + 服务器名」双条件校验，任一不匹配即拒绝下单。
SAFETY_LIMITS = {
    "allow_live_trading": False,       # 总开关：改为 True 才允许真实资金交易
    "expected_trade_mode": 1,          # 期望 DEMO
    "deny_server_keywords": ("-Real", "-Live", "Live", "Real"),  # 服务器名含这些词即拒绝
}

# ──────────────────────────────────────────
# 交易参数
# ──────────────────────────────────────────
MARKET_TYPE = "CRYPTO"  # "FOREX" | "CRYPTO" — 切换自动调整参数

TRADING_CONFIG = {
    "symbol": "BTCUSD",
    "magic_number": 20260704,
    "comment": "Goldstrategy Guild",
    "timeframes": {
        "primary": "H1",
        "secondary": "M15",
        "entry": "M5",
    },
    "max_spread": 30,
    "max_slippage": 20,
    "order_filling": "IOC",
    "sessions": {
        "london_open": 8, "london_close": 17,
        "ny_open": 13, "ny_close": 22,
        "asia_open": 0, "asia_close": 9,
    },
}

# ──────────────────────────────────────────
# 市场类型参数 (自动切换)
# ──────────────────────────────────────────
MARKET_PARAMS = {
    "FOREX": {
        "max_spread": 30,
        "max_atr": 200.0,
        "min_rr_ratio": 2.0,
        "max_risk_per_trade_pct": 1.0,
        "min_volume": 0.01,
        "pip_value": 0.1,
        "label": "外汇",
    },
    "CRYPTO": {
        "max_spread": 5000,        # BTC点差大
        "max_atr": 5000.0,         # BTC波动大
        "min_rr_ratio": 1.5,       # BTC盈亏比要求放宽
        "max_risk_per_trade_pct": 0.5,  # 小账户风控更严
        "min_volume": 0.01,        # BTC最小手数 = 0.01
        "pip_value": 1.0,          # BTC pip计算不同
        "contract_size": 1.0,      # 1手=1BTC
        "label": "加密货币",
    },
}

# ──────────────────────────────────────────
# 策略权重配置 (GoldTraderEA 加权投票系统)
# ──────────────────────────────────────────
STRATEGY_WEIGHTS = {
    "supply_demand": 3,      # 供需区 (SDP核心)
    "order_block_smc": 3,    # SMC订单块
    "fvg": 2,                # 公允价值缺口
    "liquidity_sweep": 2,    # 流动性扫荡
    "trend_ema": 2,          # EMA趋势
    "trend_adx": 1,          # ADX趋势强度
    "macd": 1,               # MACD
    "rsi_mean_reversion": 1, # RSI均值回归
    "bollinger": 1,          # 布林带
    "candle_pattern": 2,     # K线形态
    "divergence": 3,         # 背离 (高权重)
    "support_resistance": 2, # 支撑阻力
}

# 投票通过阈值 (总分需要超过此值才允许入场)
VOTE_THRESHOLD_DEFAULT = 12
VOTE_THRESHOLDS_BY_REGIME = {
    "STRONG_TREND": 10,
    "WEAK_TREND": 12,
    "HIGH_VOLATILITY": 14,
    "RANGING": 15,
}

# ──────────────────────────────────────────
# 风险配置 (12层风控体系)
# ──────────────────────────────────────────
RISK_CONFIG = {
    "kelly_fraction": 0.25,      # Fractional Kelly 系数
    "max_risk_per_trade": 1.0,   # 单笔最大风险 (%)
    "max_daily_risk": 3.0,       # 日最大风险 (%)
    "max_daily_trades": 5,       # 日最大交易次数
    "max_drawdown_pct": 10.0,    # 最大回撤暂停 (%)
    "consecutive_loss_limit": 3, # 连亏N笔后降频
    "cooloff_minutes": 30,       # 连亏后冷却时间 (分钟)
    "min_rr_ratio": 2.0,         # 最小盈亏比
    "min_atr": 10.0,             # 最小ATR
    "max_atr": 200.0,            # 最大ATR
    "anti_martingale": True,     # 盈利后适度加仓
    "anti_martingale_mult": 1.5, # 加仓倍数上限
}

# ──────────────────────────────────────────
# HMM 市场状态检测
# ──────────────────────────────────────────
HMM_CONFIG = {
    "n_regimes": 4,              # 4种状态
    "lookback_days": 90,         # 训练窗口
    "retrain_interval": 24,      # 每N小时重训练
    "features": ["returns", "atr_ratio", "rsi", "adx"],
}

# ──────────────────────────────────────────
# 数据配置
# ──────────────────────────────────────────
DATA_CONFIG = {
    "bars_to_fetch": 500,        # 每次获取K线数
    "zone_scan_limit": 100,      # 供需区扫描范围
    "swing_lookback": 20,        # Swing判断回看根数
    "base_min_bars": 3,          # 基底最小K线数
    "base_max_bars": 20,         # 基底最大K线数
    "retracement_min": 0.30,     # 最小回调比例
    "retracement_max": 0.80,     # 最大回调比例
}

# ──────────────────────────────────────────
# 数据路径配置 (统一到E盘)
# ──────────────────────────────────────────
BASE_DIR = "E:/GoldstrategyEngine"
PATHS = {
    "base_dir": BASE_DIR,
    "data_dir": f"{BASE_DIR}/data",
    "backup_dir": f"{BASE_DIR}/backup",
    "log_dir": f"{BASE_DIR}/logs",
    "config_dir": f"{BASE_DIR}/config",
    "trade_log": f"{BASE_DIR}/logs/trades.csv",
    "signal_log": f"{BASE_DIR}/logs/signals.csv",
    "equity_log": f"{BASE_DIR}/logs/equity.csv",
    "journal_log": f"{BASE_DIR}/logs/trader_journal.csv",
    "regime_log": f"{BASE_DIR}/logs/regime.csv",
    "dashboard": f"{BASE_DIR}/logs/dashboard.html",
    "signal_file": f"{BASE_DIR}/data/signals/latest.json",
    "registry_db": f"{BASE_DIR}/data/model_registry.db",
    "memory_file": f"{BASE_DIR}/data/deep_memory.json",
    "strategy_pool": f"{BASE_DIR}/data/strategy_pool.json",
    "evolution_state": f"{BASE_DIR}/data/evolution_state.json",
    "backup_state": f"{BASE_DIR}/data/backup_state.json",
}

# ──────────────────────────────────────────
# 引擎模式
# ──────────────────────────────────────────
ENGINE_MODE = "DEMO"  # "DEMO" | "LIVE" — 重要: 切换为LIVE前必须充分测试
