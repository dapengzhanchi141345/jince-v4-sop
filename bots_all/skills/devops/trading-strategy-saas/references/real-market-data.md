# Real market-data layer (true multi-timeframe K-lines, not fabricated)

The sellable trading panel must show **real** platform K-lines (MT5/MT4), never a
random-walk "demo" line the code generates on the fly. A fabricated candle set is a
hard user red line for this customer — if the terminal is offline AND there is no
real snapshot on disk, return an empty set with a clear "no data / terminal not
connected" note instead of synthesizing OHLC. The degradation rule: terminal up →
real pull; terminal down → replay the last real snapshot that was persisted; neither
→ honest empty, labeled.

## Source: MT5 Python API (read-only)

- `MetaTrader5.copy_rates_from_pos(symbol, timeframe, 0, count)` → OHLC bars for real
  data. Attach with `mt5.initialize(path_to_terminal64.exe)`; the SDK is **not
  thread-safe** — put one global lock around every call (the terminal is shared with
  the engine, do not disturb its trades; every call here is read-only, never
  order_send).
- Live quote: `symbol_info_tick(sym)` → bid/ask/last. Account: `account_info()`. Open
  positions: `positions_get(sym=None)`. Deal history: `history_deals_get(start, end)`.
- `get_provider()` factory pattern: try `MT5Provider`, fall back to
  `DryRunProvider(snapshot_path)` when the package is missing or attach fails. Keep a
  short in-memory TTL (e.g. 30s) so you don't re-`initialize` on every request.

## Timeframe constants — DO NOT copy from the docs; probe your SDK

The `TIMEFRAME_*` constant values shipped in a given MetaTrader5 package build can
**differ from the published reference values**. In one build the intraday values were
the small integers (M5=1, M15=2, M30=4) but every large timeframe was offset by a
high bit flag: H1=16385, H4=16388, D1=16408, W1=32769, MN1=49153 (i.e. 0x4000 base
plus the period id) — NOT 16/32/8/16/32 as a naive reading of the reference table
implies. Passing the wrong constant returns `None` with `last_error` = "Terminal:
Invalid params", so your loop silently gets 0 bars for H1 and above while M5/M15/M30
look fine — a very easy half-working trap. **Rule: read the constants from the
installed package itself** (`mt5.TIMEFRAME_H1`, `mt5.TIMEFRAME_D1`, … or print
`vars(mt5)`), never hardcode from memory; if the package is absent, print
`_TF_CONST` from a known-good build and confirm against a live probe before trusting
it.

## SDK shape gotchas (probe, don't guess — field layouts change between builds)

- `copy_rates_from_pos` returns a **numpy structured array**, not a list of dicts.
  Iterate rows and index by field name (`row["close"], row["tick_volume"],
  row["time"]`); `row.get(...)` fails (`numpy.void` object has no attribute `get`).
- `history_deals_get` may return **namedtuples** in some builds and dicts in others.
  Normalize defensively: `d._asdict() if hasattr(d, "_asdict") else d`, then index.
- `TerminalInfo` / `AccountInfo` in the installed build may **lack** `server_time`
  / `time` attributes even though the reference lists them. List the real fields with
  `dir(obj)` before using one; for a start/end window on deal history, fall back to
  `int(time.time())` (30-day lookback is plenty) rather than a server-clock field that
  may not exist.
- `account_info()` has no `server_time`; if you need server time, use
  `terminal_info()` — and even that is absent in some builds, so gate it behind
  `hasattr`.

## Data contract for the front-end (Lightweight Charts v5)

- The chart engine is TradingView **Lightweight Charts** (Apache-2.0; the only
  purpose-built candlestick engine, ~12 KB gzip). Vendor the standalone production
  build into the web `vendor/` dir so the panel works offline.
- Bar rows must be `{time, open, high, low, close, volume}`. Intraday timeframes use
  UNIX seconds; daily-and-above (D1/W1/MN1) use a `YYYY-MM-DD` string to avoid a
  timezone shift on the daily axis. A backend `timeframes` field that emits the right
  format per TF keeps the chart correct for all 8 periods.
- `series.update(bar)` for the forming last candle on each live poll, `series.setData`
  on TF/symbol switch — do not re-create the chart every tick.

## Acceptance / verification that must pass before calling it "real data"

- Start the real server and hit `/market/status` → `source=mt5`, `realtime=true`.
- Hit `/market/candles?symbol=XAUUSD&tf=<each of 8 TFS>&count=N` → **all 8** return
  non-empty bars with `source=mt5`; a silent 0-bars on the large TFs means the
  timeframe constants are wrong (see above), not "no data".
- Multi-symbol spot check (a second/third symbol incl. a non-FX one) returns bars.
- Quote returns a real bid/ask spread (> 0 when terminal live), account returns the
  real login/balance/equity, deals returns real history rows.
- Only then is the panel "real-data"; a pass that shows fabricated or 0 bars is not
  a pass.
