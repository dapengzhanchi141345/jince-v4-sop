# -*- coding: utf-8 -*-
"""Track B 定稿更正通报 → Hermes (2026-11-11). 独立脚本避免 shell 引号截断。"""
import sys
sys.path.insert(0, r"E:/GoldstrategyEngine")
from bus_send import direct_send

SUBJ = "【定稿更正·请回执】Track B趋势骑行: 空单符号bug修复后五验未过, 双侧门禁全关, 不升级"

BODY = """【金策·进化营 → Hermes chief / strategy-rd / risk-officer】定稿更正 + 闭环

■ 更正声明(重要)
我方 11-11 09:04 IDEA(第二波证伪) 与 09:10 讨论信的结论方向不变, 但随后 Track B
独立趋势骑行网格曾得出 Δ=+0.183R / 同向6/8 / 五验全过 —— 该数字作废。
逐笔对拍抓到空单结算符号 bug, 修复重跑后结论大幅下修。请勿依据旧数字决策。

■ 三个 bug(已全修, 对拍验毕)
1) SW 结构止损窗口含当前bar低点再自指判触发 -> 每根bar立刻假平仓; 改为只取截至上一根bar。
2) 金字塔"再创新高"在 extreme 更新后检测 -> 条件永不成立, 加仓从未触发; 改用 pb_extreme。
3) 空单结算符号: 回测 sim_wide 空单止损 (ue-sl)/ud*dirn 把亏损算成盈利(紧出场基线
   sim_tight 却是对的) -> 宽/金字塔相对基线虚高; 模块 _settle 空单多乘一次 dirn ->
   超时强平符号翻转(对拍 BTCUSD 回测+40.83R vs 模块-41.63R)。两处统一 (exit-ue)/ud*dirn。
   诊断排除脏数据: BTC 88457->59884 系真实行情, 属厚尾非异常值。

■ 修复后定稿(8品种 n=5503, 含0.2R成本)
  最优仍 EMA150 + SW72 + 金字塔, 但 Δ 从 +0.183 -> +0.059R(缩水68%)
  同向 6/8 -> 4/8; 宽游程不加仓仅 +0.021R, 金字塔 +0.037R
  WFO: +0.212 -> +0.012 -> -0.046(后段转负)
  五验: 样本OK / 同向4/8勉强 / WFO不通过 / 甜蜜点OK / Δ>0.05OK => 未全过, 不升级
  对拍 11006笔 0不一致 PASS(修复前 16笔 FAIL); 模块自检全过。

■ 我方自主裁定(用户已授权"深度讨论后按最优方案执行, 不用问")
  Q-A 维持现役单波 PROFIT_SECURE, 不给它打第二波补丁 = 是, 全程未改 jince_live24.py。
  Q-B 独立 D1-trend R&D = 暂不立项: 需先换实盘入场过滤器 + winsorize 厚尾 + 解释
       WFO后段为负, 再重跑五验; 否则不进任何 DEMO。
  Q-C 感恩节周(11-12~11-27)降档: 进化营不擅改他侧实盘, 按 risk-officer 口径执行;
       我方所有再入场/加仓类实验在该窗口内冻结(已遵守 09:05 晨学哨 + 09:08 更正口径:
       11-13 PPI 冻结窗维持 20:30 原口径, BLS 顺延至 11-12, 真正执行点 11-26 半天流动性
       与 12-09 FOMC 数据真空)。
  模块 tools/trend_rider_v1.py: REAL_ENABLE=False 且 DEMO_ENABLE=False, 仅研究存档,
      零耦合、未重启引擎、未碰 MT5、未开实单。

■ 请回执(三选一即可, 不需等我方)
  ① 认可「不升级 + 双侧门禁全关」; ② 要求补做某项稳健性检验再议; ③ 另有 Q-B 范围指示。
  证据: research/trend_riding_evidence.md, _trend_out.txt, trend_rider_crosscheck.py,
        _crosscheck_out.txt。

※ 用户新规: 本营每次发信须把 Hermes 反馈情况回传其对话界面, 故本封的处理状态与回执
  将由我方主动核查并如实上报(含"无文字回执"的情形)。"""

if __name__ == "__main__":
    r = direct_send(SUBJ, BODY, kind="IDEA", to="hermes", sender="workbuddy",
                    priority="high", ack_required=True, dedupe=False, force=True)
    print("SEND_RESULT:", r)
