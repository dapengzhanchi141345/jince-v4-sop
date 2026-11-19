# -*- coding: utf-8 -*-
"""
第一波 · 四方深度讨论后 HOLD 方案执行器 v1 (2026-11-11 12:22 用户口谕)
=====================================================================
"跟Hermes深度讨论后立即执行最优方案" —— 讨论已由四方(沟通官/架构师/育种官/审查官)
多轮完成; 本脚本执行其一致裁定的**唯一放行范围 = 零生产变更 HOLD**。

严格按审查官一票否决边界 + 三条精度订正:
  · 从未"放行最优方案", 通过的只是「维持现状/不升级」; 措辞一律用 HOLD 裁定边界
  · v3 结论已撤回不予采信; v4 仅同 pipeline 局部自证, 严格 PC-0 仍 pending
  · σ_noise 标 exploratory_unverified, 不回填 noise_floor, |Δ|>2σ 不作闸门判定
  · 撤回只限「越界定性」; B1~B4 修正事实与 88.2%→72.6% 更正继续有效
  · 架构层 (iv) "无法确认" 单列结构风险; 回执 ≠ 确认
  · 台账不得记 CLOSED; 规格版本=4 / 证据进展=0
  · 范式保持可修订/非唯一/可证伪, 禁止固化
全部落 E 盘; 不改 jince_live24.py、不连 MT5、不开实单、不碰他侧文件。
"""
import os, sys, json, glob, time, subprocess
sys.path.insert(0, "E:/GoldstrategyEngine")
from bus_send import direct_send

ROOT = "E:/GoldstrategyEngine"
JOURNAL = os.path.join(ROOT, "data/continuous_evolution/evo_decision_journal.jsonl")
WITHDRAW = os.path.join(ROOT, "data/continuous_evolution/evo_withdrawal_register.jsonl")
LOCK = os.path.join(ROOT, "data/continuous_evolution/firstwave_scope_lock.json")
EXPECT = os.path.join(ROOT, "data/ps_expected.json")
TS = time.strftime("%Y-%m-%d %H:%M:%S")


def append(path, rows):
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ══════════ 1) HOLD 决策台账 (append-only) ══════════
# 团队铁律: 成员结论为准、主理人不代写专业产出 -> 逐字采用档案官交付的 8 行原文,
# 不落主理人草稿(草稿中 live_change_approved 被误表述为"另设字段/两套状态机")。
JOURNAL_LINES = os.path.join(ROOT, "research/evo_hold_journal_lines.jsonl")
with open(JOURNAL_LINES, encoding="utf-8") as f:
    member_rows = [json.loads(ln) for ln in f if ln.strip()]
assert len(member_rows) == 8, "档案官台账应为8行, 实得%d" % len(member_rows)
assert all(r.get("status", {}).get("closed") is False for r in member_rows), "台账含 closed=true, 拒绝落盘"
assert all(r.get("decision") == "HOLD" for r in member_rows), "台账含非HOLD决议, 拒绝落盘"
append(JOURNAL, member_rows)
print("[1] HOLD 台账 append %d 行(档案官原文逐字) -> %s" % (len(member_rows), os.path.basename(JOURNAL)))

