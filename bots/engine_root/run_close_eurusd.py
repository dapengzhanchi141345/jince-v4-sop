# run_close_eurusd.py — 金策宗师团 · 平仓执行器 (仅平 EURUSD 逆风多单)
#
# 决策依据 (CIO 2026-07-07):
#   行情报告判定 EURUSD NEAR SELL (-1.0, D1+H1 向下),
#   现价 1.14334 已逼近关键破位位 1.14324, SL 1.14141 不远。
#   持仓 396383555 @1.1439 为逆风多单, 与信号反向 → 平仓止损、释放风险。
#   GBPUSD 多单 396383560 顺势 (STRONG BUY) → 保留, 等 SL/TP 自动出场。
#
# 铁律: 走 审度司 audit_close (放行) → 金刚卫 close_position (IOC) → 度支司对账。
# 本脚本严禁开启任何新仓。

import json
import MetaTrader5 as mt5
import guardian_executor as ge

# ══ 只平这一张逆风多单 ══
TICKET = 396383555  # EURUSD BUY 0.03

# 真实下单总闸 + 自动确认 (用户已授权模拟实盘)
ge.LIVE_TRADING_ENABLED = True

ex = ge.GuardianExecutor(
    auto_confirm=True,
    max_risk_per_trade=0.01,
    max_daily_risk=0.03,
)
ex.connect()

print("=" * 60)
print("[审度司+金刚卫] 平仓执行:", TICKET)
res = ex.audit_and_close(TICKET)
print(json.dumps(res, indent=2, ensure_ascii=False, default=str))

# ── 度支司 对账确认 ──
print("\n" + "=" * 60)
print("[度支司] 平仓后持仓对账:")
if mt5.positions_get() is None:
    print("  (positions_get 返回 None)")
remaining = mt5.positions_get() or []
if not remaining:
    print("  无持仓 (EURUSD 逆风多单已平)")
else:
    for p in remaining:
        typ = "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL"
        print(f"  仍持有: {p.symbol} {typ} {p.volume} @ {p.price_open:.5f} "
              f"SL {p.sl:.5f} TP {p.tp:.5f} profit {p.profit:.2f}")

# 当日成交记录核对
deals = mt5.history_deals_get(ticket=TICKET) or []
print(f"\n[度支司] ticket {TICKET} 成交记录 {len(deals)} 笔:")
for d in deals:
    print(f"  deal {d.ticket} {d.symbol} {d.type} {d.volume} @ {d.price:.5f} "
          f"profit {d.profit:.2f}")
print("=" * 60)
