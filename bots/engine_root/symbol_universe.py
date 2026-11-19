# symbol_universe.py — 金策宗师团 · 全品种宇宙 (策金尊 CIO 升级 V2)
"""
目的: 把系统从"39 个品种"扩展到"券商可交易的全品种宇宙"(外汇/贵金属/能源/
      加密货币/全球股指/农产品商品/债券), 支持"先全品种放开交易 → 收集盈亏数据
      → 按盈利筛选决定保留哪些"。

设计要点:
  1. UNIVERSE 覆盖 8 大类别 ~150 个品种。
  2. 每个品种带合约经济参数 (pip / 每手每pip美元 / 默认手数 / 点差),
     使跨品种盈亏排名**公平可比**。
  3. 点值/手数/点差为通用估算, 落地前应以券商实际合约规格校准
     (尤其指数/债券点值、加密-USDT 计价)。
  4. DATA_COLLECTION_MODE: 收集模式开关。开启时直播扫描器放开 EDGE GATE,
     全品种都能开仓(仍守双铁律/风控), 用于"先放开、后筛选"。默认关闭。
  5. classify_filter(): 按盈利 + 样本量给出 KEEP / COLLECT / CUT 决策。

字段:
  name           中文名
  cls            类别
  pip            一个 pip 对应的价格单位
  pip_usd        1 手(=1.0 lot) 每波动 1 pip 的美元价值
  lot            默认交易手数 (实际由 risk_per_trade≤1% 主导, 此处仅回测/参考)
  spread_price   点差(价格单位, 与 pip 同尺度)
  session        UTC 交易时段 (start_hour, end_hour); (0,24)=几乎全时段
  adx_min        入场 ADX 门槛
  sl_mult        SL = H4 ATR × 该倍数
  rr_mult        TP/SL 盈亏比
  max_daily      每日最大开仓数
"""

import os
import json
import math
from typing import Dict, List, Optional, Tuple

# 外汇合约: 1 标准手 = 100,000 基础货币单位 (主流零售/ECN 规格)
FX_CONTRACT_SIZE = 100000.0

# 用于推导 "货币→USD" 汇率表的品种 (必须含 USD 一侧, 从已下载 CSV 取中位价)
_FX_USD_RATE_PAIRS = [
    'EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD',
    'USDCHF', 'USDCAD', 'USDJPY',
    'USDSEK', 'USDNOK', 'USDDKK', 'USDZAR', 'USDTRY', 'USDMXN',
    'USDPLN', 'USDHUF', 'USDCZK', 'USDHKD',
]
_FX_CLASSES = {'forex_major', 'forex_cross', 'jpy_cross', 'exotic'}

# ════════════════════════════════════════════════════════════════
# 1. 收集模式开关 + 筛选阈值
# ════════════════════════════════════════════════════════════════
# 开启 = 直播引擎放开 EDGE GATE, 全品种都能交易(仍守双铁律), 用于收集数据。
# 关闭 = 维持原行为(只放行有证明优势的品种)。
DATA_COLLECTION_MODE = False

# 每个品种最少多少笔成交, 才达到"样本可用于筛选决策"的门槛。
COLLECT_MIN_TRADES = 30

# 筛选阈值 (基于回测/实盘统计)
FILTER = {
    "keep_pf": 1.15,        # PF ≥ 1.15 且样本充足 → KEEP
    "keep_net_positive": True,
    "cut_pf": 0.95,         # PF < 0.95 → CUT (无论样本量, 负期望直接砍)
    "min_trades_for_keep": 30,
}


