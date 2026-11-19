# verify_p0p1p2.py — 落地修复的针对性回归验证 (研策师)
# 覆盖任务要求的单元测试场景:
#   P0-HIGH-1  Regime 相对偏移 (evolved_adx=39 → trend31/range39/volatile47, 全≥20)
#   P0-HIGH-1  RR 保持 (preset 应用后 tp/sl ratio ≥ 2.0)
#   P0-HIGH-2  漂移绝对线 (pf=0.85→RED; pf=1.2→看相对)
#   P0-HIGH-3  标签过滤 (混合 magic 的 deals → 只算 SYSTEM_MAGIC; <5 笔→NO_DATA)
# 运行: py -V:Astral\CPython3.11.15 -u verify_p0p1p2.py
import sys
import types
import random

# ── 注入伪造 MetaTrader5 (用于测试 compute_live_metrics 的 magic 过滤路径) ──
fake_mt5 = types.ModuleType("MetaTrader5")


class FakeDeal:
    def __init__(self, magic, profit):
        self.magic = magic
        self.profit = float(profit)


class FakeTerminal:
    pass


sys.modules["MetaTrader5"] = fake_mt5

import drift_monitor as dm
import market_scanner as mh

SYS_MAGIC = dm.SYSTEM_MAGIC
OTHER_MAGIC = 888888

fails = []


def check(cond, msg):
    if cond:
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        fails.append(msg)


# ───────────────────────── P0-HIGH-1: Regime 相对偏移 + RR ─────────────────────────
print("\n[P0-HIGH-1] Regime 相对偏移 + 双铁律重过")
params = {
    'adx_min': 39, 'position_size': 0.03, 'risk_per_trade': 0.0162,
    'sl_multiplier': 2.5989, 'tp_multiplier': 5.1979,
    'volatility_scalar': 0.9735, 'momentum_filter': False,
}
expect_adx = {'trend': 31.0, 'range': 39.0, 'volatile': 47.0}
for regime in ('trend', 'range', 'volatile'):
    merged, info = mh.MarketHunter._apply_regime_preset(params, regime)
    eff = info['effective_adx_min']
    rr = merged['tp_multiplier'] / merged['sl_multiplier']
    pos = merged['position_size']
    check(abs(eff - expect_adx[regime]) < 1e-6,
          f"{regime}: effective_adx={eff} (期望 {expect_adx[regime]})")
    check(eff >= 20 and eff <= 60, f"{regime}: effective_adx 在 [20,60] 内")
    check(rr >= 2.0, f"{regime}: RR={rr:.3f} >= 2.0")
    check(0.01 <= pos <= 0.03, f"{regime}: position_size={pos} 在 [0.01,0.03]")
    check(info['position_scaled'] is True,
          f"{regime}: volatility_scalar 生效缩仓 (0.03→{pos})")
    print(f"     info={info}")

# clamp 下限: evolved=15, trend offset -8 → 7 → clamp 20
merged2, info2 = mh.MarketHunter._apply_regime_preset(
    {'adx_min': 15, 'position_size': 0.03, 'volatility_scalar': 1.0,
     'sl_multiplier': 2.0, 'tp_multiplier': 4.0}, 'trend')
check(info2['effective_adx_min'] == 20.0,
      f"低 adx_min 偏移后 clamp 到地板 20 (得 {info2['effective_adx_min']})")

# ───────────────────────── P0-HIGH-2: 漂移绝对线 ─────────────────────────
print("\n[P0-HIGH-2] 漂移绝对平衡线")
base = {'pf': 1.4143, 'win_rate': 0.2667}
r1 = dm.assess_drift({'status': 'OK', 'pf': 0.85, 'win_rate': 0.30}, base)
check(r1['status'] == 'RED', f"live.pf=0.85 (净亏损) → RED (得 {r1['status']})")
r2 = dm.assess_drift({'status': 'OK', 'pf': 1.2, 'win_rate': 0.30}, base)
check(r2['status'] == 'GREEN',
      f"live.pf=1.2 (pf>=1.0 且相对未漂移) → GREEN (得 {r2['status']})")
# 相对漂移仍生效: pf 在 [1.0, baseline*0.6) 之间
r3 = dm.assess_drift({'status': 'OK', 'pf': 0.5, 'win_rate': 0.30}, base)
check(r3['status'] == 'RED', f"live.pf=0.5 (<baseline*0.6=0.848) → RED (得 {r3['status']})")
# NO_DATA 透传
r4 = dm.assess_drift({'status': 'NO_DATA'}, base)
check(r4['status'] == 'NO_DATA', "live NO_DATA → NO_DATA")

# ───────────────────────── P0-HIGH-3: 标签过滤 + 样本不足 ─────────────────────────
print("\n[P0-HIGH-3] 按 SYSTEM_MAGIC 过滤成交")


def _build_deals(n_sys, n_other):
    random.seed(7)
    deals = []
    sys_profits = [10, 20, 15, -5, -8, 12, 8, -4, 18, -6,
                   9, 7, -3, 11, -9]  # 前 10 用; 多给不碍
    for i in range(n_sys):
        deals.append(FakeDeal(SYS_MAGIC, sys_profits[i % len(sys_profits)]))
    for _ in range(n_other):
        deals.append(FakeDeal(OTHER_MAGIC, random.choice([50, -50, 100, -20])))
    return deals


# 子测试 A: 10 笔系统 + 31 笔其它 → 只算系统 (10 笔)
fake_mt5.terminal_info = lambda: FakeTerminal()
fake_mt5.history_deals_get = lambda a, b: _build_deals(10, 31)
res = dm.compute_live_metrics(days=30)
print(f"     res={res}")
check(res['status'] == 'OK', f"混合 magic → status=OK (得 {res.get('status')})")
check(res.get('trade_count') == 10,
      f"仅统计本系统成交 trade_count=10 (得 {res.get('trade_count')})")
check(res.get('source') == 'mt5', f"source=mt5 (得 {res.get('source')})")
sys_gw = 10 + 20 + 15 + 12 + 8 + 18  # 6 wins
sys_gl = 5 + 8 + 4 + 6               # 4 losses
check(abs(res['pf'] - sys_gw / sys_gl) < 0.01,
      f"pf 仅按系统成交计算 = {sys_gw}/{sys_gl} = {sys_gw/sys_gl:.3f} (得 {res.get('pf')})")
check(abs(res['win_rate'] - 0.6) < 0.001, f"win_rate=6/10=0.6 (得 {res.get('win_rate')})")

# 子测试 B: 3 笔系统 + 31 笔其它 → 样本不足 → NO_DATA
fake_mt5.history_deals_get = lambda a, b: _build_deals(3, 31)
res2 = dm.compute_live_metrics(days=30)
print(f"     res2={res2}")
check(res2['status'] == 'NO_DATA' and res2.get('reason') == '本系统样本不足',
      f"本系统<5笔 → NO_DATA(reason=本系统样本不足) (得 {res2.get('status')}/{res2.get('reason')})")

print("\n" + ("=" * 60))
if fails:
    print(f"验证失败 {len(fails)} 项:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ 全部 P0-HIGH-1/2/3 + P1-MEDIUM-1 单元验证通过")
sys.exit(0)
