# 金策 基建/运维坑 & 根因台账（2026-11-03 沉淀）
> 处理金策 cron 异常（WinError 2/267、chief 心跳冻结、回测空件、引擎夜间断流、看门狗探针停更）时先读本文件。30 秒定位，不重解码。

## 1) 三个 JinCe Windows 计划任务会被反复停成 Disabled（chief 心跳冻结第一排查点）
- 任务：`JinCeAutoCycle`(全链驱动) / `JinCeWatchdog`(巡检) / `JinCeEventGuard`(5min 事件快通道)。
- 现象：某机制或风控 LEVEL=2 全冻结时把它们停成 `Disabled`；一停 → 全链/5min 快通道/chief 心跳断流、不出新拍（auto_cycle.log 无 `[全链自动运行完成]` 新条目）。
- 诊断：`powershell -NoProfile -Command "Get-ScheduledTask -TaskName 'JinCeAutoCycle','JinCeWatchdog','JinCeEventGuard' | % {$_.TaskName+'='+$_.State}"`。
- 修复：`Enable-ScheduledTask -TaskName <t>` + `Start-ScheduledTask -TaskName <t>`，然后验新拍（auto_cycle.log / event_guard.log 出新条目）。
- 2026-11-03 实测：三个全 Disabled，重启用后全链 08:20/08:24 恢复出拍。**每次 chief 心跳冻结先查这三个，别只怪 IPC。**

## 2) 共享终端 8736 的 MT5 IPC 互斥 = 夜间断流/回测空件根因
- 回测引擎 与 实盘 OOS runner / live24(jince_live24.py) 共用终端 8736 → MT5 IPC 层互斥卡死 →
  ① 00:10 每日回测出空件（copy_rates TIMECAP fail-open、n=0、FAIL_NO_DATA）；
  ② OOS runner / live24 引擎凌晨反复死（看门狗自动复拉，治标不治本；今晨 runner 32900→9252→79936、live24 47480→13184）；
  ③ 风控闸 LEVEL=2 全冻结（价源断）拖慢全链几十分钟。
- 根治方向 = @strategy-rd 拍板 **(b)：回测改读本地缓存 K 线（不走 live IPC），与实盘 runner 物理隔离**；引擎侧改动尚未落地，落地前 00:10 仍会出空件、看门狗仍要反复救。

## 3) gh (GitHub CLI) 全路径 + 5 件 gh 活卡 token
- gh 装在全路径 `C:\Users\Administrator\ghbin\bin\gh.exe`（winget 挂掉后手动装的）；**裸 `gh` 不在 cron 会话 PATH**，4 脚本已改全路径：`jince_tick_push.py` / `jince_github_sync.py` / `jince_dashboard_sync_guard.py` / `sites_deploy_12indep.py`。
- 5 件 gh 活（行情喂 tick_push / 看板哨兵 dashboard_sync_guard / 夜间全推 jince_github_sync / 12站 sites_deploy_12indep / 技能全推 skills_github_sync）**现统一卡在等用户 GitHub token**（`gh auth login --with-token`，仓主 dapengzhanchi141345）。token 一到 → 全绿。

## 4) 技能全推的 git "dubious ownership"
- `skills_github_sync.py` 把 skills 镜像到 `E:/workbuddy/国外模型/hermes/_skills_mirror`，该仓属主是旧不可映射 SID → git 安全检查 `fatal: detected dubious ownership` → `git ls-files 失败`。
- 修复：`git config --global --add safe.directory "E:/workbuddy/国外模型/hermes/_skills_mirror"`（**必须 --add 追加**，该仓已有 6 条其它 safe.directory 值，别覆盖）。修完 git 阶段通，下一步 gh api 推仍卡 token。

## 5) 看板哨兵 [WinError 267] 是表象，别修死路兜底
- `jince_dashboard_sync_guard.py` 的 `git push` 兜底 cwd 硬编码 `C:\Users\ASUS\jince-dashboard`（老用户 profile，现在跑在 Administrator、该目录不存在）→ `[WinError 267] 目录名称无效`。
- 这条 git 兜底按设计是"最后兜底、基本必拒"的死路；主路是 gh api（卡认证）。**token 配好后 gh 主路通、兜底根本走不到，WinError 267 自然消**，不要去造 ASUS 目录 / 改死路兜底。

## 6) 看门狗"Running 僵尸"签名：探针停写 + 锁在 tick + LastTaskResult 未终 = 救场腿死
- **删除变体（与僵尸是两种病）**：`Get-ScheduledTask` 报 Not Found = 任务被整体删除——「杀掉 X → 等下个 5min 拍自愈」类执行序立即失效、自动救场腿全哑。任务族在位核对 + ETL/MI 审计 + LastTaskResult 解码表 + 删除归因/重建纪律，照 `references/scheduled-task-forensics.md` 走。
- 三点签名：① `data/network_probe_last.json` mtime 停数小时（最后内容停在旧时间戳）而 ② `data/jince_watchdog.lock` 仍在被 tick ③ 任务 state 钉 `Running` → 看门狗某拍卡死不退出，探针（"拉终端/拉网关"救场腿）停写。**State=Running 且 LastRunTime 已过去数分钟 = 僵尸**（10-06 叠死 4h 同族）。
- `LastTaskResult` 判读（十进制先转 hex）：`2147946720 = 0x800710E0` = 任务未结束/仍在跑（僵尸签名）；出现 `0x80070FF0` = 撞 15min 限时被超时杀。
- 影响面口径（报用户用）：30min 主链（新进程）自愈照保读源，但**夜间断终端/断网关时自动救场腿是哑的**——别说"看门狗正常"，说"救场腿失效，排窗根修"。
- 根因方向：卡在没有独立 timeout 的子进程（10-05 教训：探活子进程必须逐个带 timeout，任一无限挂起 = 整个看门狗不写盘）；挖之前**先核盘上脚本 mtime**——脚本被 sibling bot 覆盖丢探针写逻辑有前科，先确认写逻辑还在再查挂起。
- 只读例行验法：`powershell -NoProfile -Command "(Get-ScheduledTask 'JinCeWatchdog') | Get-ScheduledTaskInfo | Select TaskName,State,LastRunTime,LastTaskResult"` ＋ `ls -la --time-style=+%m-%d\ %H:%M data/network_probe_last.json data/jince_watchdog.lock` 对比 mtime。

## 账号快照参考（2026-11-03）
- 60137964 (DEMO 当实盘练)：净值 894.89 → 902.33(L4_C1_CLOSE 平 2 张 +$7.44) → 898.21(0 仓)。live24 引擎在 XAU/BTC/ETH 上 0.01 手 DEMO 开平循环、SL/TP 服务器端随单、属授权活，引擎反复死由看门狗自愈。
