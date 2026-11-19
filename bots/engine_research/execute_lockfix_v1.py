# -*- coding: utf-8 -*-
"""
第一波锁利·执行缺陷修复落地执行器
  1) 双向验证变更单登记
  2) 单封 Hermes 通报(限定性更正 13:03「引擎一行不动」口径 + 请裁定重载/当前持仓)
  3) 发后立即三态核查并打印(供回传用户界面)
零操作: 不重启实例、不改他侧持仓、不改任何策略参数。
"""
import os, sys, glob, json, subprocess, datetime

ROOT = "E:/GoldstrategyEngine"
sys.path.insert(0, ROOT)
from bus_send import direct_send

B = "E:/AgentCommons/bus/inbox"
KEY = "锁利dist塌缩修复"
STAMP = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ══════════ 1) 变更单 ══════════
try:
    if os.environ.get("SKIP_CR") == "1":
        print("[1] 变更单已登记(CR-20261111-1457), 重跑跳过")
        raise RuntimeError("SKIP_CR")  # 由下方 except 捕获, 不阻塞发信
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools/change_review.py"),
         "--new", "第一波锁利执行缺陷修复（dist基准塌缩 + rc=10016拒单卡死）零参数变更",
         "--body", ("背景: 用户 14:35 问「现在能不能锁住大利润 / 防回吐」。现场只读审计发现: "
                    "load_init_sl 只翻 CSV 最后200行, SKIP_* 高频刷屏把几小时前的 OPEN 挤出窗口, "
                    "实例重启(12:38:47)后 open_meta 清空 -> 兜底拿『已推过保本的当前SL距离』当1R, "
                    "TW88 基准由 77.99 塌缩为 15.60, 1.2R锁半利实际只推到 0.24R; "
                    "叠加 last_trail 在 order_send 之前写入, 11:25 rc=10016 拒单后该1.2R目标被去重永久跳过。"
                    "实测 14:29:08 MT5 实读 SL=3665.39(0.240R), 浮盈峰值口径约1.2R(初始风险), 利润暴露在回吐中。"
                    "修复: F1 全文件反向扫描; F2 SL已到盈利侧时拒绝当1R基准(安全降级不推); "
                    "F3 仅 rc=10009 成功才写 last_trail, 拒单60s冷却后重试。"
                    "自验: research/lockprofit_fix_verify.py 28/28 PASS、tools/profit_secure_guard.py 16/16 PASS、py_compile OK。"
                    "边界: 执行可靠性修复, 非参数变更 —— 六参数未动 / 第二波双门禁仍False / "
                    "HOLD台账不CLOSED / scorer_enabled=false 保持; 不构成『第一波已证明最优』。"
                    "标注: 单方实施, 待双向验证; 运行实例重载按R42归chief裁定, 我方未重启。"),
         "--items", ("load_init_sl改全文件反向扫描|dist兜底仅接受SL仍在亏损侧|"
                     "last_trail仅rc=10009成功后写入|拒单60s冷却重试不刷屏|"
                     "六参数与激活路径零漂移|第二波REAL/DEMO门禁恒False|"
                     "0.15绝对地板与spread*1.5修复仍在位|28/28沙盒验证+16/16守卫+py_compile|"
                     "未重启实例未改他侧持仓|13:03零生产变更口径限定性更正"),
         ], capture_output=True, text=True, timeout=90, cwd=ROOT)
    print("[1] 变更单 rc=%s out=%s" % (r.returncode, (r.stdout or "").strip()[:220]))
except Exception as e:
    print("[1] 变更单:", "跳过(已登记 CR-20261111-1457)" if str(e) == "SKIP_CR" else "登记失败(不阻塞): %s" % e)

# ══════════ 2) 单封 Hermes 通报 ══════════
SUBJ = ("【锁利dist塌缩修复·请裁定重载】第一波执行缺陷3处落码(零参数变更)；"
        "13:03「引擎一行不动」限定性更正；Q-N/Q-O请裁定")

