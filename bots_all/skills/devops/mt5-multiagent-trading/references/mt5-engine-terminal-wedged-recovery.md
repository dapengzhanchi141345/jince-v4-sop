# MT5 引擎终端 wedged 恢复 / 探针超时容错 / gateway flapping 诊断

金策引擎终端 = `C:\Program Files\TMGM MT5 Terminal\terminal64.exe`（demo 60137964 默认 datafolder）。PID 经常变（终端会自重启），**禁止按 PID 认亲/判被误杀**（见 SKILL.md「MT5 终端拓扑 & 登录铁律」）。本页补三种 2026-10-06 高频故障的判定+处置。

## 1. 终端 wedged（多进程抢 + 持久 IPC 超时）
- 现象：节点②实读/`live_ticks` 拉不出、`mt5_launch.py -c "m.initialize()"` 反复 `-10005 IPC timeout`。
- 判据：`tasklist /FI "IMAGENAME eq terminal64.exe"` 出现 **>1 个 PID**（多个终端互相抢 IPC）且 initialize 重试多次仍 -10005。**特例（单 PID 也能 wedged）：引擎终端进程还活着（PID 不变）但 IPC 层卡死，initialize 间隔 15s 重试 3 次仍 -10005（含软恢复 wait 10s 后重试）= 单进程 IPC wedge，处置同本节但只 kill 引擎这一个实例，不碰 friend 观察终端（`E:\mt5_friend_observer` 是用户专用手登终端，永不 taskkill）。**
- 处置（**仅当实盘 0 挂单 0 持仓时才安全；先实读确认再动手**）：
  1. 实读确认 0 挂单 0 持仓（有单先走最小影响：撤单归 0 或先报后动，别硬重启）。
  2. `taskkill /F /IM terminal64.exe` 全杀（清掉抢 IPC 的多进程）。
  3. `cmd //c start "" "C:\Program Files\TMGM MT5 Terminal\terminal64.exe"` 拉**一个**干净实例。
  4. 等 40–90s 让终端连上 broker + 登录。
  5. 验：`initialize()=True` + `account_info().login==60137964` + 品种有 tick。
- 刚拉起后首次 initialize 常先报 `-6 Authorization failed`（GUI 重登中），等几秒重试即通，**别误判成账号挂了**。这与「禁止 poke 健康终端」铁律不冲突：这里只对 wedged/多进程态做一次性的「归一到单进程」，不是反复杀健康终端。
- 若实盘有持仓/挂单：不硬重启，改走最小影响（撤单/改 SLTP 归 0 后再重启），大动作先报后动。

## 2. 探针/巡检的 MT5 超时要容得下终端重启·重连窗口（治假报警）
- 任何探 MT5 的看门狗/巡检/节点，**探活子进程超时 ≥ 终端最坏重启·重连时长（~90s）**，否则终端一抖就出假异常：
  - `jince_auto_patrol.py` MT5 实读子进程 timeout：45s→90s。
  - `jince_node.py` `_ate_mt5_live_read` 默认 timeout：30s→90s。
  - 真卡死（90s 仍 -10005）照旧 fail-open 降级明示，不静默、不崩 30min 全链。
- 巡检报警「MT5 实读降级/终端可能挂了」时：先独立用 `mt5_launch.py` 实读一次区分「偶发重启窗口（重试即通）」vs「持续故障（要重启终端）」，别把重启窗口当故障刷群。

## 3. OpenBLAS 内存墙（多腿同拍撞 Memory allocation failed）
- 现象：30min 全链某拍多条腿（CIO/币圈/股指日内）子进程全 `退出码=1`，stderr 头行 `OpenBLAS error: Memory allocation still failed after 10 retries`；此时宿主物理内存紧张（`Win32_OperatingSystem` Free<1GB、使用率 89%+）。
- 根因：每条腿子进程 import numpy/OpenBLAS 默认开满核线程，低内存时逐个撞墙；**不是并行争抢——auto_run_cycle main() 三腿本就串行 subprocess.run**，报"改串行"时先 grep 确认无 concurrent/ThreadPool，别白改。
- 治法（2026-10-21 实修）：父 + 各腿入口顶部 `os.environ["OMP_NUM_THREADS"]="2"` + `OPENBLAS_NUM_THREADS="2"`（限线程压峰值，双保险）。改 4 入口：auto_run_cycle.py（父，env 被子进程继承）/ multi_agent/cio_orchestrator.py / trading/crypto_pending.py / trading/equity_pending.py。
- 验证铁律：跑一拍后**按行边界精确取新拍段**（前一个"全链自动运行完成"行到本拍完成行之间）grep OpenBLAS 报错数=0 + 无"退出码=1"。粗窗口（前 400 行）会混进上一拍旧报错误判"修复失败"。
- 线程=2 只压峰值不增内存；内存本身紧张是宿主环境面（`Get-Process | Sort WorkingSet` 找大户），非交易链内问题，不因此动交易逻辑。

## 4. gateway flapping（PID 反复变）诊断
- 一个观察窗口内 `hermes gateway status` 的 PID 换 2+ 次 = gateway 在反复重启（flapping）。
- 证据源：`hermes/logs/agent.log` 的 `gateway.lifecycle_ledger` 行（`Previous gateway life (pid=…) exited UNCLEANLY … SIGKILL / OOM / VM death`）+ `hermes/gateway-starts.log` 时间戳排重启节奏。
- 此时巡检/看门狗报的「gateway 未运行」是**真重启空窗、非探针措辞假警报**——别默认当误报；`jince_watchdog.py` 的 `hermes gateway start` 自拉就是恢复手段，**连两次 status 同 PID 才算稳住**。
- 根因常是内存大户（WeMeet/Hermes 桌面/WorkBuddy）挤爆触发 OOM-kill：`Get-Process | Sort-Object WorkingSet` 找压力源；gateway UNCLEANLY exit 的 suspected_oom 字段也印证。
- 区分：gateway 空窗期节点迟发/看门狗点名「chief 超窗」多为同一波（全链要连 gateway+MT5），根在终端/网关抖动而非 chief 死机；08:16 型全链「完成」行补上即消。