# ════════════════════════════════════════════════════════════════
# 2. 类别默认模板 (减少重复, 便于统一校准)
# ════════════════════════════════════════════════════════════════
_DEFAULTS: Dict[str, Dict] = {
    # 外汇主流 (Majors)
    "forex_major": dict(pip=0.0001, pip_usd=10.0, lot=1.0, spread_price=0.00007,
                        session=(0, 24), adx_min=12, sl_mult=0.8, rr_mult=2.0, max_daily=10),
    # 外汇交叉盘 (非 JPY)
    "forex_cross": dict(pip=0.0001, pip_usd=10.0, lot=0.6, spread_price=0.00015,
                        session=(0, 24), adx_min=14, sl_mult=0.9, rr_mult=2.0, max_daily=6),
    # 外汇交叉盘 (含 JPY, pip=0.01)
    "jpy_cross":   dict(pip=0.01, pip_usd=10.0, lot=0.5, spread_price=0.008,
                        session=(0, 24), adx_min=14, sl_mult=0.9, rr_mult=2.0, max_daily=6),
    # 外汇稀有货币对 (Exotics, 点差大、波动大)
    "exotic":      dict(pip=0.0001, pip_usd=10.0, lot=0.3, spread_price=0.0004,
                        session=(0, 24), adx_min=16, sl_mult=1.0, rr_mult=2.0, max_daily=4),
    # 黄金 (XAU)
    "metal":       dict(pip=0.01, pip_usd=1.0, lot=0.1, spread_price=0.30,
                        session=(15, 24), adx_min=22, sl_mult=1.5, rr_mult=2.5, max_daily=6),
    # 铂/钯 (XPT/XPD, 1 手=100oz)
    "metal_pgm":   dict(pip=1.0, pip_usd=100.0, lot=0.1, spread_price=1.0,
                        session=(15, 24), adx_min=22, sl_mult=1.5, rr_mult=2.5, max_daily=5),
    # 白银 (XAG)
    # [2026-08-24 修复] pip_usd 50.0→1.0: MT5真实规格 tick_value=$1/手/0.001点,
    # 原配置放大50倍风险 (XAG配对腿曾算到$340=66%净值). 与metal(XAU)同为$1.
    "metal_ag":    dict(pip=0.001, pip_usd=1.0, lot=0.1, spread_price=0.02,
                        session=(15, 24), adx_min=22, sl_mult=1.4, rr_mult=2.3, max_daily=6),
    # 加密主流 (BTC/ETH)
    "crypto":      dict(pip=1.0, pip_usd=1.0, lot=0.01, spread_price=0.5,
                        session=(0, 24), adx_min=18, sl_mult=1.3, rr_mult=2.0, max_daily=8),
    # 加密中盘 (SOL/DOT/LTC/BCH 等)
    "crypto_alt":  dict(pip=0.01, pip_usd=1.0, lot=0.1, spread_price=0.02,
                        session=(0, 24), adx_min=18, sl_mult=1.4, rr_mult=2.0, max_daily=6),
    # 加密小盘 (XRP/ADA 等, pip=0.0001)
    "crypto_small":dict(pip=0.0001, pip_usd=1.0, lot=1.0, spread_price=0.0003,
                        session=(0, 24), adx_min=18, sl_mult=1.3, rr_mult=2.0, max_daily=6),
    # 全球股指 (点值因券商而异, 此处按 1 手=1 指数点×1$ 估算)
    "index":       dict(pip=1.0, pip_usd=1.0, lot=0.1, spread_price=1.5,
                        session=(1, 24), adx_min=20, sl_mult=1.5, rr_mult=2.2, max_daily=6),
    # 亚太大股指 (近全时段)
    "index_asia":  dict(pip=1.0, pip_usd=1.0, lot=0.1, spread_price=2.0,
                        session=(0, 24), adx_min=20, sl_mult=1.5, rr_mult=2.2, max_daily=6),
    # 能源 (WTI/Brent)
    "energy":      dict(pip=0.01, pip_usd=10.0, lot=0.1, spread_price=0.03,
                        session=(1, 24), adx_min=20, sl_mult=1.5, rr_mult=2.2, max_daily=6),
    # 天然气
    "energy_gas":  dict(pip=0.001, pip_usd=10.0, lot=0.1, spread_price=0.004,
                        session=(1, 24), adx_min=22, sl_mult=1.6, rr_mult=2.0, max_daily=5),
    # 农产品/软商品 (咖啡/糖/棉)
    "commodity_soft": dict(pip=0.01, pip_usd=10.0, lot=0.1, spread_price=0.1,
                        session=(10, 22), adx_min=18, sl_mult=1.3, rr_mult=1.8, max_daily=5),
    # 谷物 (小麦/玉米/大豆)
    "commodity_grain":dict(pip=0.1, pip_usd=10.0, lot=0.1, spread_price=0.2,
                        session=(10, 22), adx_min=18, sl_mult=1.3, rr_mult=1.8, max_daily=5),
    # 债券 (10Y/5Y/2Y 等)
    "bond":        dict(pip=0.01, pip_usd=10.0, lot=0.1, spread_price=0.02,
                        session=(8, 22), adx_min=18, sl_mult=1.2, rr_mult=1.8, max_daily=4),
    # 美股 / 港股 (个股, 点值由券商 tick_value 真实标定)
    "stock":       dict(pip=0.01, pip_usd=1.0, lot=0.1, spread_price=0.02,
                        session=(1, 24), adx_min=20, sl_mult=1.5, rr_mult=2.2, max_daily=6),
    # ETF (QQQ/SPY 等)
    "etf":         dict(pip=0.01, pip_usd=1.0, lot=0.1, spread_price=0.02,
                        session=(1, 24), adx_min=20, sl_mult=1.5, rr_mult=2.2, max_daily=6),
}


def _mk(cls: str, name: str, **ov) -> Dict:
    """用类别默认模板 + 覆盖项生成一个品种配置。"""
    d = dict(_DEFAULTS[cls])
    d["name"] = name
    d["cls"] = cls
    d.update(ov)
    return d


# ════════════════════════════════════════════════════════════════
# 2.5 外汇合约美元点值标定 (修正 exotic 弱货币导致的盈亏放大)
# ════════════════════════════════════════════════════════════════
def _median_close(data_dir: str, sym: str):
    """取某品种已下载 CSV (D1优先, 回退 H1) 的收盘价中位数。"""
    import pandas as pd
    for tf in ('D1', 'H1'):
        p = os.path.join(data_dir, f"{sym}_{tf}.csv")
        if os.path.exists(p):
            try:
                df = pd.read_csv(p)
                if 'close' in df.columns and len(df) > 5:
                    return float(df['close'].median())
            except Exception:
                pass
    return None


