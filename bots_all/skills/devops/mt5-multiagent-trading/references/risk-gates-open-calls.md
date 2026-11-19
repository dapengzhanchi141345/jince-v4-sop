# 金策闸/风控状态 速查（2026-10-07 起）

> mt5-multiagent-trading 技能支撑文件。用户问「怎么一直没单/没挂单/太紧没收益」或改闸时先读这里。

## 1. 开单闸状态源与重算铁律（核心坑）
- 开新单闸的活体状态 = `E:\GoldstrategyEngine\data\risk_freeze_state.json`：`level` + `policy.open_new_order` + `external_live` + `note`。判「为什么没单」第一动作 = 实读这个文件 + `event_risk.json`（level/scale/halt）+ `crypto_freeze_gate.json`（币系冻不冻）。
- **铁律（踩过）：`risk_freeze_state.json` 是 30min 全链循环每轮重算的临时产物，不是持久配置。** 外网断/判断岗 429 → 循环自动写回 `level=1 / open_new_order=false`（价源活、外网断的常态）。直接手改该文件放闸 = 下一轮全链冲掉，等于白改。永久放闸/加闸参数必须**焊进全链重算逻辑**（生成该 state 的代码 / 循环入口读闸源处），让每轮重算都把新参数写回来；手改 state 只作一次性应急且要明确告知用户「下轮会被冲回」。
- 改闸前先找「谁写这个文件」（grep `risk_freeze_state` 的写入侧），再决定改哪层；写入侧在 `data/discretion_candidate.py` 读闸（`policy.open_new_order` / `dst_freeze` 一票否决出新候选）——放开 `open_new_order` 候选即出，D 级否决/币系冻结仍独立生效。

## 2. 松闸派单 SOP（用户令「太紧了没单子/加快训练/学日内」类）
用户拍板松闸时按最小影响落，顺序固定：
1. **实读三源定性**：`risk_freeze_state.json`（哪道闸在挡开单）+ `event_risk.json`（事件面 MED/HIGH 半仓=系统主动谨慎，非故障）+ `crypto_freeze_gate.json`（币系冻不冻、何时解冻）。
2. **只松用户点的那道**：用户要「日内进场」= 开「外汇/黄金/G10 日内 setup」闸，**币系冻结（11-02 NFP 生死测）默认不松**（那是用户自己定的纪律，未明说不动）。
3. **日内铁线随闸进**：`hold_max_hours=12`（日内必平、禁 overnight 扛单）写进闸参——「每天进场机会 + 学日内」与隔夜扛单天然冲突，放行隔夜=违背用户意图。
4. **派单两条照发**：strategy-rd 入 rd_queue（日内五闸同分母回放 + XAU OOS 攒单）；risk-officer 入 risk_officer_review_queue（开新单双闸照查：D 级否决继续拦 / >12h 候选 VETO / 币系日内单 0 放行）。
5. **留痕**：`discussion_log.jsonl` 落用户令原文 + 改了什么 + 备份路径（改闸前 `shutil.copy2` 原 state 为 `.bak_<tag>`，回滚有据）。
- 大白话回报用户：哪道闸放了、哪道没动、下一轮全链（~30min）什么时候开始出单、明日优先盯的品种（读全链简报「明日优先」留痕）。

## 3. 「没单子」归因顺序（先排障再谈策略）
用户报 0 开单时按此序归因，别直接归「纪律太严」：
① MT5 终端活体实读（account/orders/positions + 代表品种 tick ts 是否当下）——终端/IPC 问题先走 engine-terminal-ipc-recovery.md；
② 实读 risk_freeze_state（§1）——外网断/429 自动闸 = 环境问题，非策略问题；
③ 读当日全链简报 + 研发台拒绝理由（D 级否决/负期望 setup/低置信 的分类计数）——研究部主动拦 = 纪律在守；
④ 事件面 scale 半仓 + 币系冻结——用户定的纪律。
四步走完仍 0 单且用户嫌紧 → 才走 §2 松闸 SOP。
