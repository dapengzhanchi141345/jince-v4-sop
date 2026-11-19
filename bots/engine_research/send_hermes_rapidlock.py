# -*- coding: utf-8 -*-
"""
用户口谕「深度解析昨天的单子+进一步提升技能+验证好再汇报」→ 单封【深度解析+技能候选】通报 Hermes。
金策·进化营第一波深度优化专项。单封、high + ack_required + dedupe；不另起议题、不刷屏。
发后立即三态核查并打印，供回传用户界面。
"""
import os, sys, glob, json, datetime

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, ROOT)
from bus_send import direct_send

B = "E:/AgentCommons/bus/inbox"
KEY = "快速锁利技能深度解析"
STAMP = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

SUBJ = ("【快速锁利技能·深度解析+候选】昨日大浮盈泄漏根因 + giveback-floor 技能重放验证 "
        "+ 88.2%%→72.6%% 更正通告；Q-N 催办 / Q-P 新候选裁定")

BODY = """【金策·进化营 → Hermes chief / strategy-rd / risk-officer / ops-manager】
时间 __STAMP__；单封、high + ack_required + dedupe。

■ 0. 本封性质（先声明，避免被当成刷屏或新议题）
用户口谕「深度解析昨天的单子、进一步提升锁利技能、验证好再汇报」。本封是 13:03/14:59/15:03
同一条线的**延续**：技术修复(14:59)已落码待重载；本封聚焦「昨日大浮盈为什么没吃到」的可信复盘
+ 一个**已沙盒重放验证的锁利技能候选**，供 chief 裁定是否进 WFO 五验。
本封不碰生产、不改参数、不激活任何新逻辑、不下单；HOLD 边界与本线前信一致。

■ 1. 昨日(11-10/11-11)大浮盈没吃到的根因 —— 用 OPEN 行真实 1R 重建全部持仓，结论：主因不是「锁利技能不够紧」，是三重执行缺陷 + 旧版弱锁
  - 11-10 当天 PROFIT_SECURE 仍 OFF → 跑旧版弱锁（锁半利仅 0.5R 地板，非 1.2R）。
  - dist 塌缩 bug（load_init_sl 只翻 CSV 末200行被刷屏挤出 OPEN → 兜底拿已推保本的 SL 距离当 1R，77.99→15.60）。
  - 券商 rc=10016 拒单后 last_trail 在 order_send 之前写入 → 该 SL 目标被去重永久卡死、再不重试。
  实证泄漏表（真实 1R 来自各 ticket 的 OPEN 行 entry/sl）：
    TW88(691291492)  浮盈5.62R 实锁0.24R → 漏5.38R（dist塌缩+11:25拒单卡死）
    AUDUSD(689441650) 浮盈1.33R 3×10016全拒 → 漏1.33R（完全裸奔）
    USDZAR(689441747) 浮盈1.03R 3×10016全拒 → 漏1.03R（完全裸奔）
    AUDCNH(686665059) 浮盈0.50R 1×拒 → 漏0.50R
    US2000/NAS100/XAGUSD/LTCUSD 弱锁0.5R地板 → 各漏0.44~0.75R
    GER40/NETH25 ~3.2R@MAXHOLD 18h 硬平截断右尾（峰值回落部分未锁）
  → 立即止损动作仍是：批准重载让 F1/F2/F3 生效（即 Q-N），重载后 1.2R 地板/ATR 紧跟踪才会真正推到位。

■ 2. 快速行情锁利技能候选（沙盒已重放验证）
  针对痛点「方向做对后的快速大涨/大跌，行情走得很快、一犹豫就反转、利润回吐严重」，在现役
  PROFIT_SECURE 之外新增一个**纯 SL 目标**组件（与现役 max() 棘轮合并，只往紧推、不碰六参数）：
  【giveback-floor 峰值回撤地板】SL = 持仓峰值价 − BAND*1R（BAND 为独立于六参数的新候选常量）。
  用 11-10/11-11 真实路径重放（`research/rapid_momentum_lock_sandbox.py`，自验 ALL PASS）：
    假设尖峰后立刻反转（用户最关心的场景）：
      band=0.3R → 应锁多 8.15R（较实际 +182%）
      band=0.5R → 应锁多 6.58R（较实际 +147%）
      band=0.8R → 应锁多 5.34R（较实际 +119%）
    TW88 一笔：5.62R 峰值 → 地板应锁 ~5.1R（实际仅 0.24R），单笔多锁≈5R。

■ 3. 可信度更正（重要，请覆盖旧口径，避免重蹈 08:48 覆辙）
  早 08:48 信「网格+WFO激活real侧 lh1.2 反转捕获88.2%」已被 12:21《第一波定稿·请回执》自我更正：
  **真实 72.6%（B1+B3 虚高）**；修正 harness 重测 n=9546 **净均值R=−0.0131（为负）**，负系
  「每根 H1 突破都入场」沙盒噪声。故：
  (a) 现役 1.2R 地板建立在虚高数字上、且修正后净 R 为负，又被 dist bug 破坏 —— 不可称「已证明最优」；
  (b) 本封第 2 节的「+119%~182%」是**尖峰后反转假设下的上限重放**，绝非已验证实盘捕获率；
  (c) 引擎 `jince_live24.py:223` 注释仍写「1.2R 反转捕获率 88.2% 最高」与更正矛盾，应予修正，
      且任何新机制须走 WFO 五验（样本≥1000 / 显著性 / 稳健 / 甜蜜点 / 三时段稳定）方可进生产。

■ 4. 请 chief 逐项文字裁定（不接受一揽子）
  Q-N：是否批准**实例重载**让 F1/F2/F3 生效？PID 54660(12:38:47启动)仍跑旧码；按 R42 我方不擅自重启，
       重启前请做端口预检。重载是 bug 修复、零参数变更、安全。
  Q-P：giveback-floor 候选是否批准进 WFO 五验 / 作为第 7 个独立组件（新增常量 BAND，不碰六参数）？
       抑或 chief 认为当前优先级仍应「先重载+五验现役、再谈新机制」？请明示路径。
  Q-O（重申）：当前 TW88 持仓 691291492 SL=3665.39(0.24R) 如何处置？推 1.2R 地板(=3740.26)可能立即
       触发平仓落袋，是「宁可落袋不回吐」的设计行为，请 chief 知悉后决定；我方不擅自改他侧持仓(R11)。

■ 5. 边界与纪律
  HOLD 不变：六参数未动、第二波 REAL/DEMO 双门禁恒 False、台账不 CLOSED、scorer_enabled=false、
  不构成「第一波已证明最优」、上实盘翻闸权归 chief(R11)。
  giveback-floor 仅为候选，未经五验不进生产；本轮所有产物落 E 盘、未改 production、未开单、未重启实例。
  三态核查纪律：本封发后我方立即核查并把「发信→处理状态→反馈内容」表格回传用户界面；无文字回执
  时明说「无文字回执/未裁定」，不以「已送达」含糊带过。
""".replace("__STAMP__", STAMP)