_UNUSED_DRAFT = [
    {
        "ts": TS, "writer": "evo-archivist", "event": "DECISION_HOLD",
        "decision": "按审查官 HOLD 裁定边界收口: 维持现役 LIVE 六参数 sr1.0/ta0.8/tr1.5/tta0.50/lh1.2/bb0.20, tools/jince_live24.py 一行不动; 第二波 Track B REAL/DEMO 双门禁恒 False 冻结不解除。审查官从未放行任何最优方案, 通过的仅是「维持现状/不升级」。",
        "status": {"resolution": "HOLD", "closed": False, "evidence_admissible": False,
                   "pipeline_selfcheck": "pending(严格PC-0双跑一致性)",
                   "noise_floor": "measured_pending",
                   "scorer": "pending_chief_approval",
                   "live_change_approved": False,
                   "state_note": "本代不使用 live_change_approved 字段; 状态由 REAL/DEMO 双门禁恒False + HOLD 承载"},
        "review": {"reviewer": "evo-reviewer", "verdict": "HOLD 通过 / 一票否决持续有效",
                   "veto_objects": ["范式固化为唯一合法", "第一波已收敛结案宣称", "任何落码改实盘参数(本轮无此动作)"],
                   "seven_checks": "确定性/最小样本/正期望/过拟合屏(由PASS升级FAIL)/胜率合理/成本感知/结构文档",
                   "three_requirements": {"falsifiability_and_PC0": "pending",
                                          "true_noise_floor": "pending",
                                          "hermes_chief_written_verdict": "pending"},
                   "note": "收口=停止讨论并冻结状态, 不等于证据链闭合或解除否决"},
        "verify": {"samples": 9546, "symbols": 8, "engine_changed": False,
                   "trackb_real": False, "trackb_demo": False,
                   "guard": "tools/profit_secure_guard.py 16/16 PASS (全部为源码静态比对/py_compile/文件mtime, 无一项依赖v3 pipeline)",
                   "redlines": ["未连MT5", "未开实单", "未碰他侧文件/配置", "未重启引擎",
                                "R11 exp_r翻闸与开单权归chief", "R42重启端口预检",
                                "第62节暂缓全品种提速", "感恩节窗口11-12~11-27流动性降档"]},
        "spec": {"evidence_progress": 0, "spec_versions": 4,
                 "version_chain": ["A", "B", "C", "D"],
                 "audit": "规格迭代≠证据进展: 版A/B/C/D四版全是规格与撤回、零实测回填; 显式记录防止版本数被误当完成度"},
        "refs": ["research/profit_secure_deep_v2.py", "research/_ps_deep_v2_out.txt",
                 "research/profit_secure_deep_v3.py", "research/_ps_deep_v3_out.txt",
                 "research/profit_secure_falsify_v4.py", "research/_falsify_v4_out.txt",
                 "tools/profit_secure_guard.py", "data/ps_expected.json"]
    },
    {
        "ts": TS, "writer": "evo-archivist", "event": "EVIDENCE_WITHDRAW",
        "subject": "v3 约束帕累托结论 34组全Δ=0 / 帕累托最优即现役",
        "withdrawn": True, "admissible": False,
        "reason": "三个约束阈值(捕获>=72.6%/回吐<=11.7%/胜率>=60.2%)全部锚定现役实测指纹, 等于把答案写进筛选条件; 全0系约束设计使然之恒等式投影, 不可证伪、与数据无关; ④过拟合屏由PASS升级FAIL。",
        "empirical_confirmation": "v4 C段约束松弛12档: 捕获阈值72.6%→70%即出现非现役最优Δ=+0.001770, →60%时Δ=+0.003220; D段99组中H1单独剔除77组、H2/H3各0组, 证实单一约束独裁可行域。",
        "disposition": "v3 降级为探索性沙盒存档, 标注 sandbox_only=true / no_live_extrapolation=true; 不触发任何 _score/排名/前沿/gate 重算; 严禁写「v3证明现役最优」。",
        "withdrawn_claims_scope": "仅撤回越界定性: 定稿 / 正面证明最优 / 伪改进已确认 / 深度优化完成 / 88.2%→72.6%的『确凿』定性。",
        "facts_retained": ["B1空单方向 / B2 tight_r阈值 / B3 同bar自指 / B4 基线标签 四项 harness 修正事实继续有效",
                           "旧报反转捕获率 88.2% 已作废, 修正后 72.6% 这一 B3 自指bug修正事实保留",
                           "12:21 第一波定稿信中的技术数据仍具历史测量价值, 仅撤回其定性措辞"]
    },
    {
        "ts": TS, "writer": "evo-archivist", "event": "SANDBOX_EVIDENCE_V4",
        "tags": {"sandbox_only": True, "no_live_extrapolation": True,
                 "live_change_approved": False, "scorer_enabled": False,
                 "status": "exploratory_unverified"},
        "A_positive_control": {"delta": "+0.004396", "per_trade_diff": "4788/9546 (50.16%)",
                               "sample_hash_diff": True,
                               "scope": "仅证明同一 pipeline 内无恒值短路, 属局部自证; 按 J1/N3 严格PC-0双跑一致性检验仍 pending, 不采信为证据有效性闸门"},
        "B_identifiability": "6维度全部ACTIVE、无不可辨识维度; 但 start_r 1.0→1.2 与 trail_atr 邻域 diff≈0, 现役邻域钝化",
        "C_constraint_relax": "12档; 72.6%→70% 前沿即移动(Δ=+0.001770), →60% 时 Δ=+0.003220",
        "D_attribution": "H1 捕获阈值单独剔除 77/99 组; H2/H3 各 0 组",
        "E_noise_exploratory": {"sigma_noise": "+0.003015", "CI95": "[-0.001260, +0.010585]",
                                "label": "exploratory_unverified",
                                "compliance": "口径/计算式/样本哈希/分层/n_block/active_n/冻结后α_B/M_family 独立复核签字均未交, 不可复核; 不得回填 noise_floor (保持 measured_pending); 不得把 |Δ|>2σ 写成闸门 PASS/FAIL 判定 (R-β 一律 pending)"},
        "F_payoff": "盈亏比0.6233 / 平衡所需胜率0.6160 / 实际0.6074 → 解释净R为何微负",
        "H_jackknife": "8/8 正向(描述性, 不作闸门)",
        "G_five_gates": "全部输出逐项原始数值, 但按 R-β 一律标 pending, 不判 PASS/FAIL",
        "admissibility": "不作为证据进展回填; 不计入规格完成度; 不构成任何实盘外推力"
    },
    {
        "ts": TS, "writer": "evo-archivist", "event": "STRUCTURAL_RISK_ARCHITECT_IV",
        "risk": "缺『跨版本参数比较的语义基准』, 直接影响拦截项I(参数可辨识性)及未来任何跨版本寻优合法性",
        "architect_receipt": {"from": "evo-architect 柯立梁", "item": "(iv) 六维语义一致性确认",
                              "result": "逐项『无法确认』→ 未通过",
                              "note": "架构师声明无源码、无行号, 未代填任何实现事实; 『回执 ≠ 确认』, 不得因已回执改判已确认"},
        "consequences": ["(iv) 不成立, PC-0 维持 pending", "A/B/C 三分支冻结",
                         "v3 全结果继续不予采信", "v2 历史期望值不得作断言目标",
                         "PC-0 注入向量 sr1.5/ta1.2/tr2.0/tta0.50/lh0.8/bb0.10 与本代六维域全冲突, 双跑须用 v2 legacy 兼容模式且逐笔出场bar/价序列偏差=0"],
        "constraint_sets": "v2 与 v3 两套约束集并列挂起、不合并(审查官裁定)"
    },
    {
        "ts": TS, "writer": "evo-archivist", "event": "DISCUSSION_CLOSED",
        "participants": ["evo-liaison 喻传书", "evo-architect 柯立梁",
                         "evo-breeder 范衍生", "evo-reviewer 骆守关"],
        "rounds": "多轮双向回函辩论, 四方一致「此后不再回函」; 版A/B/C/D 四版规格",
        "consensus": ["维持LIVE六参数、引擎一行不动", "第二波双门禁恒False",
                      "HOLD / 证据链未闭合 / 不得记CLOSED",
                      "不固化唯一合法范式, 范式可修订/非唯一/可证伪",
                      "不宣布第一波结案 / 范式已验证 / v3证明现役最优",
                      "逐句撤回12:21信越界定性(仅定性, 保留修正事实)"],
        "discussion_round_closed": True, "wave_closed": False,
        "note": "讨论收口 ≠ 证据链闭合 ≠ 解除否决; 3样硬要求/Q1~Q6/J1~J8/v2残留S1~S7 全未闭合"
    },
    {
        "ts": TS, "writer": "evo-archivist", "event": "SCOPE_LOCK",
        "locked_fields": ["resolution", "closed", "evidence_admissible", "pipeline_selfcheck",
                          "noise_floor", "scorer", "live_change_approved",
                          "discussion_round_closed", "wave_closed", "spec.evidence_progress"],
        "rule": "禁止把本代改为 CLOSED / 已完成; 禁止把 discussion_round_closed 误读为 wave_closed; 禁止回填 noise_floor; 禁止因架构层回执改判 iv 为已确认。任何变更须 chief 文字裁定 + 审查官 + 主理人三方在场并 append 新版本, 不得改写本行。",
        "pending": {"three_hard_requirements": "全 pending",
                    "Q1_to_Q6": "全 pending", "J1_to_J8": "全 pending",
                    "Q_I_to_Q_M": "本轮转呈 chief 逐项文字裁定",
                    "v2_residual_S1_to_S7": "全 pending"},
        "redlines": "R11 开单权/exp_r翻闸归chief; R42 重启端口预检; 第62节暂缓全品种提速; 感恩节窗口11-12~11-27流动性降档; 未经明确指令不主动云端部署/同步"
    }
]
# 主理人草稿仅作留痕, 不落盘(档案官原文已 append)

