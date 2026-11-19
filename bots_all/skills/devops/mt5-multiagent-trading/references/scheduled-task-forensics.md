# JinCe 计划任务取证（在位 / ETL / LastTaskResult / 触发依赖）

## 什么时候读
报「看门狗腿哑了 / 自动恢复不生效 / 心跳停写 / 任务没触发」时，先跑本节再谈僵尸收尸——任务可能**已被整体删除**（Not Found）或**配置回退**，与「僵尸卡死占锁」是两种病，处置不同。

## 步骤（PowerShell，逐条实读别假设）
1. **任务族在位核对**：`Get-ScheduledTask | Where-Object { $_.TaskName -like 'JinCe*' }`。某任务 Not Found = 被删，不是卡死。被删任务的「下个触发」永远不会来——任何「杀掉 X → 等下个 5min 拍自愈」的执行序先验任务还在。删除归因（谁删的）没报出来前不重建、不猜。
2. **ETL/MI 审计**（历史加固基线=短 ETL + IgnoreNew，会回退，以实读为准）：
   ```powershell
   foreach ($n in 'JinCeAutoCycle','JinCeEventGuard','JinCeWatchdog') {
     $t = Get-ScheduledTask -TaskName $n; $s = $t.Settings
     $etl = if ($s.ExecutionTimeLimit -gt [TimeSpan]::Zero) { $s.ExecutionTimeLimit.ToString() } else { 'None' }
     "$($n) ETL=$etl MI=$($s.MultipleInstances) State=$($t.State)"
   }
   ```
   - ETL=PT72H/None + MI=IgnoreNew = 单次 run 可挂几十小时且新触发全被吞 → 僵尸占锁、探针文件停写（对照 network_probe_last.json 等探针文件 mtime）。
   - PS 语法坑：ForEach-Object 里 `$(if(...))` 表达式式报 CommandNotFoundException，必须写 `$x = if (...) {...} else {...}` 语句式。
3. **LastTaskResult 解码**（HRESULT）：十进制值 = 0x80000000 + Win32 码，先转 hex 再定性：2147946720 = **0x800710E0** = 运行未结束/仍在跑（僵尸签名，与 State=Running＋锁文件 tick 对平）；2147946480 = 0x80070FF0 = 操作超时被限时杀掉（撞 ETL）；0 = 健康。非 0 一律先十进制转 hex 再定性，别凭十进制码猜「卡死」。
4. **锁文件对平**：单实例锁 mtime 停更 + 任务 State=Running = 僵尸持锁；锁 mtime 在动但探针文件停写 = run 卡在 probe 段前（某个 subprocess 没带独立 timeout）。
5. **重建纪律**：重建被删任务带短限时参数（ETL 短 + 单实例策略显式）走 Register-ScheduledTask，重建后以 LastRun 出新拍验收才算活；停层/重建属用户授权域，先报后动。

## 销账/派单要件写"重启循环加载新码"：先定循环宿主拓扑，别假设存在要重启的进程
要件说"循环重启/重启加载新码"时，先问"这个循环宿主是**每拍新进程**还是**长驻进程**"再动手：
- **短命拍循环**（Windows 计划任务每 30min 拉一次单轮脚本，跑 2-3min 即退；如 \JinCeAutoCycle）→ 每拍天然从磁盘拉最新码，"重启载新码"要件**下一拍自动满足**，无进程可重启。实读销账三件：①计划任务在位（`Get-ScheduledTask` 查 next-run，见步骤 1）；②新码文件 mtime 早于下一拍时刻；③下一拍有产物活动（循环日志末行时间戳/tick 文件刷新）。
- **长驻进程**（引擎/循环不退出）→ 才需要真重启：走该引擎的锁协议（每魔一号锁/O_EXCL 独占锁），重启前按锁文件+在跑进程核一遍防自造双实例；手动 spawn 与哨自动拉撞窗 = 自造双实例。
- **口诀**："重启"要件先定位宿主拓扑——短命拍=只需实读销账不动手；长驻=动手重启且先查锁。查不到宿主进程 ≠ 没在跑（短命拍单轮跑完即退，`Get-CimInstance Win32_Process` 常态查空）；跨方循环绝不用进程名匹配杀，只按自己 PID 记录/魔号锁杀。
