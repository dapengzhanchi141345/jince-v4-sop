# 新专岗 (Hermes profile) 立岗 SOP

触发: 用户令『专人负责 X』『按最赚钱/最优方案立刻执行』且现有三岗 (chief/risk-officer/strategy-rd) 职能已饱和 → 新建专岗 (实例: post-mortem 验尸官, 职责=订单全生命周期复盘+进场出场点位优化)。

## 步骤 (按序)
1. **骨架复制**: `robocopy profiles/<同线岗> profiles/<新岗> /E /XD cache backups .curator_backups audio_cache attachments` (config.yaml/.env/auth.json/skills/memories 必带; 旧岗 memories 可留作知识底子)。
2. **总线邮箱**: `mkdir -p E:/AgentCommons/bus/inbox/<新岗>/ outbox/<新岗>/` — bus 双写件放新岗 inbox, 首令任务卡 (json: 职责/数据源/首交期限/红线/汇报线) 同时入 kanban。
3. **配 key (闲置 key 鉴别)**: 各岗 .env 同名 `AGNES_*_API_KEY` 变量取 sha1[:8] 指纹交叉比 — 同指纹=共享专属 key 禁改; 只被低频 fallback 槽引用或 default 独享变量=闲置候选。候选先 curl 探端点归属 (.cn/.com 互不认号, 401≠死), 再按 model-key-pools / references/jince-profiles.md insert-only 配进新岗 (主 provider 切专属 key, 跨端 key 入 fallback 尾; 原池零动; 写前备份 .env/config.yaml)。
4. **派首令 (关键坑)**: 新 profile 未进 live roster 前, `message_agent target=<新岗>` 返回 `ambiguous`/`profile_mismatch` (delivery queued, 遵指令**不重发**); **走 `kanban_create(assignee=<新岗>)` 任务卡** — kanban dispatcher 到达任务时自动拉起新 profile agent, 拉起即读其新 config (含新 key) = 最快激活路径, 无需重启 gateway。roster 同步完成后 message_agent 才可用。
5. **监测挂钩**: cron 两条 — ① no_agent 脚本型日报监测 (归档/交付物 >N 小时停滞才出声, 全绿静默=空 stdout) ② 周五归纳 cron (收新岗周报 → 进 22:00 日报)。
6. **留痕**: 状态卡 + memory 各一行 (新岗名/职责/首交期限/重启权限级 [默认须李令])。

## 弃用 (层级/组件被用户拍板『不用了』)
当日清退不留尾巴: 看门狗探针**撤点名不删探针** (留状态记录, 删 `_eg_alerts` 告警 append) + 台账 CANCELLED (注明理由+重启须李令) + 文件资产保留 (ex5 类不删, 删=重启归零) + 不再跟该对象心跳过期报警 (清退不彻底=每 15min 拍骚扰用户)。

## 验收 (验岗而非信自报)
- key 配好: 探活 curl 该岗主 key 200 真补全 (20-key 池健康 `curl 127.0.0.1:8787/health` 同查)。
- 岗活着: 首交期限到点查其产物目录有无新文件 (监测 cron 代劳), 无产出=点名, >48h=红报用户。
- 人设加载: 用 `hermes -p <新岗> chat -q '你是什么角色?'` 冒烟, 答对职责才算 SOUL/首令吃进 (注意按本轮 session id 查 state.db, 别查最新条)。