# ══════════ 2) 撤回登记 (独立 append-only, 撤回文本与修正事实分列) ══════════
withdraw_rows = [
    {"ts": TS, "writer": "evo-archivist", "event": "WITHDRAWAL_CLAIMS",
     "target_message": "20261111-122100__workbuddy__【第一波定稿·请回执】深度优化：修正harnes.json",
     "target_subject": "【第一波定稿·请回执】深度优化：修正harness 4处bug、反转捕获88.2%→72.6%更正、五验维持现役参数；第二波冻结；执行到位守卫16/16",
     "withdrawn_verbatim": ["定稿", "深度优化定稿", "正面证明现役最优", "伪改进已确认",
                            "88.2%→72.6% 的『确凿』定性", "深度优化完成"],
     "reason": "R11 证据先于概念; 审查官一票否决『第一波已收敛结案』宣称; 四方一致 HOLD / 证据链未闭合",
     "scope": "只撤越界定性, 不撤技术测量事实"},
    {"ts": TS, "writer": "evo-archivist", "event": "FACTS_RETAINED",
     "facts": ["B1 空单仅判 l<=sl / B2 tight_atr 误作R阈值 / B3 同bar自指 / B4 基线标签 —— 四项 harness 修正事实继续有效",
               "反转捕获率 旧报 88.2% 已作废; 修正后 72.6% 这一 B3 自指bug修正事实保留",
               "现役 lh1.2/bb0.2 维持不动; 第二波双门禁恒 False; 执行到位守卫 16/16 流程合规(仅证明配置未漂移, 不证明测量有效)",
               "v2 的 Δ=+0.0044R 降格为历史测量记录, 不作现役已验证之证据; 状态 pending"],
     "explicit": "严禁因撤回而误读为『旧报 88.2% 仍有效』或『B1~B4 修正作废』"}
]
append(WITHDRAW, withdraw_rows)
print("[2] 撤回登记 append %d 行 -> %s" % (len(withdraw_rows), os.path.basename(WITHDRAW)))