def calibrate_forex_pip_usd(data_dir: str) -> Tuple[int, Dict[str, Tuple[float, float]]]:
    """用真实市场中位价推导每个外汇品种的 pip_usd, 修正 exotic (TRY/ZAR/MXN...)
    因弱货币报价导致的美元盈亏放大误差 (~40–130×)。

    原理:
      pip_usd(每标准手每pip美元) = pip × 合约规模(100000) × (1单位报价货币的USD值)
      其中 "报价货币USD值" 由 _FX_USD_RATE_PAIRS 的实盘中位价构建。

    Returns:
      (更新数量, {品种: (旧pip_usd, 新pip_usd)})
    """
    # 1) 建 货币→USD 汇率表
    usd = {'USD': 1.0}
    for s in _FX_USD_RATE_PAIRS:
        p = _median_close(data_dir, s)
        if not p or p <= 0:
            continue
        base, quote = s[:3], s[3:]
        if quote == 'USD':
            usd[base] = p
        elif base == 'USD':
            usd[quote] = 1.0 / p

    # 2) 重算每个外汇品种的 pip_usd
    changed: Dict[str, Tuple[float, float]] = {}
    for sym, cfg in UNIVERSE.items():
        if cfg["cls"] not in _FX_CLASSES:
            continue
        base, quote = sym[:3], sym[3:]
        if base in usd and quote in usd:
            old = cfg["pip_usd"]
            new = round(cfg["pip"] * FX_CONTRACT_SIZE * usd[quote], 4)
            if abs(new - old) > 1e-6:
                cfg["pip_usd"] = new
                changed[sym] = (old, new)
    return len(changed), changed


# ════════════════════════════════════════════════════════════════
# 3. 全品种宇宙
# ════════════════════════════════════════════════════════════════
UNIVERSE: Dict[str, Dict] = {}

# ── 外汇主流 (Majors) ──
for _s, _n in [("EURUSD", "欧元/美元"), ("GBPUSD", "英镑/美元"),
               ("USDCHF", "美元/瑞郎"), ("AUDUSD", "澳元/美元"), ("USDCAD", "美元/加元"),
               ("NZDUSD", "纽元/美元")]:
    UNIVERSE[_s] = _mk("forex_major", _n)
# USDJPY 是日元叉盘, pip=0.01 (非 0.0001), 单独覆盖避免盈亏标定放大 100 倍
UNIVERSE["USDJPY"] = _mk("forex_major", "美元/日元", pip=0.01, pip_usd=10.0, lot=1.0,
                         spread_price=0.004, adx_min=12, sl_mult=0.5, rr_mult=2.0, max_daily=10)

# ── 外汇交叉盘 (非 JPY) ──
for _s, _n in [("EURGBP", "欧元/英镑"), ("EURCHF", "欧元/瑞郎"), ("EURNZD", "欧元/纽元"),
               ("EURCAD", "欧元/加元"), ("EURAUD", "欧元/澳元"), ("GBPCHF", "英镑/瑞郎"),
               ("GBPNZD", "英镑/纽元"), ("GBPAUD", "英镑/澳元"), ("GBPCAD", "英镑/加元"),
               ("AUDNZD", "澳元/纽元"), ("AUDCHF", "澳元/瑞郎"), ("AUDCAD", "澳元/加元"),
               ("CADCHF", "加元/瑞郎"), ("NZDCHF", "纽元/瑞郎"), ("NZDCAD", "纽元/加元")]:
    UNIVERSE[_s] = _mk("forex_cross", _n)

# ── 外汇交叉盘 (含 JPY) ──
for _s, _n in [("EURJPY", "欧元/日元"), ("GBPJPY", "英镑/日元"), ("AUDJPY", "澳元/日元"),
               ("CADJPY", "加元/日元"), ("CHFJPY", "瑞郎/日元"), ("NZDJPY", "纽元/日元")]:
    UNIVERSE[_s] = _mk("jpy_cross", _n)

# ── 外汇稀有货币对 (Exotics) ──
for _s, _n in [("USDSEK", "美元/瑞典克朗"), ("USDNOK", "美元/挪威克朗"), ("USDDKK", "美元/丹麦克朗"),
               ("USDZAR", "美元/南非兰特"), ("USDTRY", "美元/土耳其里拉"), ("USDMXN", "美元/墨西哥比索"),
               ("USDPLN", "美元/波兰兹罗提"), ("USDHUF", "美元/匈牙利福林"), ("USDCZK", "美元/捷克克朗"),
               ("USDHKD", "美元/港币"), ("EURTRY", "欧元/土耳其里拉"), ("EURZAR", "欧元/南非兰特")]:
    UNIVERSE[_s] = _mk("exotic", _n)

# ── 贵金属 (Metals) ──
UNIVERSE["XAUUSD"] = _mk("metal", "黄金")
UNIVERSE["XAGUSD"] = _mk("metal_ag", "白银")
UNIVERSE["XPTUSD"] = _mk("metal_pgm", "铂金")
UNIVERSE["XPDUSD"] = _mk("metal_pgm", "钯金")

# ── 能源 (Energies) ──
UNIVERSE["XTIUSD"] = _mk("energy", "WTI原油")
UNIVERSE["XBRUSD"] = _mk("energy", "布伦特原油")
UNIVERSE["XNGUSD"] = _mk("energy_gas", "天然气")
UNIVERSE["XHOUSD"] = _mk("energy", "取暖油", spread_price=0.03)

