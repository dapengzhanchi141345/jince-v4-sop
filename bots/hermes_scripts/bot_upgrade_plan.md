# Hermes 26 bot 弹药库升级规划（单一事实源）

> 建立 2026-10-04 · 规划执行由 Hermes cron 自动驱动，人只做抽查
> 备份根目录：`E:/workbuddy/国外模型/hermes/profiles/_sota_backup_<YYYYMMDD>/`（升级前自动全量备份 sota 技能目录）

## 一、管什么（资产清单）
- **26 个 profile**：金策 4（default 总调度/chief/risk-officer/strategy-rd）+ 专家 22
- **弹药库技能（SOTA）**：每 profile 1 个 `*-sota`（`*-skills`）目录 = 2024-2026 方法论/政策/工具快照
- **SOUL 作战手册**：金策 3 个交易 bot 的 SOUL.md（9/2 升级后 8.6-13.3KB）
- **不动的东西**：4 把专属 key（RC3b/yBL7/GRQZ/TWey）、config.yaml、.env、交易引擎确定性层

## 二、升级节奏（三档）
| 档 | 频率 | 动作 | 驱动 |
|---|---|---|---|
| 弹药库刷新 | 每月 1 日 + 15 日 03:30 | `bot_sota_scan.py` 扫 90 天周期 → 到期技能分批（≤4/批 防 429）备份+联网检索+原地更新 | cron `ae13a98bf368` bot-sota-monthly-upgrade |
| 冒烟验真 | 每月 1 日 04:30 | 金策 3 交易 bot + 3 重点专家 bot 跑「你是什么角色」验人设加载 + sqlite 查回答 | cron `6efebbcb233c` bot-soul-smoke-monthly |
| 季度全检 | 每季度首月（并入 1 日冒烟） | `bot_sota_scan.py --force` 全量 26 profile 日期戳盘点，>90 天全进队 | 手工触发或并入冒烟任务 |

## 三、周期与批次铁律（写死，防走样）
1. **90 天周期**：技能内「检索日/刷新日」距今 >90 天才进升级队列；没到期=不动，cron 如实报「无到期项」不烧 LLM。
2. **每批 ≤4 个**：免费池 RPM 低，一批 4 个 sota 的联网量是 429 实测安全线（2026-10-03 实测 11 个一批全崩，3 个一批全过）。
3. **429 三行为（定死）**：① 429 后 30s 自动重试 1 次；② 连续 2 次 → 该批降级为「只备份 + 写待办 `E:/GoldstrategyEngine/data/bot_sota_pending.md`」，下轮续做；③ 绝不静默吞掉，降级也落盘留痕。
4. **备份先行**：任何升级前 `_sota_backup_<YYYYMMDD>/` 全量备份本轮要动的技能目录。
5. **frontmatter 锁**：更新只改正文，`name:` 行永不动（skill 索引靠它）。
6. **无源不编造**：检索没新料 → 如实标「本期检索未更新，沿用 <旧日期> 基线」，绝不编来源。
7. **红线继承**：政策/考试条目标「以官方当年文件为准」；中医标「文化科普，不构成医疗建议」；命理标「不作决策依据」。

## 四、数据与留痕
- 扫描机读：`E:/GoldstrategyEngine/data/bot_sota_scan_last.json`（每轮全量日期戳 + 到期队列 + 批次）
- 冒烟机读：`E:/GoldstrategyEngine/data/bot_smoke_last.json`（每轮 6 profile 验真结果）
- 待办残留：`E:/GoldstrategyEngine/data/bot_sota_pending.md`（429 降级未完成的批次）
- 升级日志：本文档「## 升级日志」节（每轮 cron 追加一行）

## 五、人工口（李彦明抽查用，零歧义步骤）
想确认某 bot 弹药库新不新：让 Hermes 主 bot 说一句「跑一次 bot_sota_scan.py --force 给我看清单」即可。
想手动触发某次升级：「现在执行 bot_sota_monthly_upgrade」→ 主 bot 按三、的节奏执行一轮。
想停用：「把 bot-sota 相关 cron 都 pause」。

## 升级日志
- 2026-10-03/04 手动首刷：金策 3 SOUL 升级 + 23 个 sota 全量刷新（子代理 2 崩主进程接手），备份 `_sota_backup_20261003/`。
- 2026-10-15 03:30 例行：扫描 53 个弹药库技能，0 个到期（全部在 90 天周期内），无待办残留，本轮静默跳过、未烧任何联网检索。
