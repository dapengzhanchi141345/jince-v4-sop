# 金策监控·快速衔接（当前卡点快照，免重新诊断）

> 状态随时间变，先读 state.cmd/看板再认下面的卡点；过期条目删掉。

## GitHub 同步 5 件（行情喂/看板哨兵/技能夜推/12站/夜间全推）
- 全卡 **gh 认证 = 等李彦明的 PAT token（dapengzhanchi141345）**。token 一到，主路 gh 全绿。
- gh CLI 全路径：`C:\Users\Administrator\ghbin\bin\gh.exe`（脚本已改全路径调用，别再依赖 PATH）。
- **看板哨兵报 `[WinError 267] 目录名称无效` = 死路 git 兜底踩不存在的 `C:\Users\ASUS\jince-dashboard`，忽略它**；真卡点是 gh 认证（看 gh api 443/拿不到 HEAD）。token 到位后 gh 主路成功、267 自然消。
- 行情喂 exit=6「gh api 拿不到远端 HEAD…本地已写」= 同上，本地 tick 已落、只差推远端（等 token）。

## MT5 共享终端 IPC 间歇冻
- 现象：行情喂「MT5 实读 0 品种(终端 IPC 断)」/ 全链 50min 空档 / 风控闸 LEVEL=2 全冻结；**会自愈**，IPC 一恢复 tick 自动追新、全链补拍。
- 铁律（已在 SKILL.md 顶部）：**禁止 spawn/kill terminal64.exe，禁替用户登录 MT5**；终端用户手维护，agent 只读 attach。治不了 IPC 只能盯。
- 根治：@strategy-rd 方向 (b)＝回测/喂线走本地缓存 K 线、不跟实盘抢同一终端 IPC（白天做）。

## 其它自愈型（看门狗在救，根因未除）
- `jince_live24` 引擎反复死（夜间断流模式），看门狗自动拉起，仓位安全；根治同上 IPC 互斥。
- 节点投递卡队列（asia_open/asia_midday 卡>30min）＝纯投递延迟，内容在 discussion_log、零丢失、22:00 兜底销账，非新故障。
- gateway 重启窗口（PID 变）会让当期 cron 报 GatewayUnavailableError；gateway 起来后补跑即绿（`hermes cron run <id>`）。

## 诊断顺序（收到金策异常先走这步）
1) 先读 `E:\AgentCommons\bin\state.cmd`（实盘真值）+ 看板；2) 全链心跳 `E:\GoldstrategyEngine\data\auto_cycle.log` 尾（`[全链自动运行完成]`）；3) 三定时任务 `JinCeAutoCycle/JinCeWatchdog/JinCeEventGuard` 是否被停成 Disabled；4) 异常对照上面卡点表，对得上=已知模式不重查，对不上才深查。
