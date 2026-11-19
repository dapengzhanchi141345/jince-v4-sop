# -*- coding: utf-8 -*-
"""
account_calibrate.py — 用真实模拟账号 (60043976 / TradeMaxGlobal-Demo) 校准全宇宙合约规格

替换此前的手工估算 pip_usd，直接取 MT5 真实数据：
  - trade_tick_value / trade_tick_size  -> 每 pip 真实美元值 (1 lot)
  - volume_min / volume_step / volume_max
  - order_calc_margin  -> 开最小手需要多少保证金
  - spread (真实点差)
  - trade_mode (是否可交易)

产出: data/account_specs.json
"""
import json, os, sys
import MetaTrader5 as mt5

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import symbol_universe as su

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUT = os.path.join(DATA_DIR, "account_specs.json")

# 券商符号别名（universe 名 -> 券商名）
ALIAS = {
    "SPX500": ["US500", "SPX500", "USA500"],
    "DE30":   ["GER40", "DE40", "DE30", "GER30"],
    "JP225":  ["JPN225", "JP225"],
    "CHN50":  ["CHI50", "CHN50", "CN50"],
    "US10Y":  ["US10YT", "US10Y"],
    "UK100":  ["UK100", "GBR100"],
    "FRA40":  ["FRA40", "FR40"],
    "SWI20":  ["SWI20", "CH20"],
    "HK50":   ["HK50", "HKG33"],
    "AUS200": ["AUS200", "AU200"],
    "US2000": ["US2000", "USA2000"],
    "NAS100": ["NAS100", "USTEC", "US100"],
    "US30":   ["US30", "USA30", "DJ30"],
    "ESP35":  ["ESP35", "SPA35"],
    "ITA40":  ["ITA40", "IT40"],
    "NED25":  ["NED25", "NL25"],
    "EU50":   ["EU50", "STOXX50", "EUSTX50"],
    "XAUUSD": ["XAUUSD", "GOLD"],
    "XAGUSD": ["XAGUSD", "SILVER"],
    "WTI":    ["WTI", "USOIL", "XTIUSD", "CL"],
    "BRENT":  ["BRENT", "UKOIL", "XBRUSD"],
    "NGAS":   ["NGAS", "XNGUSD", "NATGAS"],
    "BTCUSD": ["BTCUSD", "BTCUSD.b"],
}


def resolve(u, alls):
    """在券商符号表中解析 universe 符号名"""
    cands = ALIAS.get(u, []) + [u]
    for c in cands:
        for suf in ("", ".c", ".r", ".b", ".pro", "m"):
            n = c + suf
            if n in alls:
                return n
    return None


def main():
    if not mt5.initialize():
        print("MT5 initialize FAILED:", mt5.last_error())
        return 1

    ai = mt5.account_info()
    if ai is None:
        print("account_info FAILED")
        mt5.shutdown()
        return 1

    print(f"=== ACCOUNT {ai.login} @ {ai.server} ===")
    print(f"balance={ai.balance} {ai.currency}  leverage=1:{ai.leverage}  "
          f"mode={'DEMO' if ai.trade_mode == 0 else 'REAL'}")
    if ai.currency != "USD":
        print(f"!! WARNING: account currency is {ai.currency}, tick_value is in account currency")

    alls = {s.name for s in mt5.symbols_get()}
    print(f"broker symbols: {len(alls)}")

    specs = {}
    unresolved = []

    for u, cfg in su.UNIVERSE.items():
        bs = resolve(u, alls)
        if bs is None:
            unresolved.append(u)
            specs[u] = {"broker_symbol": None, "status": "NOT_OFFERED"}
            continue

        # 必须先 select 才能拿到完整信息
        mt5.symbol_select(bs, True)
        si = mt5.symbol_info(bs)
        if si is None:
            specs[u] = {"broker_symbol": bs, "status": "NO_INFO"}
            continue

        pip = cfg.get("pip", 0.0001)
        tick_size = si.trade_tick_size or si.point
        tick_val = si.trade_tick_value or 0.0

        # 每 pip 真实美元值 (1 lot)
        pip_usd_real = (tick_val / tick_size * pip) if tick_size else 0.0

        # 开最小手所需保证金
        tick = mt5.symbol_info_tick(bs)
        price = (tick.ask if tick and tick.ask else si.ask) or 0.0
        margin_min = None
        if price > 0:
            m = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, bs, si.volume_min, price)
            margin_min = round(m, 2) if m is not None else None

        # 真实点差 (价格单位 & pip 数)
        spread_price = (si.spread or 0) * si.point
        spread_pips = spread_price / pip if pip else 0.0

        specs[u] = {
            "broker_symbol": bs,
            "status": "OK",
            "digits": si.digits,
            "point": si.point,
            "tick_size": tick_size,
            "tick_value": tick_val,
            "contract_size": si.trade_contract_size,
            "pip_cfg": pip,
            "pip_usd_real": round(pip_usd_real, 6),
            "pip_usd_old": cfg.get("pip_usd"),
            "volume_min": si.volume_min,
            "volume_step": si.volume_step,
            "volume_max": si.volume_max,
            "margin_min_lot": margin_min,
            "spread_points": si.spread,
            "spread_price": round(spread_price, 8),
            "spread_pips": round(spread_pips, 3),
            "trade_mode": si.trade_mode,  # 0=disabled 4=full
            "tradable": si.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL,
            "price": price,
            "cls": cfg.get("cls"),
            "name": cfg.get("name"),
        }

    mt5.shutdown()

    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {
        "account": {
            "login": ai.login, "server": ai.server, "currency": ai.currency,
            "balance": ai.balance, "equity": ai.equity, "leverage": ai.leverage,
            "demo": ai.trade_mode == 0,
        },
        "specs": specs,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    ok = [s for s, v in specs.items() if v.get("status") == "OK"]
    tradable = [s for s, v in specs.items() if v.get("tradable")]
    print(f"\nresolved OK : {len(ok)} / {len(su.UNIVERSE)}")
    print(f"tradable    : {len(tradable)}")
    print(f"NOT_OFFERED : {len(unresolved)}")

    # pip_usd 修正对比 (差异最大的)
    print("\n=== pip_usd 真实值 vs 旧估算 (差异 TOP 25) ===")
    rows = []
    for s, v in specs.items():
        if v.get("status") != "OK":
            continue
        o, n = v.get("pip_usd_old") or 0, v.get("pip_usd_real") or 0
        if o > 0 and n > 0:
            rows.append((abs(n / o - 1), s, o, n, v.get("cls")))
    rows.sort(reverse=True)
    for d, s, o, n, c in rows[:25]:
        print(f"{s:<10} {c:<12} {o:>10.4f} -> {n:>10.4f}  (x{n/o:>7.3f})")

    # 账户能否开最小手
    print(f"\n=== 保证金检查 (账户余额 ${ai.balance}) ===")
    bad = [(s, v) for s, v in specs.items()
           if v.get("tradable") and v.get("margin_min_lot") and v["margin_min_lot"] > ai.balance * 0.5]
    if bad:
        print(f"最小手保证金 > 余额50% 的品种 ({len(bad)} 个, 单笔就占半个账户):")
        for s, v in sorted(bad, key=lambda x: -x[1]["margin_min_lot"]):
            print(f"  {s:<10} minlot={v['volume_min']:<6} margin=${v['margin_min_lot']:<10} cls={v['cls']}")
    else:
        print("所有可交易品种最小手保证金均 < 余额50% (1:1000 杠杆充裕)")

    print(f"\nsaved -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