# ── 加密货币 (Crypto, 24h) ──
for _s, _n in [("BTCUSD", "比特币"), ("ETHUSD", "以太坊")]:
    UNIVERSE[_s] = _mk("crypto", _n)
for _s, _n in [("BCHUSD", "比特币现金"), ("LTCUSD", "莱特币"), ("SOLUSD", "Solana"),
               ("DOTUSD", "波卡"), ("LINKUSD", "Chainlink"), ("AVAXUSD", "Avalanche"),
               ("MATICUSD", "Polygon"), ("ATOMUSD", "Cosmos"), ("XLMUSD", "Stellar"),
               ("TRXUSD", "波场"), ("ETCUSD", "以太坊经典"), ("EOSUSD", "EOS"),
               ("NEARUSD", "Near"), ("APTUSD", "Aptos"), ("FILUSD", "Filecoin"),
               ("SANDUSD", "Sandbox"), ("MANAUSD", "Decentraland"), ("AXSUSD", "Axie"),
               ("THETAUSD", "Theta"), ("XTZUSD", "Tezos"), ("ALGOUSD", "Algorand"),
               ("EGLDUSD", "Elrond"), ("FLOWUSD", "Flow"), ("CHZUSD", "Chiliz"),
               ("ENJUSD", "Enjin"), ("GALAUSD", "Gala"), ("APEUSD", "ApeCoin"),
               ("CRVUSD", "Curve"), ("LDOUSD", "Lido"), ("OPUSD", "Optimism"),
               ("ARBUSD", "Arbitrum"), ("SUIUSD", "Sui"), ("INJUSD", "Injective"),
               ("TIAUSD", "Celestia"), ("SEIUSD", "Sei"), ("RUNEUSD", "THORChain"),
               ("STXUSD", "Stacks"), ("IMXUSD", "ImmutableX"), ("MKRUSD", "Maker"),
               ("SNXUSD", "Synthetix"), ("COMPUSD", "Compound"), ("YFIUSD", "Yearn"),
               ("BATUSD", "BasicAttention"), ("ZECUSD", "Zcash"), ("DASHUSD", "Dash"),
               ("UNIUSD", "Uniswap"), ("FTMUSD", "Fantom"), ("HBARUSD", "Hedera"),
               ("XRPUSD", "瑞波币"), ("ADAUSD", "艾达币")]:
    if _s in ("XRPUSD", "ADAUSD"):
        UNIVERSE[_s] = _mk("crypto_small", _n)
    else:
        UNIVERSE[_s] = _mk("crypto_alt", _n)

# ── 全球股指 (Indices) ──
for _s, _n in [("US30", "道琼斯30"), ("NAS100", "纳斯达克100"), ("SPX500", "标普500"),
               ("US2000", "罗素2000"), ("DE30", "德国DAX"), ("UK100", "英国FTSE100"),
               ("FRA40", "法国CAC40"), ("ESP35", "西班牙IBEX35"), ("ITA40", "意大利MIB"),
               ("NED25", "荷兰AEX"), ("SWI20", "瑞士SMI"), ("EU50", "欧洲STOXX50"),
               ("POR20", "葡萄牙PSI20"), ("BEL20", "比利时BEL20"), ("POL20", "波兰WIG20"),
               ("HUN30", "匈牙利BUX"), ("USDX", "美元指数")]:
    UNIVERSE[_s] = _mk("index", _n)
for _s, _n in [("JP225", "日经225"), ("HK50", "香港恒生"), ("CHN50", "中国A50"),
               ("TWN25", "台湾加权"), ("KOSPI200", "韩国KOSPI200"), ("SING30", "新加坡STI"),
               ("AUS200", "澳洲ASX200"), ("CAN60", "加拿大SPTSX60"), ("BRA50", "巴西Ibovespa"),
               ("MEX35", "墨西哥IPC"), ("IND50", "印度Nifty50")]:
    UNIVERSE[_s] = _mk("index_asia" if _s in ("JP225", "HK50", "CHN50", "TWN25",
               "KOSPI200", "SING30") else "index", _n)

# ── 农产品/软商品 (Commodities) ──
for _s, _n in [("COFFEE", "咖啡"), ("SUGAR", "糖#11"), ("COCOA", "可可"),
               ("COTTON", "棉花#2"), ("ORANGEJUICE", "橙汁"), ("RICE", "稻谷")]:
    UNIVERSE[_s] = _mk("commodity_soft", _n)
for _s, _n in [("WHEAT", "小麦"), ("CORN", "玉米"), ("SOYBEAN", "大豆"),
               ("SOYOIL", "豆油"), ("SOYMEAL", "豆粕"), ("LUMBER", "木材")]:
    UNIVERSE[_s] = _mk("commodity_grain", _n)

# ── 债券 (Bonds) ──
for _s, _n in [("US10Y", "美债10年"), ("US05Y", "美债5年"), ("US02Y", "美债2年"),
               ("DE10Y", "德债10年"), ("UK10Y", "英债10年"), ("JP10Y", "日债10年")]:
    UNIVERSE[_s] = _mk("bond", _n)


