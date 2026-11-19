# Engine editing safety (when touching the GoldstrategyEngine tree or wiring live-order gates)

Read this BEFORE editing any engine code or before wiring a new safety/ops control. Covers three traps that cost a full session each.

## 1. Two near-identical engine trees — edit the LIVE one
- There are two trees with working-looking files: `E:/GoldstrategyEngine/` (live, scheduled, active) and `E:/资料/GoldstrategyEngine/` (stale snapshot / deprecated copy). Editing the 资料 copy "succeeds" (files exist, `py_compile` passes) but has **zero effect** on the running system and burns the whole session.
- **Prove which tree is live before editing:** the live tree's `data/auto_cycle.log` / `data/discussion_log.jsonl` has a recent mtime and is the target of the running cron/watchdog. Touch the most-recently-written, scheduler-targeted tree. Verify liveness by mtime + scheduler target, **not** by file existence (both trees have the files).
- A stale copy may already carry local fixes the live tree lacks (soft-restart, magic-based bookkeeping), so "the 资料 copy is fixed" ≠ "the live system is fixed." Cross-check the live tree independently before concluding anything is resolved.
- Whatever you change in the live tree: back up the touched files first and keep it minimal + reversible; the tree is a running production system, not a scratch sandbox.

## 2. Live order-entry is ONE convergence point; gate opens, never gate closes
- Many scripts can call `order_send`, but the single LIVE open-position convergence point is `guardian_executor.GuardianExecutor._send_order`, held DRY-RUN by `LIVE_TRADING_ENABLED=False` + `auto_confirm=False`. Put any "wrong-account / wrong-live-server" safety gate there — the one place every real open order passes — and make it fail-closed (unknown or unreadable account → reject; never fail open).
- The close path `close_position` must **NOT** carry the open-only gate: closing releases risk, so blocking it (e.g. on an account mismatch) would leave positions naked. Gate the opens, never the closes.
- Reliable account/server sanity anchors: `account_info().server` keyword check and `account_info().login == config.login`. `trade_mode` is **not** a reliable DEMO anchor on this broker — its demo accounts also return 0, so record it but do not fail-closed on it.
- Before wiring a gate, confirm the current live switch state is DRY-RUN (both `LIVE_TRADING_ENABLED` and `auto_confirm` False) so the gate is inert until a human explicitly enables live — that keeps the change zero-risk to the running account.

## 3. Single-instance lock for double-spawned cron/watchdog
- A 15-min no_agent cron can get scheduled twice and run two overlapping instances → duplicate probes, duplicate gateway/terminal relaunches, duplicate risk-gate refresh (the same "double-scheduling churn" family that stacks same-price pending orders). Symptom: two processes of the same script started seconds apart.
- Guard the entrypoint with an OS-native exclusive file lock: open the lock file, `f.seek(0)`, write pid, then `msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)` (non-blocking). On lock failure another instance holds it → log a line and `sys.exit(0)` silently (no_agent: quiet exit = no message, which is correct). The OS releases the handle lock on both normal exit AND crash, so no zombie lock blocks the next scheduled round.
- Verify by starting two instances: the second must be the one that exits. Do a syntax check after editing the scheduled script.