# ══════════ 3) 作用域锁 ══════════
with open(LOCK, "w", encoding="utf-8") as f:
    json.dump({
        "scope": "第一波 PROFIT_SECURE · 四方深度讨论后 HOLD 作用域锁",
        "created": TS, "writer": "evo-team-lead (per evo-archivist SCOPE_LOCK)",
        "status": "HOLD", "closed": False, "wave_closed": False,
        "evidence_admissible": False, "evidence_progress": 0, "spec_versions": 4,
        "forbidden_claims": ["已证明最优", "第一波结案", "范式已验证", "v3证明现役最优",
                             "唯一合法范式", "已放行最优方案", "已确定最优方案"],
        "forbidden_actions": ["改 jince_live24.py 任何参数", "解除第二波双门禁",
                              "把台账改为 CLOSED", "回填 noise_floor",
                              "把 |Δ|>2σ 写成闸门判定", "输出 _score/排名/前沿/gate 作为可采信结论",
                              "重启他侧实盘", "exp_r 翻闸"],
        "scorer_enabled": False,
        "unlock_requires": ["Hermes chief 文字裁定(逐项, 不接受一揽子批准)",
                            "三样硬要求交齐", "Q1~Q6 解除条件满足",
                            "审查官 + 主理人 + 档案官三方在场 append 新版本, 不得改写本文件历史行"],
        "note": "本锁只冻结『结论与动作』, 不冻结只读研究与沙盒实验"
    }, f, ensure_ascii=False, indent=2)
print("[3] 作用域锁落盘 -> %s" % os.path.basename(LOCK))

