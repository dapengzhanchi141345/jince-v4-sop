# -*- coding: utf-8 -*-
"""
第一波锁利「执行缺陷」修复 · 独立验证
不 import 引擎(会连MT5), 不连 MT5, 不改任何生产状态。纯静态断言 + 真实数据重放。

验证对象(2026-11-11 落码, 全部为执行可靠性修复, 零参数变更):
  F1 load_init_sl 全文件反向扫描 (原最后200行被 SKIP 刷屏挤出 OPEN)
  F2 dist 兜底护栏 (SL 已被推到盈利侧时拒绝拿它当 1R 基准)
  F3 last_trail 仅在 rc=10009 成功后记入 + 拒单 60s 冷却重试
  F4 六参数/激活路径/第二波门禁/0.15地板 无漂移
"""
import os, re, csv, py_compile, sys

ROOT = "E:/GoldstrategyEngine"
ENGINE = os.path.join(ROOT, "tools", "jince_live24.py")
CSVF = os.path.join(ROOT, "data", "live24_trades.csv")

results = []


def check(name, cond, detail=""):
    ok = bool(cond)
    results.append((name, ok))
    print("  [%s] %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


src = open(ENGINE, encoding="utf-8").read()

print("=" * 88)
print("  第一波锁利 · 执行缺陷修复验证  (只读, 不连 MT5)")
print("=" * 88)

# ---------- F4: 参数与门禁零漂移 ----------
print("\n[F4] 现役参数 / 门禁 / 历史修复 零漂移")
EXPECT_NUM = {
    "PS_TRAIL_START_R": 1.0, "PS_TRAIL_ATR": 0.8,
    "PS_TRAIL_TIGHT_R": 1.5, "PS_TRAIL_TIGHT_ATR": 0.5,
    "PS_LOCK_HALF_R": 1.2, "PS_BE_BUF_R": 0.2,
}
for k, v in EXPECT_NUM.items():
    m = re.search(r"^%s\s*=\s*([0-9.]+)" % k, src, re.M)
    check("常量 %s = %s" % (k, v), m and abs(float(m.group(1)) - v) < 1e-9,
          "实际=%s" % (m.group(1) if m else "缺失"))
check("REAL_PROFIT_SECURE = True", bool(re.search(r"^REAL_PROFIT_SECURE\s*=\s*True", src, re.M)))
check("PINBAR_EXIT_ENABLE = False", bool(re.search(r"^PINBAR_EXIT_ENABLE\s*=\s*False", src, re.M)))
check("锁利缓冲 spread*1.5 在位", "max(_be_buf, (tick.ask - tick.bid) * 1.5)" in src)
check("无 0.15 绝对地板回归", not bool(re.search(r"max\([^)]*,\s*0\.15\s*\)", src)))
tr = open(os.path.join(ROOT, "tools", "trend_rider_v1.py"), encoding="utf-8").read()
check("第二波 REAL 门禁恒 False", bool(re.search(r"^TREND_RIDER_REAL_ENABLE\s*=\s*False", tr, re.M)))
check("第二波 DEMO 门禁恒 False", bool(re.search(r"^TREND_RIDER_DEMO_ENABLE\s*=\s*False", tr, re.M)))

# ---------- 修复片段在位 ----------
print("\n[F1~F3] 修复片段静态在位")
check("F1 全文件反向扫描", "for row in reversed(rows):" in src and "rows[-200:]" not in src)
check("F2 SL亏损侧护栏", "_raw = (p.price_open - p.sl) * (1 if _is_buy else -1)" in src and "if _raw > 0:" in src)
check("F3 成功才写去重表", "if rc == 10009:" in src and "last_trail[sym] = ns" in src)
check("F3 拒单冷却重试", "SL_RETRY_COOLDOWN" in src and "last_reject[sym] = _now" in src)
check("F3 旧'发送前写last_trail'已移除", not bool(re.search(r"else:\s*\n\s*last_trail\[sym\] = ns\s*\n\s*try:", src)))

# ---------- 真实数据重放 ----------
print("\n[重放] TW88 ticket 691291492 (2026-11-11 09:06 开仓, 14:29 仍持仓)")
rows = list(csv.reader(open(CSVF, encoding="utf-8")))


def scan_old(sym):
    for row in reversed(rows[-200:]):
        if len(row) > 7 and row[1] == "OPEN" and row[2] == sym:
            d = abs(float(row[6]) - float(row[5]))
            return d if d > 0 else None
    return None


def scan_new(sym):
    for row in reversed(rows):
        if len(row) > 7 and row[1] == "OPEN" and row[2] == sym:
            d = abs(float(row[6]) - float(row[5]))
            return d if d > 0 else None
    return None


old_d, new_d = scan_old("TW88"), scan_new("TW88")
check("旧逻辑 load_init_sl(TW88) 返回 None(致塌缩)", old_d is None, "实际=%s" % old_d)
check("新逻辑恢复真实初始 1R = 77.99", new_d is not None and abs(new_d - 77.99) < 0.02,
      "实际=%.2f" % (new_d if new_d else -1))
print("       当前 CSV 最后200行窗口: %s ~ %s  (09:06 的 OPEN 已被挤出)" %
      (rows[-200][0], rows[-1][0]))


def fallback(entry, sl, is_buy):
    """F2: 仅当 SL 仍在亏损侧才接受 |entry-sl| 作为 1R"""
    raw = (entry - sl) * (1 if is_buy else -1)
    return abs(entry - sl) if raw > 0 else None


entry = 3646.67      # SL_TRAIL 行记录的 p.price_open(券商实际成交)
entry_open = 3646.97 # OPEN 行的请求开仓价, 差 0.30 = 成交滑点
sl_be = 3662.27     # 10:34 已推保本(盈利侧)
sl_init = 3568.98   # 09:06 初始SL(亏损侧)
check("F2 保本后SL(盈利侧) 拒绝当1R", fallback(entry, sl_be, True) is None)
check("F2 初始SL(亏损侧) 接受当1R", abs((fallback(entry_open, sl_init, True) or 0) - 77.99) < 0.02,
      "算出=%.2f (OPEN口径)" % (fallback(entry_open, sl_init, True) or 0))
check("滑点口径一致(OPEN 3646.97 vs 成交 3646.67)", abs(entry_open - entry - 0.30) < 1e-6)

# 锁利目标计算
bad_dist = abs(entry - sl_be)     # 15.60 塌缩基准
good_dist = new_d                 # 77.99 正确基准
bad_sl = entry + 1.2 * bad_dist
good_sl = entry + 1.2 * good_dist
check("旧: 1.2R锁半利实际只推到 3665.39", abs(bad_sl - 3665.39) < 0.05, "算出=%.2f" % bad_sl)
check("新: 1.2R锁半利应推到 3740.26", abs(good_sl - 3740.26) < 0.05, "算出=%.2f" % good_sl)
check("修复后多锁 %.2fR" % ((good_sl - bad_sl) / good_dist),
      (good_sl - bad_sl) > 0, "差=%.2f 价格单位 = %.2fR" % (good_sl - bad_sl, (good_sl - bad_sl) / good_dist))
print("       MT5 14:29:08 实读 SL=3665.39 = %.3fR (按真实1R=77.99)" % ((3665.39 - entry) / good_dist))

# last_trail 拒单重试行为
def old_behavior():
    last_trail = {}
    ns, rc = 3740.26, 10016
    last_trail["TW88"] = ns        # 原: 发送前就记
    # 下一轮: 相同目标 -> 去重跳过
    return not (last_trail.get("TW88") == ns)


def new_behavior():
    last_trail, last_reject = {}, {}
    ns, rc, now, cooldown = 3740.26, 10016, 1000.0, 60.0
    if rc == 10009:
        last_trail["TW88"] = ns
    else:
        last_reject["TW88"] = now
    t2 = now + 61
    return (last_trail.get("TW88") != ns) and (t2 - last_reject.get("TW88", 0) >= cooldown)


check("旧: rc=10016 拒单后该SL目标永久不重试", old_behavior() is False)
check("新: 拒单冷却 60s 后可重试", new_behavior() is True)

# ---------- 编译 ----------
print("\n[编译]")
try:
    py_compile.compile(ENGINE, doraise=True, cfile=os.path.join(ROOT, "research", "_lockfix_verify.pyc"))
    check("引擎 py_compile", True)
except Exception as e:
    check("引擎 py_compile", False, str(e))

npass = sum(1 for _, ok in results if ok)
print("\n" + "=" * 88)
print("  合计 %d/%d PASS   VERDICT: %s" % (npass, len(results), "修复验证通过" if npass == len(results) else "存在失败项"))
print("  说明: 本验证为静态+沙盒重放, 不构成实盘效果证明; 运行实例需重载后新逻辑才生效。")
print("=" * 88)
sys.exit(0 if npass == len(results) else 1)
