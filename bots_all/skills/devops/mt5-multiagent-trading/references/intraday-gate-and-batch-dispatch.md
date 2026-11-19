# 松闸持久化 & 批量派单 429（2026-10-07 教训）

## 松闸/策略改动持久化铁律
- `data/risk_freeze_state.json` 是**全链 30min 循环的临时产物**——手工改它必被下一轮 `E:/GoldstrategyEngine/risk_network_gate.py` 重算冲回（现象：手工改 LEVEL_0 + 日内铁线，两轮后全丢、open_new_order 回 False）。
- **要松闸/加策略参数，必须**：① 写持久参数文件（如 `data/intraday_policy.json`，全链循环不碰它）；② 把读取逻辑焊进 `risk_network_gate.py` 重算段（`load_intraday_policy()`），每轮重算自动带上；③ 改完**实跑一遍风控闸 + 实读 state 验证 `open_new_order` 真为 True** 才算生效，不能只改文件就当生效。
- DST 冻结令（dst_freeze，11-02 NFP 生死测）默认一刀切 ban_open=True；日内策略生效时应区分：币系冻（coin_freeze 独立闸，11-02 NFP 前币系 0 开）+ 禁 overnight（hold_max_hours=12），但日内 FX/金/G10 单（12h 必平）放行，别一刀锁死。
- 动风控官独立闸（DST/双闸口径）时：即使有"全交给我"授权，改动也要留痕（state note + discussion_log）并让 risk-officer 复核，不静默破独立风控。
- 2026-10-07 已落地：`intraday_policy.json`（enabled/hold_max_hours=12/intraday_only/coin_freeze）+ `risk_network_gate.py` 的 load_intraday_policy() + DST 分支尊重日内政策。实读 state: open_new_order=True + 日内铁线齐，LIVE_TRADING_ENABLED 仍 False（只练不真挂）。

## 429 限速下的 bot 批量派单
- 向多个学科 bot 批量发认领单时，各 bot 的 LLM 调用共享今日文本额度，**连发会集中撞 429（免费池每 1 分钟 1 次限速）**。
- 认领单进了队列不丢（额度次日 0 点重置自动回执），**不必刷重发**（刷了也是 429）；确定性 0 LLM 的活不受影响照跑。
- 回执回来才报进度，没回执别报"已派单"（本会话教训：曾口头报"12 张全发"实际只有 it-edu 一张发出，用户发现"各智能体没动静"）。
