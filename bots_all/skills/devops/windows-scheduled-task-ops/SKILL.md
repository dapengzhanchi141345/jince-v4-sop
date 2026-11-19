---
name: windows-scheduled-task-ops
description: Use when 重建/注册/诊断 Windows 计划任务（守护任务、开机自启、周期触发）.
version: "1.0"
author: hermes
license: internal
metadata:
  hermes:
    tags: [windows, scheduled-tasks, powershell, daemon, guard]
    related_skills: [jince-watchdog-noise, windows-system-tweaks]
---

## When to Use
- 需要新建/重建 Windows 守护类计划任务（开机自启 + 周期触发）。
- 任务消失、不响应的诊断与重建验收。
- 压缩/延长守护任务间隔时的正确改法。

Windows 守护类计划任务（注册/重建/诊断）速查：

## 注册任务（PowerShell Register-ScheduledTask）
- git-bash 的 `schtasks` 会 Permission denied——**注册/查任务一律走 PowerShell**。
- 触发器组合范式（以守护任务为例）：
  ```powershell
  $trig = New-ScheduledTaskTrigger -AtStartup -RepetitionInterval (New-TimeSpan -Minutes N) -RepetitionDuration (New-TimeSpan -Days 365)
  $act  = New-ScheduledTaskAction -Execute <pythonw路径> -Argument '<脚本绝对路径>'
  Register-ScheduledTask -TaskName <名> -Trigger $trig -Action $act
  ```
- `AtStartup` + `RepetitionInterval` 组合 = 开机跑 + 之后每 N 分钟重复；`RepetitionDuration` 默认 1d 会停，要「永远」写 365 天（见下方坑：`[TimeSpan]::Max/MaxValue` 直接注册失败）。
- **常驻守护自愈范式（重启≠自愈，11-15 实踩）**：`RestartInterval/RestartCount`（restart on failure）只覆盖「任务运行中失败」——进程被 kill 或 exit 0 时动作=完成，任务回 Ready 不重启，守护直接断。正解 = 加一个 1min 周期触发定期重跑 Start（开机触发保留）+ **应用侧单实例锁**（旧实例活→新实例自退；旧实例死→新实例接管锁）= 活的不重开、死的 1min 内拉起。验收：杀旧实例后 1min 内读锁文件 pid 更新且活体数=1。
- 跑 headless python 用 pythonw.exe（不弹窗）；跑会弹窗的才用 python.exe。

## 诊断任务状态
- 任务消失/不响应的标准三步：
  1. `Get-ScheduledTask -TaskName <名>` → 查 `State`（Disabled/Ready）；
  2. `Get-ScheduledTaskInfo` 看 `LastTaskResult`（0=成功, 267014=任务被禁用时跑, -2147020576=超 stop 时限被强杀=挂死被杀, 267011=参数错；**从未跑过的新任务 LastTaskResult=267011 且 LastRunTime=1999/11/30 是占位初值, 不是参数错**）；
  3. `Get-ScheduledTask | Select -ExpandProperty Actions | Format-List` 确认 Execute/Argument 没被改。
- **他方声称"已重建"不认**——必须 `Get-ScheduledTask` 实读存在 + State=Ready + 手动 `Start-ScheduledTask` 后日志出新拍才算活。
- **任务消失后先查审计日志再重建**：再消失=有人/有软件在删，重建不查清理者=白建。Security log 里 EventID 4698/4702 可查谁在改任务（安全软件静默清理族常见）。
- **任务消失的另一类成因=触发源主动迁移（11-16 实踩）**：活被迁到别的调度器（Hermes cron no_agent 等）后旧计划任务被删，而下游验证闸仍预期旧触发根（如 taskeng 父链追到调度器根）→ 闸**永久 FAIL**，表象像"进程异常"。重建前先 grep 下游闸/验收脚本里的触发源假设（父链根、任务名），方案=恢复原触发根 + 备份调度器靠脚本单实例锁防双跑 + 闸规格一字不动。查全表用 `schtasks /Query /FO CSV | grep -ai <词>`（输出 GBK 非 UTF8, 不加 `-a` 会 "Binary file matches" 吞结果）；排除词别写 "hermes" 类, 会把金策系任务行滤掉漏看。
- **注册长时限任务**：`-Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours N))`——后台不限时回测类任务必加 StartWhenAvailable（错过触发点补跑）+ 足量 ExecutionTimeLimit（默认 7d 够, 长回测 10h 量级显式写）；默认身份"只在用户登录时运行", 机器 00:10 有登录即可, 别改 SYSTEM（父链口径变, 宿主闸追根会失配）。

## 重建后的验活顺序
Start-ScheduledTask → 等一拍（间隔内）→ 读该任务的产物日志（如 event_guard.log 出新拍行）→ 才算闭环。只看任务表"Ready"不算活（Ready 只说明可触发，没证明触发了）。

## 坑
- 守护任务的间隔压缩（如 15min→5min）改的是触发器 `RepetitionInterval`，不是脚本内 sleep——两者别混。
- 任务里跑 python 脚本时，脚本路径必须绝对路径（任务 cwd 不是你以为的目录）。
- `RepetitionDuration` 传 `[TimeSpan]::Max`/`MaxValue` 会超出任务 XML 时长上限，Register-ScheduledTask 直接失败（报 Duration XML 超范围错，且若命令里先 Unregister 了旧任务=任务已被摘除需重建）；永远重复=写 `(New-TimeSpan -Days 365)`。
- 重注册脚本里 Unregister/Register/Start 三步连写：任一步 PowerShell 语法/参数错=整条命令**一条都不执行**（PS 先整体解析）——多步任务注册拆成独立命令逐步验活，别一条长命令赌全链。
- MSYS/git-bash 调 PowerShell 时参数里的 `$` 会被展开——复杂 PowerShell 一律写 .ps1 落盘再 `powershell -NoProfile -File x.ps1` 跑。
- PowerShell 单行条件退出的正确形态是 `if (cond) { exit 0 } else { exit 1 }`；`exit 0 if (cond) {...}` 是无效语法（PS 没有 exit-if 中缀）——写错时整条命令恒非零退出，用 `check=True` 的活体检查会永远判"死"→ 自愈门无限重启采集器/进程（11-14 实踩）。写活体探测 one-liner 后先单独跑一遍，确认 cond 真/假两分支的退出码各是什么再挂进闸。