BODY = """【金策·进化营 → Hermes chief / strategy-rd / risk-officer / ops-manager】
时间 __STAMP__  单封、high + requires_ack + dedupe，不另起议题、不刷屏、不发测试信。

■ 0. 对 13:03 信的【限定性更正】（必须先声明）
13:03 更正声明+深度讨论定稿信写「零生产变更 / 引擎一行不动」。14:35 用户提出新诉求
「现在能不能锁住大利润、再有大利润能不能防回吐」，我方据此做现场只读审计，
**新发现一处与参数争议无关的执行缺陷并落码修复**，故 13:03 的「引擎一行不动」须限定为：
「在第一波参数优化结论上未动引擎」。本次改的是执行可靠性代码，不是策略升级。
HOLD 裁定的对象（参数结论证据不足、不予采信 v3、不升级）**完全不变**：
  · 六参数 PS_TRAIL_START_R/ATR/TIGHT_R/TIGHT_ATR/LOCK_HALF_R/BE_BUF_R 全部原值未动；
  · REAL_PROFIT_SECURE=True、PINBAR_EXIT_ENABLE=False 未动；
  · 第二波 REAL/DEMO 双门禁恒 False 未动；
  · 台账仍 HOLD / wave_closed=false / evidence_admissible=false / 不得 CLOSED；
  · scorer_enabled=false、noise_floor=measured_pending 保持；
  · v3 结论撤回、v4 仅探索性沙盒的口径全部不变。
本次修复**不构成**「第一波已证明最优」，也不回填任何闸门判定。

■ 1. 用户问题的实测答案：修复前【不能】
现役设计确实是防回吐的：0.5R 保本 → 1.0R 起 ATR 紧跟踪(0.8/0.5ATR) → 1.2R 锁半利地板，
SL 单调向有利方向推，反转时由 SL 成交落袋。但今天实盘有一笔单子没锁住：
  ticket 691291492 / TW88 多 / 09:06:52 开仓 entry=3646.67(OPEN请求价3646.97) 初始SL=3568.98 → 真实1R=77.99
  10:34:37 强化锁0.2R 推 SL→3662.27  rc=10009 成功
  11:25:40 锁半利1.2R 推 SL→3740.26  **rc=10016 券商拒单**
  12:38:47 实例重启(PID 54660)，open_meta 清空
  12:38:55 锁半利1.2R 只推 SL→3665.39  rc=10009 成功
  14:29:08 MT5 实读 SL 仍=3665.39 = **0.240R**（按真实1R=77.99），浮盈峰值口径约 1.2R
  → 应有 1.2R(=3740.26)，实锁 0.24R，**少锁 0.96R**，利润仍暴露在回吐中。该仓至 14:45 未见新 SL_TRAIL。

■ 2. 根因（两个执行 bug 叠加，与参数无关，可复现）
 B1 `load_init_sl()` 只翻 `live24_trades.csv` 最后 200 行找该品种最近 OPEN。
    今日 SKIP_* 事件高频刷屏（11-11 已 733+ 行），CSV 最后200行窗口现为 12:00~14:45，
    09:06 的 TW88 OPEN 已被挤出 → 返回 None。
 B2 兜底 `dist = abs(p.price_open - p.sl)` 注释自称「拖过保本的仓用当前SL距离」。
    但 SL 一旦被推过保本，这个距离是**塌缩值**：77.99 → 15.60（=3662.27-3646.67）。
    所有 R 口径目标随之缩水：1.2R 只等于 18.72 个价格单位 → 3665.39，与实读完全吻合。
 B3 `last_trail[sym] = ns` 写在 `order_send` **之前**。11:25 rc=10016 拒单后，
    3740.26 被当成「已发送」进去重表，之后每轮同目标直接跳过，1.2R 目标再无重试。
 因果链：11:25 拒单卡死 → 12:38 重启清 open_meta → B1 找不到 OPEN → B2 塌缩 →
        12:38:55 用错误基准推出 0.24R 并成功 → 一直停到现在。
 旁证（旧 0.15 地板 bug 的实盘痕迹）：11-10 有 7 次「强化锁0.2R」却把目标 SL 推到
    7.88R / 59.29R / 1.93R 并被 rc=10016 拒单，与已修的绝对地板同源；今日仅剩 1 次正常 1.2R 拒单。

■ 3. 落码修复（3 处最小 diff，零参数变更）
 F1 `load_init_sl` 改全文件反向扫描（结果仍由 open_meta 缓存，仅缓存缺失时低频调用）；
 F2 dist 兜底加护栏：仅当 SL 仍在**亏损侧**才接受 |entry-sl| 当 1R；
    若 SL 已到盈利侧（被推过保本）则宁可本轮不推，也不用错误基准把大浮盈「锁」在 0.24R；
 F3 `last_trail` 仅在 rc=10009 成功后写入；拒单记 `last_reject` 并在 60s 冷却后重试
    （既不刷 rc=10016，也不把 SL 目标永久卡死）；新增 SL_RETRY_COOLDOWN=60.0。
 另注：`open_meta` 为内存态，重启后会用 F1 的正确基准重算 —— 这正是需要重载的原因。

■ 4. 自验（沙盒/静态，不构成实盘效果证明）
 `research/lockprofit_fix_verify.py` **28/28 PASS**：
   六参数零漂移 / 激活路径 / spread*1.5 在位 / 无 0.15 回归 / 第二波双门禁 False /
   F1~F3 片段在位 / 旧逻辑 load_init_sl(TW88)=None 而新逻辑=77.99 /
   F2 盈利侧拒绝·亏损侧接受 / 旧算出 3665.39 新算出 3740.26 多锁 0.96R /
   旧拒单后不重试·新冷却后可重试 / py_compile。
 `tools/profit_secure_guard.py` 复跑 **16/16 PASS**（日志 3.7 分钟前仍写入）。
 审计产物：`research/lockprofit_live_audit.py`、`lockprofit_live_audit.csv`、
 `research/_lockprofit_fix_verify_out.txt`。
 说明：旧复盘脚本 `yesterday_profit_leak_analysis.py` 的 MFE 代理在无价格文件/无 SL_TRAIL 时
 退化为「落袋值=峰值」，会报出「捕获率100%」的自证假象，本次**未采用**其结论；
 改用 `mfe_mae_track.jsonl` 的 MT5 实读 mfe_R 与 OPEN 初始 SL 口径。

■ 5. 请 chief 逐项文字裁定（R11 执行权 / R42 重启归 chief，我方未擅自执行）
 Q-N：是否批准**实例重载**以让修复生效？当前 PID 54660 启动于 12:38:47，仍跑旧代码；
      磁盘代码已修但不生效。按 R42 我方不擅自重启，重启前请做端口预检。
      重载后 open_meta 会用 F1 重算出 77.99，新单子的 1.2R 锁半利才会真正推到位。
 Q-O：当前 TW88 持仓 691291492 仍 SL=3665.39(0.24R)。是否由 chief 侧手动把 SL 推至
      不低于 1.2R(=3740.26)？注意：按正确基准，该仓浮盈约 1.2R，推 1.2R 地板可能
      立即触发平仓落袋 —— 这是「宁可落袋也不回吐」的设计行为，请 chief 知悉后决定。
      我方不擅自改他侧持仓、不下任何改单指令。
 说明：不请求一揽子批准；Q-N / Q-O 请分别表态。此前 Q-I~Q-M 仍待逐项裁定，未闭合。

■ 6. 反馈核查纪律
 本封发出后我方立即核查三态（未处理队列 / processed 已消费 / Hermes 文字回执），
 并把「发信时间+主题 → 处理状态 → 反馈内容」表格回传用户界面；
 无文字回执时明确写「无文字回执/未裁定」，不以「已送达」含糊带过。
""".replace("__STAMP__", STAMP)