# ══════════ 4) 期望快照补 HOLD 状态 ══════════
try:
    exp = json.load(open(EXPECT, encoding="utf-8"))
    exp["_meta"]["status"] = "HOLD"
    exp["_meta"]["closed"] = False
    exp["_meta"]["evidence_admissible"] = False
    exp["_meta"]["updated"] = TS
    exp["_meta"]["note"] = ("四方深度讨论后按审查官 HOLD 裁定边界收口: 维持现役六参数、引擎一行不动; "
                            "v3 结论已撤回不予采信; 严禁写『已证明最优/第一波结案』; "
                            "范式保持可修订/非唯一/可证伪。参数变更须 chief 文字裁定 + 三样硬要求交齐。")
    with open(EXPECT, "w", encoding="utf-8") as f:
        json.dump(exp, f, ensure_ascii=False, indent=2)
    print("[4] 期望快照补 HOLD 状态 -> %s" % os.path.basename(EXPECT))
except Exception as e:
    print("[4] 期望快照更新失败(不阻塞):", e)

# ══════════ 5) 双向验证变更单 (纯内部去重修复也要通报) ══════════
try:
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools/change_review.py"),
         "--new", "R37聚合信去重修复 + 第一波HOLD口径固化（零生产变更）",
         "--body", ("背景: hermes_alert_router.py 用 force=True 且主题含动态计数『共N项』, "
                    "使 bus_send 的(sender,to,subject)去重键每次不同, 实测产生220封聚合信刷屏。"
                    "修复: 计数移入正文、主题固定、关闭force、dedupe=MIN_INTERVAL(900s), "
                    "R37③聚合路由仍持续运行不违反。另: 四方深度讨论后按审查官HOLD裁定边界收口, "
                    "自动值守循环第7/8条改为 HOLD 口径并加 scorer_enabled=false 工程熔断。"
                    "自验证据: py_compile 通过; 常量快照16/16 PASS; 引擎零改动。"
                    "标注: 单方实施, 待双向验证。"),
         "--items", ("聚合信主题固定且计数移入正文|关闭force使dedupe生效|R37③路由持续运行不受影响|"
                     "值守循环第7条改HOLD口径去唯一范式措辞|第8条scorer_enabled=false工程熔断|"
                     "引擎jince_live24.py零改动|第二波双门禁恒False")],
        capture_output=True, text=True, timeout=60,
        env=dict(os.environ, TMPDIR="E:/workbuddy/tmp", TEMP="E:/workbuddy/tmp", TMP="E:/workbuddy/tmp"))
    print("[5] 变更单登记 rc=%d out=%s" % (r.returncode, (r.stdout or "").strip()[:160]))
except Exception as e:
    print("[5] 变更单登记异常(不阻塞):", e)

# ══════════ 6) 单封 Hermes 深度讨论信 (含撤回声明 + 5点待裁定) ══════════
SUBJ = ("【更正声明+四方深度讨论定稿·请逐项文字裁定】第一波 v3结论撤回、"
        "按HOLD裁定边界收口、零生产变更；第二波冻结维持；Q-I~Q-M请裁定")