# ════════════════════════════════════════════════════════════════
# 2.6 动态全品种宇宙 (策金尊 CIO: 把 65 硬编码 → 券商全量 248)
# ════════════════════════════════════════════════════════════════
_FX_CCY = {"USD","EUR","GBP","JPY","CHF","CAD","AUD","NZD","TRY","ZAR","MXN",
           "SEK","NOK","DKK","PLN","HUF","CZK","HKD","SGD","THB"}
_EXOTIC_CCY = {"TRY","ZAR","MXN","SEK","NOK","DKK","PLN","HUF","CZK"}
_ASIA_IDX = {"JP225","HK50","CHN50","TWN25","KOSPI200","SING30"}


def _is_forex(nm: str) -> bool:
    return len(nm) == 6 and nm[:3] in _FX_CCY and nm[3:] in _FX_CCY


def _forex_subclass(nm: str) -> str:
    if nm in ("EURUSD","GBPUSD","AUDUSD","NZDUSD","USDCHF","USDCAD","USDJPY"):
        return "forex_major"
    if nm[3:] == "JPY":
        return "jpy_cross"
    base, quote = nm[:3], nm[3:]
    if base in ("USD",) and quote in _EXOTIC_CCY:
        return "exotic"
    if quote == "USD" and base in _EXOTIC_CCY:
        return "exotic"
    return "forex_cross"


def _classify(name: str, ti) -> str:
    """按券商 group + 符号把品种映射到资产类别 cls。"""
    grp = (ti.path or "").split("\\")[0].strip() if getattr(ti, "path", None) else ""
    gu = grp.upper()
    nm = name.upper()
    if _is_forex(nm):
        return _forex_subclass(nm)
    if "GOLD" in gu or "GRAM" in gu or "METAL" in gu or nm.startswith(("XAU","XAG","XPT","XPD")):
        if nm.startswith("XAG"):
            return "metal_ag"
        if nm.startswith(("XPT","XPD")):
            return "metal_pgm"
        return "metal"
    if gu == "OIL":
        return "energy_gas" if nm == "XNGUSD" else "energy"
    if gu in ("BITCOIN","ALTCOINS"):
        if nm in ("BTCUSD","ETHUSD"):
            return "crypto"
        if nm in ("XRPUSD","ADAUSD"):
            return "crypto_small"
        return "crypto_alt"
    if gu == "INDEX" or gu == "INDEX ASIA":
        return "index_asia" if nm in _ASIA_IDX else "index"
    if "STOCK" in gu:
        return "stock"
    if gu == "ETF":
        return "etf"
    return "index"   # 兜底: 归入指数类(点值型, 保守)


def _pip_for(cls: str, name: str, digits: int) -> float:
    if cls in ("forex_major","forex_cross"):
        return 0.0001
    if cls == "jpy_cross":
        return 0.01
    if cls == "metal":
        return 0.01
    if cls == "metal_ag":
        return 0.001
    if cls == "metal_pgm":
        return 1.0
    if cls in ("index","index_asia"):
        return 1.0
    if cls == "energy":
        return 0.01
    if cls == "energy_gas":
        return 0.001
    if cls.startswith("crypto"):
        return 0.01 if cls == "crypto_alt" else (0.0001 if cls == "crypto_small" else 1.0)
    if cls in ("stock","etf"):
        return 0.01
    return (10 ** (-digits)) if digits else 0.01