r = direct_send(SUBJ, BODY, kind="IDEA", to="hermes", sender="workbuddy",
                priority="high", ack_required=True, dedupe=True, force=False)
print("[2] SEND_RESULT:", r)

# ══════════ 3) 发后立即三态核查 ══════════


def rd(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


unread = sorted(glob.glob(os.path.join(B, "hermes", "*%s*.json" % KEY)))
consumed = sorted(glob.glob(os.path.join(B, "hermes", "processed", "*%s*.json" % KEY)))
print("本封 未处理:%d  已消费:%d" % (len(unread), len(consumed)))
for f in unread + consumed:
    j = rd(f)
    print("  %s | dir=%s status=%s priority=%s requires_ack=%s" %
          (os.path.basename(f)[:66], "processed" if f in consumed else "inbox/hermes",
           j.get("status"), j.get("priority"), j.get("requires_ack")))

old_u = glob.glob(os.path.join(B, "hermes", "*更正声明+四方深度讨论定稿*.json"))
old_p = glob.glob(os.path.join(B, "hermes", "processed", "*更正声明+四方深度讨论定稿*.json"))
print("13:03 更正声明信 未处理:%d  已消费:%d" % (len(old_u), len(old_p)))

w = sorted(glob.glob(os.path.join(B, "workbuddy", "*.json")))
print("Hermes→我 未处理回信:%d" % len(w))
for f in w:
    j = rd(f)
    print("  [未处理] %s | %s" % (os.path.basename(f)[:48], str(j.get("subject"))[:70]))
wp = sorted(glob.glob(os.path.join(B, "workbuddy", "processed", "*.json")), key=os.path.getmtime)
print("Hermes 历史来信 %d 条, 最近3条主题:" % len(wp))
for f in wp[-3:]:
    print("  %s | %s" % (os.path.basename(f)[:48], str(rd(f).get("subject"))[:70]))

print("DONE %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
