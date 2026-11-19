# 运维排障速查（2026-11-03 夜~晨沉淀）

## 1. gh CLI 只有全路径（cron 会话 PATH 无裸 gh）
- gh 全路径：`C:\Users\Administrator\ghbin\bin\gh.exe`；cron 会话调裸 `gh` → `[WinError 2] 系统找不到指定的文件`。
- git for Windows 未装（只有 git-bash 的 /mingw64/bin/git），裸 `git` 在 cron 会话也可能 WinError2；看板哨兵的 `git push` 兜底还会踩陈目录 `C:\Users\ASUS\jince-dashboard`（不存在）→ WinError 267，属死路兜底表象。
- 金策 4 个 gh 脚本已改全路径：`jince_github_sync.py` / `jince_tick_push.py` / `jince_dashboard_sync_guard.py` / `sites_deploy_12indep.py`；`skills_github_sync.py` 的 gh 从 jince_github_sync 导入（自动受益）。新写 gh 调用脚本一律全路径。
- gh 未认证时 5 件 GitHub 活（行情喂/看板哨兵/金策夜间全推/12站部署/技能全推）全卡 "gh api 拿不到远端 HEAD (已重试仍全挂) 本地已写"（tick_push exit=6 降级态，本地数据照常刷）；**李彦明供 token 后 `gh auth login --with-token` 一条命令全绿**。

## 2. JinCe 计划任务会被反复停成 Disabled（全链/快通道静默死亡根因）
- 现象：JinCeEventGuard 03:03 被停、JinCeAutoCycle 02:53 被停（LastTaskResult=267014）、JinCeWatchdog 被停 → chief 全链心跳冻结 02:29、5min 事件快通道静默 36min+。原因未明（疑风控 LEVEL=2 全冻结联动或维护动作误停）。
- 排障顺序：全链心跳冻结（watchdog 点名 chief）→ 先 `powershell -NoProfile -Command "Get-ScheduledTask -TaskName 'JinCeAutoCycle','JinCeWatchdog','JinCeEventGuard' | % { \$_.TaskName+'='+\$_.State }"` 查状态 → 发现 Disabled 就 `Enable-ScheduledTask -TaskName <名>` + `Start-ScheduledTask -TaskName <名>` 恢复 → 再查 IPC。
- 恢复后全链 ~30min 一拍自然追上；watchdog 点名"超窗"可能是抓在 IPC 空档（见 4），先核对 auto_cycle.log 最后拍时间再动手。

## 3. git 换户口 dubious ownership
- `git config --global --add safe.directory "<repo>"`，**必须 --add**（safe.directory 已有多值，单值设置报 `cannot overwrite multiple values`）。已加：`E:/workbuddy/国外模型/hermes/_skills_mirror`（技能全推 git 镜像仓）。

## 4. MT5 IPC 间歇冻死根因（@strategy-rd 实读，2026-11-03）
- 根因：回测引擎 + 实盘 OOS runner 共终端 8736 → MT5 IPC 互斥 → copy_rates 握手白磨。症状群：风控闸 LEVEL=2 全冻结（mt5=False 价源断）/ 全链 50min+ 空档 / 回测 3060s TIMECAP 空件（3 品种 n=0，backtest_edge.json 空件）/ 夜间断流（runner 32900→9252→79936、live24 47480→86868→13184 反复死，看门狗自愈拉起；持仓 SL/TP 在服务器端，引擎死不裸奔）。
- 根治方向已拍板 **(b)**：回测走本地缓存 K 线、引擎读文件不碰 live IPC（非破坏、不断 OOS 证据链）；@strategy-rd 落地中。落地前 00:10 每日回测会持续出空件（结构性，勿反复重跑刷屏）。
- 孤儿回测引擎卡死数小时后会自行 TIMECAP 超时退出（不产新 edge）；判卡死先看 backtest_engine 进程数 + backtest_edge.json mtime；卡死期间占终端 8736 拖累实盘 IPC，杀前须李彦明确认（taskkill 有安全闸）。

## 5. 判读口诀（防误报）
- 看板哨兵 [WinError 267] = git 死路兜底表象；tick_push exit=6 = gh 认证挡路+本地已写（降级非故障）；gateway=probe-output-abnor/fail-open 不判挂；watchdog 点名先核台账最后拍时间（可能已自愈）；巡检/播报里"连亏 N 笔/回撤"属引擎正常循环，未触 10% 日亏熔断不升级。
