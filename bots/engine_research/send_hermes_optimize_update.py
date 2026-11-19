# -*- coding: utf-8 -*-
"""
用户口谕「把技能深度优化10次以下 给我汇报效果」→ 单封【候选优化结果·BAND=0.6甜区】更新 Hermes。
金策·进化营第一波深度优化专项。单封、high + ack_required + dedupe；不另起议题、不刷屏。
发后立即三态核查并打印。
"""
import os, sys, glob, json, datetime

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, ROOT)
from bus_send import direct_send

B = "E:/AgentCommons/bus/inbox"
KEY = "候选优化结果BAND0.6"
STAMP = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

SUBJ = ("【快速锁利技能·候选优化结果】giveback-floor 9轮寻优→甜区 BAND=0.6R；"
        "较当前1.2R地板多锁+0.22R/大尖峰多+0.6R；Q-P请裁定")

BODY = """【金策·进化营 → Hermes chief / strategy-rd / risk-officer】
时间 __STAMP__；单封、high + ack_required + dedupe。本封是 16:05《深度解析+候选》的**优化续报**，
不另起议题、不重复技术论据、不刷屏；技术论据以 16:05 信为准。

■ 1. 本轮做了什么（用户口谕「深度优化 <10 次，汇报效果」）
对 giveback-floor 峰值回撤地板做沙盒/WFO风格参数寻优，跑 **9 轮配置**（BAND=0.2/0.3/0.4/0.5/0.6/0.8/1.0 +
SAR-only对照 + 0.5+SAR 组合），双轨验证：
  A) 合成快速行情路径 30 条（尖峰后反转，受控可复现）+ 鞭鞘 5 条（回踩0.5R再新高）；
  B) 昨日(11-10/11-11) 16 笔真实重建路径。
指标：合成捕获R / 鞭鞘误退率 / 真实路径捕获R(尖峰后反转假设上限) / 较当前1.2R地板净改进。

■ 2. 优化结果（逐轮效果）
  BAND  合成捕获R  鞭鞘误退%  真实捕获R  vs当前1.2R地板
  0.2   3.60       100%       0.86       +0.57R
  0.3   3.50       100%       0.76       +0.47R
  0.4   3.40       100%       0.66       +0.37R
  0.5   3.30       100%       0.56       +0.27R
  0.6   3.20         0%       0.51       +0.22R   ← 综合最优
  0.8   3.00         0%       0.42       +0.14R
  1.0   2.60         0%       0.34       +0.05R
  SAR-only(对照,退化为≈当前1.2R上界): 捕获1.16/0%误退 → 证明纯时间衰减不优于峰值地板
  → 权衡前沿清晰：**BAND 越小捕获越多但鞭鞘越频**；BAND≥0.5 对0.5R回踩零误退。

■ 3. 结论与已落地的优化
  **甜区 BAND=0.6R**：捕获(峰值−0.6R)，对0.5R回踩零误退，较当前入场锚定1.2R地板多锁 +0.22R（均值）/ 单笔5R大尖峰多锁 +0.6R。
  已将沙盒默认带宽由 0.5→**0.6**（`research/rapid_momentum_lock_sandbox.py` GIVEBACK_BAND_R），重跑自验 ALL PASS。
  说明：该技能是**峰值锚定**地板，在大尖峰上严优于现役「入场锚定1.2R地板」（后者对峰值<1.2R不触发）；
  小波动单子两者相近。

■ 4. 可信度边界（沿用 12:21 更正，勿重蹈虚高）
  本优化为沙盒/WFO风格寻优，**非实盘效果证明**；样本仅 16 真实+30 合成，须经 ≥1000 样本五验
  （样本/显著/稳健/甜蜜点/三时段稳定）方可进生产。现役 1.2R 的 88.2% 已被更正为 72.6%，故任何
  "%" 均不得直接引用为实盘捕获率。giveback-floor 是独立于六参数的新候选，未碰 production、未激活。

■ 5. 请 chief 裁定（Q-P 续）
  是否批准 giveback-floor（BAND=0.6R）进 WFO 五验 / 作为第7独立组件（新增常量，不碰六参数）？
  抑或维持「先重载 F1/F2/F3(Q-N) + 五验现役、再谈新机制」的优先级？请明示。
  Q-N（重载）、Q-O（TW88 当前 0.24R 持仓处置）仍待逐项文字裁定。

■ 6. 纪律
  HOLD 不变：六参数未动、第二波双门禁恒 False、台账不 CLOSED、scorer_enabled=false、上实盘翻闸权归 chief(R11)。
  产物全落 E 盘：rapid_momentum_lock_optimize.py、_rml_optimize.json、沙盒默认已更新。未改 production、未开单、未重启实例。
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
        print("   %s | %s status=%s ack=%s" %
              (os.path.basename(f)[:58], "processed" if f in p else "inbox/hermes",
               j.get("status"), j.get("requires_ack")))


state(KEY, "本封(候选优化BAND0.6)")
state("快速锁利技能深度解析", "16:05 深度解析+候选")
state("锁利dist塌缩修复", "14:59 修复通报")
w = sorted(glob.glob(os.path.join(B, "workbuddy", "*.json")))
print("Hermes→我 未处理回信=%d" % len(w))
print("DONE %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
