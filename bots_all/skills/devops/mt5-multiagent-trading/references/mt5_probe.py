import MetaTrader5 as mt5, json, datetime, sys


def probe(symbols):
    """One-command MT5 live read: account + positions + 4-timeframe K-lines (last 6 bars) as one JSON.
    Verified on demo 60137964 @ TradeMaxGlobal-Demo, ~30s wall-clock incl. initialize+shutdown.
    Use this instead of hand-typing a probe each session; it pre-solves the 3 recurring pitfalls below.

    Usage:
        python3.11 mt5_probe.py                  # default watchlist
        python3.11 mt5_probe.py XAUUSD EURUSD    # explicit symbols

    PITFALLS BAKED IN:
      1. copy_rates_from_pos returns a numpy structured array. `arr or []` raises
         "truth value of an array with more than one element is ambiguous".
         Guard: `if arr is not None and len(arr)` then `list(arr)`.
      2. Do NOT reference mt5.PERIOD_* or mt5.TIMEFRAME_* constants — on the uv-global
         cpython binding here, neither attribute family exists (AttributeError). Use raw codes.
      3. Interpreter: here `python3.11` (uv-global cpython) can `import MetaTrader5`;
         bare `python`/`python3.14` raise ModuleNotFoundError. Detect a working interpreter first.
      4. Index symbols (DE30 etc.) may fail symbol_select (name not mapped on this account) ->
         returns {"err":"select_fail"}. Verify real symbol names via mt5.symbols_total() if needed.
    """
    symbols = sys.argv[1:] or ["XAUUSD", "EURUSD", "EURTRY", "GBPUSD"]
    ok = mt5.initialize()
    if not ok:
        print(json.dumps({"error": "mt5.initialize failed", "detail": mt5.last_error()}, ensure_ascii=False))
        return
    out = {"connect": True, "account": None, "positions": [], "market": {}}
    acc = mt5.account_info()
    if acc:
        out["account"] = {"login": acc.login, "server": acc.server,
                          "balance": round(acc.balance, 2), "equity": round(acc.equity, 2),
                          "trade_allowed": acc.trade_allowed}
    pos = mt5.positions_get()
    out["positions"] = [{"ticket": p.ticket, "symbol": p.symbol,
                         "type": str(p.type).split(".")[-1], "volume": p.volume,
                         "price_open": p.price_open, "sl": p.sl, "tp": p.tp}
                        for p in list(pos or [])]
    # Raw period codes: M15=15, H1=16385, H4=16388, D1=16408 (binding-version-independent).
    P = {"M15": 15, "H1": 16385, "H4": 16388, "D1": 16408}

    def ts(x, day):
        d = datetime.datetime.utcfromtimestamp(int(x["time"]))
        return d.strftime("%m-%d") if day else d.strftime("%m-%d %H:%M")

    for s in symbols:
        if not mt5.symbol_select(s, True):
            out["market"][s] = {"err": "select_fail"}
            continue
        d = {}
        tick = mt5.symbol_info_tick(s)
        if tick:
            d["bid"] = float(tick.bid)
            d["ask"] = float(tick.ask)
        for name, code in P.items():
            arr = mt5.copy_rates_from_pos(s, code, 0, 6)
            d[name] = ([ (ts(x, name == "D1"), float(x["close"])) for x in list(arr) ]
                       if arr is not None and len(arr) else [])
        out["market"][s] = d
    print(json.dumps(out, ensure_ascii=False))
    mt5.shutdown()


probe([])
