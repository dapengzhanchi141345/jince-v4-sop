# -*- coding: utf-8 -*-
"""上海策略10天数据回测: 验证盯市四指标闸在深蹲段会触发、在盈利段不误杀。
逐M5根K线喂 mtm_gate.evaluate(), 模拟上海账户 (基净值假设 5000, 杠杆 1:500)。"""
import sys, json, datetime
sys.path.insert(0, r"E:\GoldstrategyEngine\multi_agent\risk")
import mtm_gate

BASE = 5000.0          # 上海账户基净值假设 (相对曲线起点=0)
LEV = 500.0            # 用户心法提及 1:500

trades = json.load(open(r"E:\workbuddy\tmp_shanghai_trades.json"))
eq = json.load(open(r"E:\workbuddy\shanghai_true_equity.json"))["eq"]
fl = json.load(open(r"E:\workbuddy\shanghai_true_equity.json"))["fl"]

# 名义敞口: 逐K线 O(n^2) 重建 (entry<=t<close 的活跃仓)
def dt(s): return datetime.datetime.strptime(s, "%Y.%m.%d %H:%M:%S")
xau = [t for t in trades if t["symbol"] == "XAUUSD"]
for t in xau:
    t["_e"] = dt(t["entry"]); t["_c"] = dt(t["close"])
# 活跃仓名义敞口函数: (label, [lots...]) — 用简化的逐K线活跃手数(两边都算)
labels = [a for a, _ in eq]
notional_series = []
for lab in labels:
    tdt = datetime.datetime.strptime(lab, "%Y-%m-%d %H:%M")
    active = [t for t in xau if t["_e"] <= tdt < t["_c"]]
    lots = sum(t["vol"] for t in active)
    px = max((t["price"] for t in active), default=0.0)
    notional_series.append(round(lots * 100 * px, 2))

state = {}
first_halt = None
first_warn = None
n_halt, n_warn, n_ok = 0, 0, 0
triggers = []
prev_mlvl = "OK"
for i, lab in enumerate(labels):
    equity = BASE + eq[i][1]
    fpnl = fl[i][1]
    gm = notional_series[i] / LEV if notional_series[i] > 0 else None
    tdt = datetime.datetime.strptime(lab, "%Y-%m-%d %H:%M")
    now_ts = tdt.timestamp()
    trig, lvl, scale, m = mtm_gate.evaluate(state, equity, fpnl, gm, now_ts=now_ts)
    if lvl == "HALT":
        n_halt += 1
        if first_halt is None:
            first_halt = lab
            triggers.append((lab, "HALT", m, scale))
    elif lvl == "WARN":
        n_warn += 1
        if first_warn is None:
            first_warn = lab
            triggers.append((lab, "WARN", m, scale))
    else:
        n_ok += 1

print("=== 上海回测 (基净值%s, 杠杆1:%s) 共%d根M5 ===" % (BASE, LEV, len(labels)))
print("HALT 根数: %d | WARN 根数: %d | OK 根数: %d" % (n_halt, n_warn, n_ok))
print("首次HALT: %s" % first_halt)
print("首次WARN: %s" % first_warn)
print()
print("=== 关键触发时刻 ===")
for lab, lvl, m, scale in triggers[:3]:
    print("%s [%s] scale=%.1f  G1=%.1f%% G2=%.1f%% G3=%.1fh G4=%.2fx" %
          (lab, lvl, scale, m["mtm_mdd_pct"], m["min_float_pct_of_equity"], m["g3_hours"], m["margin_level_x"]))

# 验证1: 深蹲段 (9/28 14:00-18:00) 必须有 HALT — 这是闸门的核心价值
deep = [x for x in triggers if "09-28" in x[0] and int(x[0][11:13]) in (14, 15, 16, 17, 18)]
print()
print("深蹲段(9/28 14-18h)触发记录数:", len(deep), "→", "通过" if deep else "未触发(需查)")

# 验证2: 期末盈利段 (10/7-10/8) 不应 HALT — 防误杀
late = [x for x in triggers if x[0] >= "2026-10-07"]
late_halt = [x for x in late if x[1] == "HALT"]
print("10/7-10/8 HALT记录:", len(late_halt), "→", "误杀!" if late_halt else "无误杀, 通过")

# 验证3: 金策当前账户现状 (无快照, 净值961.54, 空仓) → 应 OK 不干扰
state3 = {}
_, l3, s3, m3 = mtm_gate.evaluate(state3, 961.54, 0.0, None)
print("金策现状(净值961.54空仓): level=%s scale=%s → %s" % (l3, s3, "零干扰, 通过" if l3 == "OK" else "异常!"))