def build_full_universe(data_dir: str = ".", verbose: bool = True) -> int:
    """动态把券商全品种接入 UNIVERSE (替代硬编码 65 个)。

    连接 MT5 → 订阅 symbols_get() 全部 → 按 group 分类 → 用真实
    trade_tick_value/tick_size 计算 pip_usd (根治指数 10-13× 低估) →
    合并进 UNIVERSE。幂等, 可重复调用。返回接入品种数。
    """
    import MetaTrader5 as _mt5
    if not _mt5.initialize():
        if verbose:
            print("  [全宇宙] MT5 初始化失败, 退回硬编码 UNIVERSE")
        return len(UNIVERSE)
    try:
        all_syms = _mt5.symbols_get() or []
    except Exception:
        all_syms = []
    added = 0
    tf_h1 = getattr(_mt5, "TIMEFRAME_H1", 0)
    for s in all_syms:
        nm = s.name
        try:
            _mt5.symbol_select(nm, True)
            ti = _mt5.symbol_info(nm)
        except Exception:
            ti = None
        if ti is None:
            continue
        tm = int(ti.trade_mode)
        if tm not in (1, 2, 4):      # 不可开仓 (禁用/仅平仓) → 跳过
            continue
        spread = float(ti.spread) if ti.spread else 0.0
        if spread <= 0:              # 券商常对最优流动性品种(如EURUSD)报0点差
            # 不剔除真实可交易品种, 用保守最小点差(2 tick)估计, 偏安全
            spread = max(float(ti.trade_tick_size) * 2.0, 1.0)
        cls = _classify(nm, ti)
        if cls is None:
            continue
        d = dict(_DEFAULTS[cls])
        d["name"] = nm
        d["cls"] = cls
        digits = int(ti.digits) if ti.digits else 5
        tick_size = float(ti.trade_tick_size) or (10 ** (-digits))
        tick_value = float(ti.trade_tick_value) or 0.0
        # 强制拉一次行情, 触发 MT5 填充 tick_value (订阅瞬间常为 0)
        if tick_value <= 0:
            try:
                _mt5.copy_rates_from_pos(nm, tf_h1, 0, 1)
                ti2 = _mt5.symbol_info(nm)
                if ti2 and ti2.trade_tick_value and ti2.trade_tick_value > 0:
                    tick_value = float(ti2.trade_tick_value)
                    tick_size = float(ti2.trade_tick_size) or tick_size
            except Exception:
                pass
        pip = _pip_for(cls, nm, digits)
        contract = float(ti.trade_contract_size) if ti.trade_contract_size else 100000.0
        if tick_value > 0 and tick_size > 0:
            pip_usd = (tick_value / tick_size) * pip
        else:
            # 回退: USD 计价品种 contract_size×pip 即每手每pip美元
            # (如 US30: 10×1=$10, 精确; 非USD计价如日元叉盘略偏保守)
            pip_usd = contract * pip
        d["pip"] = pip
        d["pip_usd"] = round(float(pip_usd), 6)
        d["spread_price"] = spread * tick_size
        d["vol_min"] = float(ti.volume_min) if ti.volume_min else d.get("vol_min", 0.01)
        d["vol_step"] = float(ti.volume_step) or d.get("vol_step", 0.01)
        d["vol_max"] = float(ti.volume_max) or d.get("vol_max", 100.0)
        d["contract_size"] = contract
        d["trade_mode"] = tm
        d["tradable"] = True
        d["spec_source"] = "MT5_LIVE"
        UNIVERSE[nm] = d
        added += 1
    if verbose:
        n_trad = sum(1 for c in UNIVERSE.values() if c.get("tradable"))
        print(f"  [全宇宙] 券商共 {len(all_syms)} 个品种, 已动态接入 {added} 个 "
              f"(可交易 {n_trad}, 类别覆盖 {len(set(c['cls'] for c in UNIVERSE.values()))})")
    return added



# ════════════════════════════════════════════════════════════════
# 3.9 真实账户规格注入 (来自 MT5 account_calibrate.py)
#     优先级: MT5 真实规格 > 汇率推导标定 > 类别模板估算
# ════════════════════════════════════════════════════════════════
ACCOUNT: Dict = {}          # 账户信息 (login/balance/leverage/currency)
SPECS: Dict[str, Dict] = {}  # 券商真实规格


