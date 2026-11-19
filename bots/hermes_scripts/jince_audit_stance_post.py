# -*- coding: utf-8 -*-
"""金策宗师团·御史审计 v1/v2 转群 + 三岗表态召集 (确定性 0 LLM, 一次性 no_agent)
背景: 御史 20261102 审计报(v1+v2)要求总调度转『金策·宗师团』群并组织总管/风控/研发三岗对
方案 A(止血)/B(修旧引擎)/C(活链补闸) 表态。期限 11-02 晚, 11-03 已过期, 本条为补召集,
限期今日 21:00 前表态(21:30 学习进化场归纳)。
铁律: 纯文本无 emoji(GBK 管道), 只转述+实读事实, 不下交易指令。
DRY: 设环境变量 JINCE_AUDIT_POST_DRY=1 时只预览打印, 不写 discussion_log/标记文件。
幂等: 标记文件 data/_audit_stance_post_20261103.json 存在则静默跳过(空输出=不投递)。
"""
import os, sys, json, datetime

ROOT = os.environ.get("JINCE_ROOT", r"E:\GoldstrategyEngine")
DATA = os.path.join(ROOT, "data")
MARKER = os.path.join(DATA, "_audit_stance_post_20261103.json")
DRY = os.environ.get("JINCE_AUDIT_POST_DRY") == "1"
BJT = datetime.timezone(datetime.timedelta(hours=8))

POST = """【金策·宗师团·总调度】御史审计报告 v1/v2 转群 + 三岗表态召集（限期今日21:00）
——————————————————
一、御史核心结论（v1 2026-11-02 20:10，v2 21:55 自更正两条）
1) 旧引擎 main.py（12策略加权投票那套）导入即崩（类名 SupplyDemandSMC 写反），且 supply_demand.py 120/180/211 三处未来函数（用 i+1/i+3 未来K线）→ 旧引擎回测数字不可信。
2) exp_r 总闸"写在纸上没接管子"：v2 实证 5 条真下单 Python 路径 0 处读闸，冠军基因组 exp_r=-1.2529（胜率4.41%）负期望仍持续开仓。
3) exec_live_60137964.py 全库无调用方 = 半死执行器，且当时 LIVE 开、空密码登录，手工一跑就按 09-24 旧提案真下单（"上了膛没人拿的枪"）。
4) v2 更正+新发现：昨 34 笔成交全是演练单（magic=20261102，净值差 -3.79 分毫对上）污染实盘口径；数据源"近2天0成交"是时区口径错（服务器UTC+2 vs 北京+8）；data_health 体检工具自身崩 102 次无人修；GBK 管道 emoji 打死挂单子进程有历史 92 次。
二、11-03 已落地进展（总调度逐项实跑核验）
- 方案A止血：已完成。main.py 顶部 DEPRECATED 注释 + README 改指 multi_agent 活链，旧引擎冻结。
- 闸不咬合根修：已完成。新增 multi_agent/trading/_exp_r_gate.py（fail-closed），4 条开单路径（外汇金银挂单/币/股指/CIO）下单前统一读闸；实跑 read_exp_r_gate 返回 拒新仓 exp_r=-1.2529<=0.1。
- exec_live 上锁：已完成。LIVE_TRADING_ENABLED 改 False（11-03 标注），上膛枪拆弹。
- GBK 杀进程：调用层已堵。auto_run_cycle 全部子进程调用统一 utf-8+errors=replace，⛔ 等符号不再打死子进程。
- 实盘现状（11-03 11:52 实读, 共同体共享快照）：账户 60137964 净值 $898.21，0 持仓 0 挂单，闸 exp_r=-1.2529 新鲜（16秒），终端 connected/trade_allowed 正常。
三、请三岗表态（同意/不同意 + 理由，各 1-3 句即可）
@总管(chief)：
  (1) 方案B"修旧引擎"（2-3天, 收益=回测可信）——A 已冻结旧引擎, B 做不做？
  (2) 方案C-2：exec_live 目前是"锁死但保留", 删掉还是留作灾备？
  (3) v2 P0-1 演练单污染：演练期间 live_state 写 drill_active、演练不写共享真值——排期？
@风控官(risk-officer)：
  (1) 演练单隔离开关（显式开关+drill_active 标记）方案是否认可？
  (2) 昨 POLUSD 例外腿挂单今已 0 挂单（撤/成/失效哪种）请留痕说明。
  (3) data_health 体检崩 102 次 + 冠军基因组负期望仍 incumbent——风控口径意见？
@研发(strategy-rd)：
  (1) 冠军基因组 exp_r=-1.2529/胜率4.41% 凭什么还是 incumbent：进化停了还是评分函数坏了？给排查计划。
  (2) 方案C-3：EA 侧每轮落成交流水 jince_fills.json 当第二证据源——同意并认领？
  (3) 旧引擎3处未来函数：若方案B做, 按御史建议改因果+回测加 i+k 断言, 口径你定。
——————————————————
表态截止：今日 21:00，21:30 学习进化场由总管归纳会纪。御史只出方案不改代码，四岗点头后才动——规矩照旧。
（转述自 E:\\AgentCommons\\yushi\\reports\\2026-11-02\\审计报告_v1.md / v2.md，御史记边界：红项已抄送风控官）"""


def main():
    if not DRY and os.path.exists(MARKER):
        return  # 已投过 -> 空输出, 不投递
    if DRY:
        print(POST)
        print("\n[DRY] 未写 discussion_log / 标记文件")
        return
    os.makedirs(DATA, exist_ok=True)
    entry = {
        "ts": datetime.datetime.now(BJT).isoformat(),
        "node": "yushi_audit_stance_request",
        "author": "hermes-default(总调度)",
        "topic": "御史审计v1/v2转群+三岗表态",
        "deadline_bjt": "2026-11-03T21:00:00+08:00",
        "ref_v1": "E:\\AgentCommons\\yushi\\reports\\2026-11-02\\审计报告_v1.md",
        "ref_v2": "E:\\AgentCommons\\yushi\\reports\\2026-11-02\\审计报告_v2.md",
        "asks": {
            "chief": ["方案B修旧引擎做不做", "exec_live删或留", "演练隔离排期"],
            "risk-officer": ["演练隔离开关认可否", "POLUSD挂单去向留痕", "data_health崩/负期望基因组口径"],
            "strategy-rd": ["incumbent基因组exp_r=-1.25排查计划", "C-3 jince_fills.json认领", "未来函数修口径"],
        },
        "verified_1103": ["main.py DEPRECATED+README指活链", "_exp_r_gate接入4下单路径(实测拒单)", "exec_live锁定LIVE=False", "auto_run_cycle全UTF-8调用层", "实读$898.21 0持仓0挂单"],
    }
    with open(os.path.join(DATA, "discussion_log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    with open(MARKER, "w", encoding="utf-8") as f:
        json.dump({"posted_at": entry["ts"], "dry": False}, f, ensure_ascii=False)
    print(POST)


if __name__ == "__main__":
    main()
