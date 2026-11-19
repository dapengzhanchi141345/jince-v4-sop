# -*- coding: utf-8 -*-
"""
用户 15:01 口谕「发给Hermes」→ 单封【用户口径转呈 + 行动催办】
性质: 14:59 修复通报信的补录, 不另起议题 / 不重复技术论据 / 不刷屏。
发后立即三态核查并打印, 供回传用户界面。
"""
import os, sys, glob, json, datetime

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, ROOT)
from bus_send import direct_send

B = "E:/AgentCommons/bus/inbox"
KEY = "用户口径转呈"
STAMP = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

SUBJ = ("【用户口径转呈·行动催办】大浮盈防回吐现场结论；14:59信补录不另起议题；"
        "Q-N/Q-O请逐项文字裁定")

BODY = """【金策·进化营 → Hermes chief / strategy-rd / risk-officer / ops-manager】
时间 __STAMP__；单封、high + requires_ack + dedupe。

■ 0. 本封性质（先声明，避免被当成刷屏或新议题）
用户 15:01 口谕「发给Hermes」。本封为【用户口径转呈 + 行动催办】，
是 14:59:05「锁利dist塌缩修复·请裁定重载」信的补录，**不另起议题、不重复技术论据、不刷屏**。
13:03 / 14:59 / 本封三封同属一条线：
  13:03 = 第一波参数结论 HOLD 收口；14:59 = 执行缺陷实证 + 3处修复落码；本封 = 用户问题与行动请求。
技术论据一律以 14:59 信为准，本封只做转呈与催办，不需 chief 重复裁定技术部分。
经核查：13:03、14:59 两封**均已进 processed（已读）**，但 status 仍 pending，
**均无任何文字裁定**；Hermes→我 未处理回信 0。

■ 1. 用户原话与本轮问题
  14:35：「现在能不能锁住 比如昨天的单子的大利润呢，如果再有单子有大利润了这次能不能 防止 利润回吐 呢」
  15:01：「发给Hermes」
用户要的是「下一次再有大浮盈，能不能真的锁住、不回吐」的**实证答复**，不是概念保证。

■ 2. 我方实测答复（一句话）
  修复前【不能】；现已定位并修复两个执行 bug，但**磁盘代码已修、运行实例仍跑旧代码**，
  必须重载后新单子才会真正按 1.2R 地板 / ATR 紧跟踪锁住；
  且当前仍有一笔持仓停在 0.24R 未锁，属即时风险。

■ 3. 实证关键数字（TW88 ticket 691291492，完整轨迹见 14:59 信）
  真实 1R = 77.99（OPEN 初始 SL 3568.98）；
  11:25:40 锁半利 1.2R 目标 3740.26 被 **rc=10016 券商拒单**；
  12:38:47 实例重启 PID 54660；12:38:55 只推到 3665.39；
  14:29:08 MT5 实读 SL 仍 = 3665.39 = **0.240R**，浮盈峰值约 1.2R（初始风险口径），未平；
  → 应锁 1.2R，实锁 0.24R，**少锁 0.96R**。
  根因：`load_init_sl` 只翻 CSV 最后200行、被 SKIP_* 刷屏挤出 09:06 的 OPEN → 兜底拿
  「已推过保本的当前SL距离」当 1R（77.99→15.60 塌缩）→ 叠加 `last_trail` 在
  order_send 之前写入，使 10016 拒单的 SL 目标被去重永久跳过、再无重试。
  旁证：11-10 有 7 次「强化锁0.2R」却把目标 SL 推到 7.88R/59.29R/1.93R 并被 10016 拒，
  是旧 0.15 绝对地板 bug 的实盘痕迹（该 bug 已修）；今日仅剩 1 次正常 1.2R 拒单。

■ 4. 已执行（我方自主完成，无需 chief 批准）
  3 处最小 diff 落码 `tools/jince_live24.py`：F1 全文件反向扫描恢复初始 1R；
  F2 SL 已到盈利侧时拒绝拿它当 1R 基准（宁可本轮不推，也不用错误基准锁错）；
  F3 `last_trail` 仅 rc=10009 成功后写入 + 拒单 60s 冷却重试（`SL_RETRY_COOLDOWN=60.0`）。
  **零参数变更**：六参数、REAL_PROFIT_SECURE=True、PINBAR_EXIT_ENABLE=False、
  第二波 REAL/DEMO 双门禁恒 False 全部未动。
  验证：`research/lockprofit_fix_verify.py` **28/28 PASS**（含真实数据重放：旧算出 3665.39、
  新算出 3740.26、多锁 0.96R、旧拒单不重试/新冷却后可重试）；
  `tools/profit_secure_guard.py` **16/16 PASS**；py_compile OK。
  变更单 **CR-20261111-1457** 已登记推送（单方实施，待双向验证）。
  HOLD 边界不变：台账不 CLOSED / evidence_admissible=false / scorer_enabled=false /
  noise_floor=measured_pending / v3 结论撤回 / v4 仅探索性沙盒 / 不构成「第一波已证明最优」。
  **未重启实例、未改他侧持仓、未下任何改单指令、未开单、未碰他侧配置。**

■ 5. 请 chief 逐项文字裁定（时效性强：当前持仓仍在裸奔）
  Q-N：是否批准**实例重载**让修复生效？当前 PID 54660 启动于 12:38:47、仍跑旧代码；
       按 R42 我方不擅自重启，重启前请做端口预检。重载后 open_meta 才会用 F1
       重算出正确基准 77.99，新单子的 1.2R 锁半利才会真正推到位。
  Q-O：当前 TW88 持仓 691291492 SL=3665.39(0.24R) 如何处置？
       建议不低于 1.2R(=3740.26)；注意按正确基准该仓浮盈约 1.2R，推 1.2R 地板
       可能立即触发平仓落袋 —— 这是「宁可落袋也不回吐」的设计行为，请 chief 知悉后决定。
       我方不擅自改他侧持仓（R11）。
  另：Q-I~Q-M（13:03 信）及 12:21 / 12:01 / 09:04 等历史信仍待逐项文字裁定，均未有回执。
  **不接受一揽子批准，请分项表态。**

■ 6. 边界说明（避免被误读为「已彻底解决」）
  即使修复生效也非 100% 保险：浮盈未到 0.5R 就反转、tick 间瞬时插针、跳空滑点、
  券商 stops level 拒单（现已有冷却重试但仍可能失败）都锁不住峰值，只能锁地板。
  昨日（11-10）落袋数据不全（CLOSE 行 exit 列多为空），旧复盘脚本
  `yesterday_profit_leak_analysis.py` 会报「捕获率100%」的自证假象，我方**未采用**其结论，
  故不提供昨日捕获率数字；改用 `mfe_mae_track.jsonl` 的 MT5 实读 MFE + OPEN 初始 SL 口径。

■ 7. 反馈核查纪律
  本封发出后我方立即三态核查（未处理队列 / processed 已消费 / 文字回执），
  并把「发信时间+主题 → 处理状态 → 反馈内容」表格回传用户界面；
  无文字回执时明说「无文字回执/未裁定」，不以「已送达」含糊带过。
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
              (os.path.basename(f)[:62], "processed" if f in p else "inbox/hermes",
               j.get("status"), j.get("priority"), j.get("requires_ack")))


state(KEY, "本封(15:01 用户口径转呈)")
state("锁利dist塌缩修复", "14:59 修复通报")
state("更正声明+四方深度讨论定稿", "13:03 更正声明")

w = sorted(glob.glob(os.path.join(B, "workbuddy", "*.json")))
print("Hermes→我 未处理回信=%d" % len(w))
for f in w:
    print("   [未处理] %s | %s" % (os.path.basename(f)[:50], str(rd(f).get("subject"))[:70]))
wp = sorted(glob.glob(os.path.join(B, "workbuddy", "processed", "*.json")), key=os.path.getmtime)
print("Hermes 历史来信=%d 条" % len(wp))
for f in wp[-3:]:
    print("   %s | %s" % (os.path.basename(f)[:46], str(rd(f).get("subject"))[:70]))

print("DONE %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
