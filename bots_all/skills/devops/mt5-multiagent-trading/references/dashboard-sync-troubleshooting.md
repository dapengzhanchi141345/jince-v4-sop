# 看板同步哨兵 / K线 / GitHub 同步 排障（2026-11-04 根因留痕）

同步脚本都在 `E:/workbuddy/国外模型/hermes/scripts/`：jince_dashboard_sync_guard.py（看板哨兵）、jince_tick_push.py（行情喂）、jince_github_sync.py、jince_node.py（节点）。

## 看板哨兵 [WinError 267]「目录名称无效」
- 根因：`git_push_fallback()` 以 `cwd=C:\Users\ASUS\jince-dashboard` 跑 `git push`，而**该本地仓不存在** → subprocess 抛 WinError 267 冒到哨兵。
- 已根治：给 `git_push_fallback` 加 `if not os.path.isdir(REPO): 跳过` + `except OSError` 守卫（已验证，后续哨兵不再报 267，改为干净打印「git 兜底跳过」并报出真正的 gh auth 错）。只改推送逻辑，不碰交易配置/挂单/撤单。

## gh api 443 推失败 = 双闸，但 extnet 旗别信字面
- (a) **GH_TOKEN 缺失**（gh 未 auth，报错 "gh auth login" / "populate the GH_TOKEN environment variable"）**且** (b) **extnet=down**（外网断，看门狗心跳 extnet=down）。
- 要推得 **token + 外网** 同时通。盯 gh 卡点先看这两项，别只怪 443。tick_push 报「gh api 拿不到远端 HEAD (443/API 抖?)」= 同一双闸。
- **extnet=down 常是误报，先验端点再下"外网断"结论（2026-11-04 实查）：** 看门狗 extnet 探的是另一端点/或滞后面，会出现 `curl -s -m3 https://api.github.com` 返 200 但心跳仍报 extnet=down。正确分诊三步：`curl -s -m3 https://api.github.com`（200=网络实通）+ `gh auth status`（not logged in?）+ `echo $GH_TOKEN`（空?）。若 api.github.com=200 而所有 gh job 全挂，根因收窄为 **仅 gh 鉴权（GH_TOKEN 未配 + gh 未登录）**——一个 token 解掉 tick_push/看板哨兵/12 站部署/夜间全推整串 gh 系 job。**暂停/不停决于墙的性质：间歇墙（443 抖、预计 1h 内自清）= 别暂停、让 job 自愈自动消**；**持续墙（鉴权缺失、token 短期拿不到、job 连挂且每次失败都刷 bot chat 通知）= 暂停失败的推型 cron 止血（`hermes -p <profile> cron pause <job>`，保留本地生成步照跑），token 到位后批量 resume + 补推**——暂停的是"推"不是"生成"，别连带停掉写本地看板的节奏；暂停清单留痕（哪些 job + 为何 + 恢复条件），否则 token 到手后忘了 resume = 推送永久断。12 站部署（02:00）同规：gh 未鉴权时 12 仓建仓/推全挂，暂停部署 cron、本地内容升级照常，恢复后一次补推；各站公网旧版仍活（`公网=活`），掉队是 token 墙的派生症状，别当内容故障反复挖。
- **`jince_github_sync.py` 夜间全推 "Script timed out after 3600s" = 同一 gh 未鉴权，不是新 bug：** 它 gh api 推 2 仓，每 op `retry(5, backoff3)`；无 token → 每 op 401 烧 ~45s 重试，blob/tree/commit/refs 一大堆 op + 积压 → 累计超 3600s 被杀。token 到位后首次清大积压可能仍 >3600s，需给该 job 单独调超时（**全局 `cron.script_timeout_seconds` 动不得，影响所有脚本 job**）。

## gh 推型脚本 3600s 预算加固
- 任何 cron no_agent 的 gh 推型脚本（tick_push/github_sync/看板哨兵）每个 gh api 子进程调用**必须带小单调用超时（45s 量级）** + 有上限的重试：外网挂起/无 token 时连接可无限挂住，长单超时 × 重试 × 多环节会把总时长顶穿 3600s 脚本预算，症状从「快速 exit=6」劣化为「script timed out after 3600s」。改完实测一次端到端总耗时（token 墙下应 2-3min 内收敛回正常失败码）才算收口。

## ATE python 取 MT5 K线 坑
- `C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe` **无** `m.time_to_value`。
- `copy_rates_from_pos` 返回 **numpy 结构数组**（非 dict 列表）：取值用 `arr['time'][-1]` + `time.localtime(...)`，**不是** `arr[-1].time`（会 `AttributeError: 'numpy.void' object has no attribute 'time'`）。
- 只读探 K线模板：`initialize → symbol_select(sym,True) → copy_rates_from_pos(sym, TF, 0, N) → shutdown`。

## K线不落本地文件
- 走 MT5 IPC copy_rates 活读；`data_health INSUFFICIENT_DATA` 是 MT5 侧取数不足（终端 Invalid account 断线期），**非**本地文件缺。
- 11-03 23:00 实探 XAUUSD/BTC/ETH/US500/AAPL/TSLA/POLUSD：H1 到 01:00、D1 到 11-03 全有数据 → INSUFFICIENT_DATA 多为终端断线期陈旧判定，下轮全链扫描会重评，**别当新故障反复挖**。

## 泄漏单处置先例（2026-11-03）
- live24 泄漏 SELL #663837800（XAUUSD 0.01手 @3927.57）：L4 移 SL 到保本 3928.5 → XAU 回抽后 SL 触发，只亏 **-$0.93**（余额 898.21→897.28 分毫不差），不是全 SL 的 -$25。保本保护把亏损锁到一点点。
- 账户 3 连亏 → 24h 冷却（到次日 ~06:18 前不开新仓）；币系 exp_r 总闸冻结；LIVE_TRADING=False 全程 DRY-RUN。最小影响处理（不平活仓、只移 SL/挂闸），合用户一贯偏好。