def apply_account_specs(data_dir: str, verbose: bool = True) -> Tuple[int, Dict]:
    """读取 data/account_specs.json, 用 MT5 真实合约规格覆盖宇宙配置。

    覆盖字段:
      pip_usd      <- tick_value/tick_size*pip  (真实每 pip 美元值)
      spread_price <- 券商真实点差 (价格单位)
      vol_min/vol_step/vol_max <- 真实手数约束
      margin_min   <- 开最小手所需保证金
      broker_symbol/tradable
    返回 (覆盖品种数, {sym: (old_pip_usd, new_pip_usd)})
    """
    global ACCOUNT, SPECS
    path = os.path.join(data_dir, "account_specs.json")
    if not os.path.exists(path):
        if verbose:
            print(f"  [规格] 未找到 {path}, 跳过真实规格注入 (先跑 account_calibrate.py)")
        return 0, {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        if verbose:
            print(f"  [规格] 读取失败: {e}")
        return 0, {}

    ACCOUNT = payload.get("account", {}) or {}
    SPECS = payload.get("specs", {}) or {}
    changed: Dict[str, Tuple[float, float]] = {}
    n = 0
    for sym, sp in SPECS.items():
        if sp.get("status") != "OK" or sym not in UNIVERSE:
            continue
        cfg = UNIVERSE[sym]
        pu_new = sp.get("pip_usd_real") or 0.0
        if pu_new > 0:
            pu_old = cfg.get("pip_usd") or 0.0
            if abs(pu_new - pu_old) > 1e-9:
                changed[sym] = (pu_old, pu_new)
            cfg["pip_usd"] = pu_new
        sp_price = sp.get("spread_price")
        if sp_price and sp_price > 0:
            cfg["spread_price"] = sp_price
        cfg["vol_min"] = sp.get("volume_min") or 0.01
        cfg["vol_step"] = sp.get("volume_step") or 0.01
        cfg["vol_max"] = sp.get("volume_max") or 100.0
        cfg["margin_min"] = sp.get("margin_min_lot")
        cfg["broker_symbol"] = sp.get("broker_symbol")
        cfg["tradable"] = bool(sp.get("tradable"))
        cfg["spec_source"] = "MT5"
        n += 1
    if verbose:
        bal = ACCOUNT.get("balance")
        print(f"  [规格] 已注入 MT5 真实规格: {n} 个品种 | 账户 {ACCOUNT.get('login')} "
              f"@ {ACCOUNT.get('server')} 余额 ${bal} 杠杆 1:{ACCOUNT.get('leverage')}")
    return n, changed


def risk_lot(cfg: Dict, sl_pips: float, equity: float, risk_pct: float = 1.0,
             max_risk_mult: float = 2.0,
             allow_min_lot: bool = False,
             hard_usd_cap: float = None) -> Tuple[float, float, bool]:
    """按账户资金 + 固定分数风险计算真实手数 (受券商最小手/步长约束)。

    returns (lots, actual_risk_usd, ok)
      ok=False 表示即使最小手风险也超过 max_risk_mult 倍目标 -> 真实账户不该开这一笔
    """
    pip_usd = cfg.get("pip_usd") or 0.0
    if sl_pips <= 0 or pip_usd <= 0 or equity <= 0:
        return 0.0, 0.0, False
    target = equity * risk_pct / 100.0
    v_min = cfg.get("vol_min", 0.01)
    v_step = cfg.get("vol_step", 0.01) or 0.01
    v_max = cfg.get("vol_max", 100.0)

    raw = target / (sl_pips * pip_usd)          # 理论手数
    lots = math.floor(raw / v_step) * v_step     # 按步长向下取整 (保守)
    if lots < v_min:
        lots = v_min                             # 不足最小手 -> 只能开最小手
    lots = min(lots, v_max)
    lots = round(lots, 4)
    risk = sl_pips * pip_usd * lots
    ok = risk <= target * max_risk_mult          # 最小手风险仍超 2 倍目标 -> 放弃
    # [2026-08-18 A+B+C/C1] 收集数据阶段(allow_min_lot=True): 即便最小手风险超
    #   max_risk_mult, 也允许以最小手开仓(修复 5191 次"开不起"——宽 SL 品种被永久拒);
    #   但若设 hard_usd_cap 且最小手风险仍超该绝对美元上限, 仍拒绝(防 USDSEK 类
    #   -1395pip 爆亏). allow_min_lot 默认 False, 完全不改旧行为/回测引擎.
    if (not ok) and allow_min_lot:
        if hard_usd_cap is not None and risk > hard_usd_cap:
            ok = False
        else:
            ok = True
    return lots, risk, ok


# ════════════════════════════════════════════════════════════════
# P0-4: 智能数列系统（博森CCR核心技术）
# ════════════════════════════════════════════════════════════════
# [2026-08-21] 参考博森科技CCR机器人智能数列系统
# 6种经典数列 + 波动率自适应选择

import numpy as np

# 6种经典数列
NUMERICAL_PATTERNS = {
    "倍数数列": [1, 2, 4, 8, 16, 32, 64],       # 高波动用，快速递增
    "斐波那契数列": [1, 1, 2, 3, 5, 8, 13, 21], # 中等波动用，黄金比例
    "卢卡斯数列": [2, 1, 3, 4, 7, 11, 18, 29],  # 类斐波那契
    "平方数列": [1, 4, 9, 16, 25, 36, 49],      # 强趋势用
    "三倍数列": [1, 3, 9, 27, 81],               # 极端行情用
    "平推数列": [1, 1, 1, 1, 1, 1, 1],           # 低波动用，固定手数
}

def get_numerical_pattern(volatility: float, trend_strength: float = None) -> List[float]:
    """根据市场波动率和趋势强度选择最优数列。

    规则:
    - 高波动(>5%) → 倍数数列（快速递增，快速回本）
    - 低波动(<1%) → 平推数列（固定手数，稳定积累）
    - 中等波动 → 斐波那契数列（黄金比例，平衡风险）
    - 强趋势 → 卢卡斯数列（类斐波那契，增长更快）
    - 极端行情 → 三倍数列（快速递增，捕捉大行情）

    参数:
        volatility: 市场波动率（标准差）
        trend_strength: 趋势强度（0-1），可选

    返回:
        数列列表
    """
    if volatility > 0.05:
        # 高波动：使用倍数数列
        return NUMERICAL_PATTERNS["倍数数列"]
    elif volatility < 0.01:
        # 低波动：使用平推数列
        return NUMERICAL_PATTERNS["平推数列"]
    elif trend_strength is not None and trend_strength > 0.7:
        # 强趋势：使用卢卡斯数列
        return NUMERICAL_PATTERNS["卢卡斯数列"]
    elif volatility > 0.03:
        # 中高波动：使用斐波那契数列
        return NUMERICAL_PATTERNS["斐波那契数列"]
    else:
        # 默认：使用斐波那契数列
        return NUMERICAL_PATTERNS["斐波那契数列"]

def calculate_volume_sequence(base_volume: float, pattern_name: str = "斐波那契数列") -> List[float]:
    """根据数列名称和基础手数，计算递增手数序列。

    参数:
        base_volume: 基础手数（首单手数）
        pattern_name: 数列名称

    返回:
        手数序列列表
    """
    pattern = NUMERICAL_PATTERNS.get(pattern_name, NUMERICAL_PATTERNS["斐波那契数列"])
    return [base_volume * p for p in pattern]

def get_pattern_by_symbol(symbol: str, volatility: float = None) -> Tuple[str, List[float]]:
    """根据品种和波动率，获取最优数列名称和序列。

    参数:
        symbol: 品种代码
        volatility: 波动率（可选，None则自动计算）

    返回:
        (数列名称, 手数序列)
    """
    # 默认波动率
    if volatility is None:
        volatility = 0.02  # 默认中等波动

    # 根据波动率选择数列
    pattern_name = _select_pattern_by_volatility(volatility)

    # 计算手数序列
    base_volume = 0.01  # 默认基础手数
    sequence = calculate_volume_sequence(base_volume, pattern_name)

    return pattern_name, sequence

def _select_pattern_by_volatility(volatility: float) -> str:
    """根据波动率选择数列名称。"""
    if volatility > 0.05:
        return "倍数数列"
    elif volatility < 0.01:
        return "平推数列"
    elif volatility > 0.03:
        return "斐波那契数列"
    else:
        return "卢卡斯数列"


def to_symbol_config(symbol: str, cfg: Dict) -> Dict:
    """把一个宇宙品种转换成 SYMBOL_CONFIG 条目。

    SYMBOL_CONFIG 现有字段: name, pip, spread, volatility, pip_usd_per_lot
    """
    return {
        "name": cfg["name"],
        "pip": cfg["pip"],
        "spread": cfg["spread_price"],          # 价格单位的点差
        "volatility": cfg["pip_usd"] * cfg["lot"] * 0.5,  # 粗略波动代理, 仅占位
        "pip_usd_per_lot": cfg["pip_usd"],
        # 额外保留风控默认参数, 供回测/收集模式使用
        "_cls": cfg["cls"],
        "_lot": cfg["lot"],
        "_adx_min": cfg["adx_min"],
        "_sl_mult": cfg["sl_mult"],
        "_rr_mult": cfg["rr_mult"],
        "_max_daily": cfg["max_daily"],
        "_session": cfg["session"],
    }


def merge_into_symbol_config(base: Dict, symbols: Optional[List[str]] = None) -> Dict:
    """把宇宙合并进一个 SYMBOL_CONFIG 字典 (不修改入参)。"""
    merged = dict(base)
    keys = symbols if symbols is not None else list(UNIVERSE.keys())
    for s in keys:
        if s in UNIVERSE:
            merged[s] = to_symbol_config(s, UNIVERSE[s])
    return merged


def load_universe_into_ce(symbols: Optional[List[str]] = None,
                          ce_module=None) -> Dict:
    """把宇宙**就地**载入 continuous_evolution_v2 的 SYMBOL_CONFIG,
    使 market_scanner.scan_all 自动覆盖全品种。

    用法(在 run_trader.py 顶部或 __main__ 前调用):
        import symbol_universe as su
        su.DATA_COLLECTION_MODE = True
        su.load_universe_into_ce()
    """
    if ce_module is None:
        import continuous_evolution_v2 as ce_module
    merged = merge_into_symbol_config(ce_module.SYMBOL_CONFIG, symbols)
    ce_module.SYMBOL_CONFIG = merged
    return merged


# ════════════════════════════════════════════════════════════════
# 5. 筛选决策: 按盈利 + 样本量 => KEEP / COLLECT / CUT
# ════════════════════════════════════════════════════════════════
def classify_filter(stats: Dict, min_trades: int = COLLECT_MIN_TRADES) -> Tuple[str, str]:
    """根据统计给出筛选决策。

    Args:
        stats: {trades, win_rate, pnl, pf, expectancy, max_dd, ...}
        min_trades: 达到该样本量才允许 KEEP 决策
    Returns:
        (decision, reason)  decision ∈ {'KEEP','COLLECT','CUT','NO_DATA'}
    """
    if stats is None or stats.get("trades", 0) == 0:
        return "NO_DATA", "无成交 / 无数据"

    trades = stats["trades"]
    pf = stats.get("pf", 0.0) or 0.0
    pnl = stats.get("pnl", 0.0) or 0.0

    if pf < FILTER["cut_pf"]:
        return "CUT", f"PF={pf:.2f}<{FILTER['cut_pf']} 负期望, 直接剔除"
    if trades < min_trades:
        return "COLLECT", f"PF={pf:.2f} 但样本仅 {trades}<{min_trades}, 继续收集数据"
    if pf >= FILTER["keep_pf"] and pnl > 0:
        return "KEEP", f"PF={pf:.2f}≥{FILTER['keep_pf']} 且样本 {trades}≥{min_trades}, 保留"
    if pnl > 0:
        return "KEEP", f"净盈利 ${pnl:.0f} 且 PF={pf:.2f}≥1, 样本充足, 保留"
    return "COLLECT", f"样本充足但净盈亏 ${pnl:.0f} 偏弱, 继续观察"


def summary() -> str:
    """打印宇宙概览"""
    by_cls: Dict[str, int] = {}
    for s, c in UNIVERSE.items():
        by_cls[c["cls"]] = by_cls.get(c["cls"], 0) + 1
    lines = [f"★ 全品种宇宙 V2: 共 {len(UNIVERSE)} 个品种"]
    for cls, n in sorted(by_cls.items(), key=lambda x: -x[1]):
        lines.append(f"  {cls:<14s}: {n}")
    lines.append(f"  收集模式 DATA_COLLECTION_MODE = {DATA_COLLECTION_MODE}")
    lines.append(f"  样本门槛 COLLECT_MIN_TRADES = {COLLECT_MIN_TRADES}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