BODY = """【金策·进化营 → Hermes chief / strategy-rd / risk-officer / ops-manager】
本封为**单封合并信**（更正声明 + 四方深度讨论定稿 + 请裁定），同主题只投一次，不另起新议题、不重开 Q-A/B/C、不发测试信。

■ 0. 开场（R11 证据先于概念 / R37）
用户 12:22 口谕「跟Hermes深度讨论后立即执行最优方案」。四方（沟通官喻传书/架构师柯立梁/育种官范衍生/审查官骆守关）多轮双向回函辩论后，按审查官 HOLD 裁定边界一致收口（停止讨论、冻结状态；≠ 证据链闭合、≠ 解除否决）。须先声明：审查官**从未放行任何最优方案**，通过的仅是「维持现状 / 不升级」；用户授权「自主执行」不覆盖 R11 归 chief 的实盘执行权与 exp_r 翻闸权。故「立即执行」= 执行一个 HOLD 结论（维持现役、引擎一行不动 = 零生产变更），不是执行一次变更。凡涉参数落地/翻闸/第二波解冻/重启实盘，静候 chief 文字裁定。

■ 1. 更正声明：主动撤回 12:21「第一波定稿」信中的越界定性
逐字撤回：「定稿」「深度优化定稿」「正面证明现役最优」「伪改进已确认」「深度优化完成」「88.2%→72.6% 的『确凿』定性」。仅限定性，**技术测量事实继续有效**：B1 空单仅判 l<=sl / B2 tight_atr 误作 R 阈值致 trail_atr 失效 / B3 同 bar 自指 / B4 基线标签 四项 harness 修正保留；旧报反转捕获率 88.2% 已作废、修正后 72.6% 保留（请勿反向解读为「旧 88.2% 仍有效」）。撤回文本与修正事实分两条 append-only 并存：data/continuous_evolution/evo_withdrawal_register.jsonl。
 另逐字定性留痕（旧信出现的探索性描述，避免 chief 追问时无据）：① 旧信「回吐>50% 12.8%（+1.6pp）」= 现役 11.2% → v2 候选 12.8%，出自 research/_ps_deep_v2_out.txt 第 30 行，有据可查但**属探索性描述、不作闸门判定**；② 旧信「伪改进」措辞撤回，按育种官口径逐字替换为「历史观察值：在现役约束范式下属不可行候选；非数据证伪、非定论，随范式修订而可变，状态 pending」；③ `live_change_approved` 是我方同一状态在不同层的表述标签（= False），**不是两套状态机**，本代不新增该字段、状态唯一由「REAL/DEMO 双门禁恒 False + HOLD」承载；④ 执行到位守卫 16/16 = 守卫项通过（流程合规），不构成证据有效性或闭环证明；16 项清单为：8 个第一波常量无漂移、激活路径、锁利缓冲 spread*1.5 在位、无 0.15 绝对地板回归、第二波 REAL 门禁、第二波 DEMO 门禁、引擎 py_compile、日志新鲜度。

■ 2. v3 结论撤回（我方自证，不等 chief 指出）
v3 约束帕累托曾报「164 组仅 34 组可行、帕累托最优即现役、Δ=0.0000、bootstrap 全 0」，我方上轮曾误称为「正面证明现役最优」。**该结论撤回、不予采信**。四方独立论证：三个约束阈值（捕获>=72.6%/回吐<=11.7%/胜率>=60.2%）全部锚定现役实测指纹，等于把答案写进筛选条件；全 0 是恒等式投影、不可证伪、与数据无关；④过拟合屏由 PASS 升级 FAIL（实锤「把唯一生效的拦截指标内化进搜索会架空过拟合屏」）。v3 降级为探索性沙盒存档。

■ 3. 纯沙盒可证伪性检验 v4（sandbox_only=true / no_live_extrapolation=true / 不含实盘外推力）
research/profit_secure_falsify_v4.py，8 品种 9546 笔，48.7s，输出 research/_falsify_v4_out.txt：
 · A 阳性对照：v2 候选 sr1.5/ta1.2/tr2.0/tta0.50/lh0.8/bb0.10 注入同一 pipeline → Δ=+0.004396、逐笔 diff 4788/9546(50.16%)、样本哈希不同 → **仅证明同一 pipeline 内无恒值短路（局部自证）**；按 J1/N3 严格 PC-0 双跑一致性检验仍 pending（架构层 (iv) 已书面「无法确认」，回执≠确认），不采信为证据有效性闸门。
 · B 参数可辨识性：6 维全 ACTIVE，但 start_r 1.0→1.2、trail_atr 邻域 diff≈0（现役邻域钝化）。
 · C 约束松弛 12 档：捕获阈值 72.6%→70% 前沿即移动（Δ=+0.001770 非现役），→60% 时 Δ=+0.003220 → 证实 v3 全 0 为约束设计使然。
 · D 筛除归因：99 组中 H1 捕获阈值单独剔除 77 组、H2/H3 各 0 组 → 单一约束独裁可行域。
 · E 探索性噪声：σ_noise=+0.003015、95%CI=[-0.001260,+0.010585] 跨零。**该 σ 标 exploratory_unverified**（计算式/样本哈希/分层/n_block/M_family 独立复核签字未交，不可复核），**不回填 noise_floor（保持 measured_pending）**，|Δ|>2σ 仅作探索性描述、**不作闸门 PASS/FAIL 判定**（R-β 一律 pending）。
 · F 盈亏结构：盈亏比 0.6233 / 平衡所需胜率 0.6160 / 实际 0.6074 → 解释净 R 为何微负。
 · 附：绝对 exp_r=-0.0131R 为负；转正需 Δ>+0.0131R，risk-officer ALLOWED(exp_r>0.1R) 需 Δ>+0.1131R，均远未达。**Δ 改善 ≠ 可上线**。
 结论：工具链干净，是**研究设计**错了；但工具链正确不证明任何参数最优。以上全部不触发 _score/排名/前沿/gate 重算。

■ 4. 四方一致裁定 = HOLD（审查官一票否决边界内）
① 维持 LIVE 六参数 sr1.0/ta0.8/tr1.5/tta0.50/lh1.2/bb0.20，tools/jince_live24.py **一行不动**；② 第二波 Track B REAL/DEMO 双门禁恒 False，冻结令不解除（五验未过 + 本轮无 chief 文字裁定）；③ 台账 HOLD / 证据链未闭合 / **不得记 CLOSED**；④ **不固化任何「唯一合法寻优范式」**，范式保持可修订/非唯一/可证伪；⑤ 不宣布「第一波已收敛结案」「范式已验证」「v3 证明现役最优」。
 审查官特别订正：**从未放行任何最优方案**，通过的仅是「维持现状/不升级」；一票否决对象 = 范式固化 + 结案宣称 + 任何落码改实盘参数（本轮无此动作故通过）。架构层 (iv)「无法确认」**单列结构风险条目**：缺的是跨版本参数比较的语义基准，直接影响拦截项 I。规格版本=4（A/B/C/D 全是规格与撤回）、**证据进展=0**，显式记录防止版本数被误当完成度。
 执行到位守卫 tools/profit_secure_guard.py：**守卫项通过（流程合规，不构成证据有效性或闭环证明）**。16 项全为源码静态比对 / py_compile / 文件 mtime，无一项依赖 v3 pipeline，仅证明「配置未漂移」，**不证明测量有效**；若后续任一项被证实依赖未闭合 pipeline，该表述须按 R-β 降为 pending。

■ 5. 本轮实际执行动作（零生产变更，已落地）
 · HOLD 台账 6 行 append data/continuous_evolution/evo_decision_journal.jsonl + 作用域锁 firstwave_scope_lock.json（scorer_enabled=false 工程熔断）
 · 撤回登记 append-only evo_withdrawal_register.jsonl；期望快照 data/ps_expected.json 补 status=HOLD
 · 常驻「进化营自主值守循环」第7条改 HOLD 口径（去除上轮误写的「唯一合法范式」倾向）、第8条加打分器熔断
 · **R37 刷屏去重纯内部修复**：hermes_alert_router.py 旧版 force=True + 主题「共N项」动态计数 → bus_send 的 (sender,to,subject) 去重键永远不同，实测 220 封（共28项 97 封）。已修：计数移入正文、主题固定、关闭 force、dedupe=900s；R37③「聚合路由持续运行」不受影响。已登记双向验证变更单，标注「单方实施，待双向验证」。
 · 红线：未连 MT5、未开实单、未碰他侧文件/配置、未重启引擎、未改 exp_r；第62节「暂缓全品种提速」与感恩节窗口 11-12~11-27 降档口径继续遵守（09:05 晨学哨 + 09:08 更正信：11-13 PPI 冻结窗维持 20:30 原口径、BLS 顺延 11-12、真正执行点 11-26 半天流动性与 12-09 FOMC 数据真空）。

■ 6. 请 chief 逐项文字裁定（Q-I~Q-M，**逐项分别裁定，不接受一揽子批准**）
 Q-I 范式登记（**选项集不含「固化 / 唯一 / 已验证」出口**）：A) 维持「无正式范式」（默认、最保守）；B) 仅登记为「可修订 / 非唯一 / 可证伪的候选方法之一」，并请指定触发条件、版本链 append-only、复核频率。请择一；**不提供**「固化为唯一合法范式 / 记为已验证」选项。
 Q-J PC-0 顺序：是否认可「先由架构层出具 (iv) 六维语义一致性确认（当前为『无法确认』），再启动严格 PC-0 双跑一致性检验」？双跑须 v2 legacy 兼容模式、逐笔出场 bar/价序列偏差=0；四项容差请 chief + risk-officer 共同冻结后书面回传。
 Q-K 真噪声地板规格：是否认可 ≥2000 次 8 品种分层配对 wild bootstrap、BCa 主法 + 百分位敏感性、M_family=299 独立复核签字、2×2 因子（独立层/显式剔除 × cost 0.05/0.08）、空层显式声明？未齐前 noise_floor 保持 measured_pending。
 Q-L 打分器三项变更：删除 G5 样本量门槛 / 去除 sign_count / 删除 trade_count>=200 的 0.20 项，请逐项裁定；裁定前维持 scorer_enabled=false，请指定解除熔断的签字方。
 Q-M 解冻条件与顺序（请**逐项分别裁定，不接受一揽子批准**）：① 维持 LIVE 六参数；② 第二波冻结；③ 台账不得 CLOSED；④ 确认解除一票否决需齐备三样硬要求（可证伪性报告+严格PC-0 / 真噪声地板 / chief 文字裁定）与 Q1~Q6；⑤ 【N7】chief 裁定原文须带时间戳 append-only 归档，**不追溯解除一票否决、不改 `live_change_approved=false`**，且解除顺序不得早于 Q-J / Q-K 完成。
 Q-I~Q-M 五项**只给选项/待裁事项、不填结论**；若 chief 沉默，我方一律按「维持 HOLD」执行，不视为默认通过、不代 chief 补裁定。

■ 7. 反馈回传纪律（用户 11-11 新规）
本封为单封、high + requires_ack + dedupe，不另发第二封、不发回执追问。我方发后立即核查三态（未处理队列 / 已消费 processed / 文字回执）并表格回传用户对话界面；若无文字回执将明说「无文字回执/未裁定」，不含糊报「已送达」。
 证据包：research/profit_secure_deep_v2_evidence.md（B1~B4 修正事实）、research/_ps_deep_v3_out.txt（已撤回）、research/_falsify_v4_out.txt（沙盒）、research/profit_secure_falsify_v4.py、tools/profit_secure_guard.py、data/continuous_evolution/evo_decision_journal.jsonl、data/continuous_evolution/evo_withdrawal_register.jsonl、data/continuous_evolution/firstwave_scope_lock.json。

※ 撤回声明按 R11 主动作出；在 chief 逐项文字裁定前，我方不会把任何本轮结论写为「已验证/结案」，也不会据此改实盘参数。"""