r = direct_send(SUBJ, BODY, kind="IDEA", to="hermes", sender="workbuddy",
                priority="high", ack_required=True, dedupe=True, force=False)
print("[SEND_RESULT]", r)


def rd(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def state(kw, label):
    u = sorted(glob.glob(os.path.join(B, "hermes", "*%s*.json" % kw)))
    p = sorted(glob.glob(os.path.join(B, "hermes", "processed", "*%s*.json" % kw)))
    print("%s: 未处理=%d 已消费=%d" % (label, len(u), len(p)))
    for f in u + p:
        j = rd(f)
        print("   %s | %s status=%s priority=%s ack=%s" %
              (os.path.basename(f)[:60], "processed" if f in p else "inbox/hermes",
               j.get("status"), j.get("priority"), j.get("requires_ack")))


state(KEY, "本封(快速锁利技能深度解析)")
state("锁利dist塌缩修复", "14:59 修复通报")
state("用户口径转呈", "15:03 行动催办")
state("更正声明", "13:03 更正声明")

w = sorted(glob.glob(os.path.join(B, "workbuddy", "*.json")))
print("Hermes→我 未处理回信=%d" % len(w))
wp = sorted(glob.glob(os.path.join(B, "workbuddy", "processed", "*.json")), key=os.path.getmtime)
print("Hermes 历史来信(processed)=%d 条，最近3:" % len(wp))
for f in wp[-3:]:
    print("   %s | %s" % (os.path.basename(f)[:46], str(rd(f).get("subject"))[:66]))

print("DONE %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
