# Trading Strategy SaaS — Architecture & Component Reference

## Four-layer architecture

```
① Strategy layer (the bot)         your engine/EA publishes order events
        │  signal broadcast over WebSocket (one pub, many subs)
② Signal hub (multi-tenant)        signal bus + tenant isolation + per-customer risk gate
        │                           (this is the heart; hand-roll it)
③ Web client (the customer UX)     strategy marketplace (net-value curve / win-rate / MDD /
        │                           sharpe) → subscribe (full / %-of-equity / fixed-lot) →
        │                           own risk gates → live positions → P&L statement
        ▼
④ Execution layer                   server-side unified execution (1 MT5 API session per
                                     customer)  AND/OR  client-terminal ZMQ mirror
```

Plus a **white-label admin portal** (per asset-manager: branding/theme JSON, customer list,
subscription overview, audit-log viewer, strategy on/off switch) and a **billing engine**
(subscription / performance-fee-with-HWM / platform-tier + a 402 subscription gate that
downgrades an expired customer's WS to read-only and blocks new copies).

## API contract shape (define up front so the frontend task doesn't block)

- `GET /strategies?tenant={slug}` → list: id,name,net_value,win_rate,max_drawdown,sharpe,active
- `GET /strategies/{id}/stats` → net-value curve points + last-50 fills + open positions
- `POST /accounts` → bind a customer MT5 account (login,server,password|token; store + dry-run
  validity check first; real terminal management lives in the execution service)
- `POST /subscriptions` / `DELETE /subscriptions/{id}` → copy_mode=full|percent|fixed_lot,
  percent, fixed_lot, per-customer gates max_drawdown_pct / daily_loss_pct / spread_max_pts
- `WS /ws/stream?customer={id}` → push `signal`/`position`/`equity` JSON with `ts`
- `GET /customers/{id}/report` → P&L statement (positions/fills/risk metrics)
- Auth: JWT for the web client; a separate machine `api_key` tier (`Bearer` or `X-API-Key`,
  scoped per tenant/customer, per-minute rate limit, every call logged for billing) for
  open `/open/v1` endpoints a third party or the asset manager's own system pulls from.

## Multi-node execution routing (asset-manager delivery at scale)

The MT5 SDK can only `order_send` to the ONE account its terminal is logged in as, so one central terminal serves one account. To host many customer accounts, add a node layer (each node = a Windows VPS running the exec-node loop, terminals logged in as the customer accounts it serves):

- **Tables:** `ExecNode` (name, `mt5_login` [indexed — the routing key], credential [stored, NEVER echoed; expose `has_credential` bool only], base_url, status registered|online|offline, last_seen) + `ExecQueue` (node_name, customer_id, payload_json, `client_order_id` [unique — the idempotency key], status pending|claimed|sent|filled|dead, attempts, last_error).
- **Routing decision in `execute_plan`:** terminal attach == customer's bound account → local direct send; ELSE a registered node owns that bound login → `enqueue_order` into that node's queue (fill status `routed`, the idempotency key still dedupes replays); ELSE → honest dry-run degrade with the reason on the run log.
- **Node agent loop (`exec_node_runner`):** heartbeat → `node_pick_orders` (atomic claim, prevents two nodes racing the same order) → `order_send` on its own terminal → `node_report` (ok → sent/filled; fail → attempts+1, ≥3 → dead). Admin console `replay-dead` resets dead back to pending.
- **Admin console auth (platform tier, distinct from customer JWT):** one `X-Admin-Token` env var; the validator is a PURE function of the token — no FastAPI param default, one caller (the `admin_auth` dependency), never also called in endpoint bodies (see the double-fire pitfall in SKILL.md). Unset env → 403 fail-safe (channel closed); wrong → 401. Endpoints: create/update tenant (auto-provision white-label + default `PlanPricing`), get/put tenant pricing, list/add/delete symbol aliases (tenant-scoped row overrides the global row), register/delete exec-nodes (delete refused while that node's queue has pending orders), inspect node queue, replay-dead. Node-facing `/exec-node/{name}/heartbeat|pick|report` take NO admin token — the node name is the key and registering the node in the console is what authorizes it. Mount a new admin router via `app.include_router(admin_router)`, verified on a fresh TestClient, never `routes.extend`.

## Execution-path decision table

| Path | When | Trade-off |
|---|---|---|
| Server-side unified execution (main) | customer wants web-only UX | platform must host one MT5 session per customer account; the differentiator to sell |
| Client-terminal ZMQ mirror (fallback) | customer won't open a server account / terminal does the copy | ships as pre-built MQL; lower friction to start, weaker UX |

## Verified open-source MT4/MT5 components to vendor (as-of last research pass)

> Re-screen before trusting — star/README can be stale or a name collision.

| Repo | License | Use |
|---|---|---|
| `jiowcl/MQL-CopyTrade` (~200★) | MIT | MT4/MT5 client copy-trade: publisher (strategy side) → subscribers; %-/fixed-lot, multi-publisher, symbol mapping, margin check. **Only needs the investor read-only password — a compliance plus.** |
| `dingmaotu/mql-zmq` (~700★) | Apache-2.0 | MQL↔ZeroMQ binding with precompiled MT4(32-bit)/MT5(64-bit) DLLs. The foundation MQL-CopyTrade sits on. |
| `tristannottelman/mt5-copy-trading` | — | Pure-Python two-account MT5 mirror via `pip install MetaTrader5`; steal its retcode/slippage handling (10009/10008/10010 success, 10018 market-closed skip). |
| `mikha-dev/mt4-websockets-server` | — | MT4 WebSocket server so a web page can read live terminal data; optional admin-portal channel. |

Hand-roll (no good open-source; this is the value you sell): web client, white-label admin
portal, multi-tenant signal hub, billing engine. Commercial white-label PAMMs to benchmark
UX/feature-set against (closed-source, ~€799/mo): B2COPY, Tramaxis PAMM Backoffice.

## Billing model

Subscription (per customer/period) + performance share on net profit with a **high-water
mark** (no fee on recovered losses — test with the canonical 4-segment curve below) +
platform fee by AUM tier. Expired subscription → 402 business code: WS degrades to
read-only net-value, copy endpoints reject; configurable grace period.

### HWM performance-fee formula

Per-customer state: `hwm` (high-water mark, base 100) and `base_equity` (period baseline),
with a configurable reset cycle (`rolling30` / `week_end` / `month_end`). For each equity
point `E`:
1. If the reset cycle is due: pull `base_equity` back to `hwm`, restart the period.
2. `period_pnl = E - base_equity`; `eligible = max(period_pnl - max(hwm - base_equity, 0), 0)`.
3. New high (`eligible > 0`): `fee = eligible × rate`; `new_hwm = E - fee`; set
   `hwm = new_hwm`, `base_equity = new_hwm`, reset the period (fee on a new high is
   charged exactly once).
4. Drawdown (`eligible == 0`): charge nothing — recovering a loss is not new profit.

Canonical acceptance curve: 4 segments rise-fall-rise-fall, proving
fall-does-not-rebill + new-high-charges-once + post-new-high reset. (Pitfall from this
class: a "legacy overload" that `raise`s at the top of the new-signature function is
silent dead code — the real implementation below it never runs; remove it, don't
leave it "for the old signature".)

### Six fee structures

Performance (HWM) / management (AUM × annual% ÷ 12 × months) / platform (AUM tiered)
/ subscription (per period) / entry (one-time at activation) / exit (cancel penalty,
prorated by remaining days) — each independently switchable, configurable per tenant.

### Settlement engine (the asset-manager selling point)

Per period: compute → debit customer → credit strategy provider → credit platform
clip (AUM-tiered) → all legs into an append-only ledger. `debit_total == credit_total`
is asserted BEFORE posting; an unbalanced batch is refused. Recalculable: any
historical period re-derives from its ledger entries, so tampering surfaces on recompute.

## Execution-engine reliability (the part that actually loses money if done badly)

- **Idempotency key:** `JINCE-{strategy}-{leg|all}-{signal_ts_ms}-{8hex}` (sha256 of
  the tag, first 8 hex). Re-pushed signal / executor restart / network retry → same key
  → short-circuit against the fills/order table; a copy trade places exactly once.
  **The idempotency ledger must survive a process restart** — keep an in-memory `_seen`
  set only as a fast path, but source-of-truth in a DB/receipt table (`ClientOrder`) so
  an executor that crashes mid-submit and restarts re-reads the ledger and does NOT
  re-place an already-filled order ("orphan double-order" / Rataash scenario). Also
  write the key into the MT5 `order comment` (`JINCE|{client_order_id}`) so a live
  terminal can be re-scanned for the prefix as a third dedupe layer (MT5 has no
  native `client_order_id`; the comment is the industry channel).
- **Lot sizing, 4 modes:** `full` = signal lots; `percent` = signal_lots ×
  (customer_equity / strategy_equity) × (percent / 100) — two-factor scaling, so the
  expected value in tests must fold both factors in; `fixed_lot` = constant;
  `multiplier` = signal_lots × multiplier (CopySync: 1.0 = full, 2.5 = 2.5×). After
  computing the raw lots, **normalize to the broker's lot grid**: floor to the
  `MODE_VOLUMESTEP`, then clamp to `MODE_MINLOT` (forceTinyTrades: too small → raise to
  min) and `MODE_MAXLOT`. Skipping the vol-step floor is the classic cause of a
  `10014 INVALID_VOLUME` server rejection. Floor to 0.01 with 2 decimals (micro-account
  friendly).
- **Symbol mapping precedence:** hand/tenant alias → global alias → auto prefix/suffix
  probe against the customer broker's live symbol list (`m.`, `i`, `-m`, `.m`, `_m`
  variants) → exact-name match. All tiers miss = reject with reason, never guess.
  (Production: add an existence gate — a probed symbol only counts if the broker reports
  it has a real base currency AND trading is enabled, so you don't adopt a phantom
  variant — and write auto-probed aliases back to the alias table for audit.)
- **Per-account hard ceilings before submission, three-state on breach**
  (MetaCopier 2026 skip-vs-clamp semantics, configurable per customer): max lots /
  max position-% of equity / max open positions. On breach, `on_breach` = `reject`
  (default: refuse, record an audited copy-filter rejection) | `skip` (silently drop,
  no trace, "rather not copy than blow up the account") | `clamp` (shrink the lot to the
  allowed ceiling and still send). The clamp path returns the allowed lot so the caller
  substitutes it before submission.
- **Reliability:** per-symbol ordered queue (one serial consumer per
  `(customer, symbol)` so OPEN→MODIFY→CLOSE stays strictly FIFO; a CLOSE landing before
  its OPEN is a "ghost position"), exponential backoff **with jitter** using the
  Tradecast formula `delay = min(base · 2^attempt + U(0, jitter_ms/1000), max_backoff)`
  (attempt starts at 1, not 0), and a dead-letter table for retry-exhausted orders
  (human-replayable, never silently dropped; replay must keep the original idempotency
  key so an already-filled replay short-circuits to `skipped_dup`). Only *transient*
  failures (requote/no-money/terminal-busy/network timeout) go to backoff; *hard*
  rejections (INVALID_VOLUME / INVALID_STOPS / symbol-mapping miss) fail fast with no
  retry — do not hammer a known-bad order 5×.

## Web client + white-label + compliance depth

- Marketplace with switchable multi-board ranking (MDD / Sharpe / win-rate).
- Strategy detail: offline-vendored net-value chart, leg-matrix with single-leg
  subscribe, last-N fills, open positions.
- Account center: positions, unrealized P&L, fee breakdown, CSV export.
- Live page: WS signal blink + equity tick; 402 → "copy paused" banner + renew button.
- White-label: per-tenant theme JSON (logo / primary color / domain / brand name /
  risk-disclosure text) restyles the whole site; one asset manager = one domain +
  one brand; theme export/import.
- Compliance gate before register/subscribe: 7-class risk disclosure (market /
  slippage / leverage / liquidity / tech failure / strategy change / backtest
  limitation); "guaranteed returns" wording is a marketing red line; consent is
  recorded as document version + device + IP + timestamp, not a boolean.