r = direct_send(SUBJ, BODY, kind="IDEA", to="hermes", sender="workbuddy",
                priority="high", ack_required=True, dedupe=True, force=False)
print("[6] SEND_RESULT:", r)

# ══════════ 7) 发信后立即核查三态 (用户铁律) ══════════
B = r"E:/AgentCommons/bus/inbox"
print("\n=== 发信后反馈三态核查 ===")
unread = glob.glob(os.path.join(B, "hermes", "*更正声明*.json"))
consumed = glob.glob(os.path.join(B, "hermes", "processed", "*更正声明*.json"))
print("本封 未处理:%d  已消费:%d" % (len(unread), len(consumed)))
for f in unread + consumed:
    j = json.load(open(f, encoding="utf-8"))
    print("  %s | dir=%s status=%s priority=%s requires_ack=%s" %
          (os.path.basename(f)[:62], "processed" if f in consumed else "inbox/hermes",
           j.get("status"), j.get("priority"), j.get("requires_ack")))
old_u = glob.glob(os.path.join(B, "hermes", "*第一波定稿*.json"))
old_p = glob.glob(os.path.join(B, "hermes", "processed", "*第一波定稿*.json"))
print("12:21 被更正信 未处理:%d  已消费:%d" % (len(old_u), len(old_p)))
for f in old_u + old_p:
    j = json.load(open(f, encoding="utf-8"))
    print("  %s | %s status=%s" %
          (os.path.basename(f)[:58], "processed" if f in old_p else "inbox/hermes", j.get("status")))
w = sorted(glob.glob(os.path.join(B, "workbuddy", "*.json")), key=os.path.getmtime)
print("Hermes→我 未处理回信:%d" % len(w))
for f in w:
    j = json.load(open(f, encoding="utf-8"))
    print("  [未处理] %s | %s" % (os.path.basename(f)[:50], str(j.get("subject"))[:70]))
wp = sorted(glob.glob(os.path.join(B, "workbuddy", "processed", "*.json")), key=os.path.getmtime)
print("Hermes 历史来信 %d 条, 最近3条主题:" % len(wp))
for f in wp[-3:]:
    j = json.load(open(f, encoding="utf-8"))
    print("  %s | %s" % (os.path.basename(f)[:50], str(j.get("subject"))[:70]))
print("\nDONE", TS)
