# EA 一体化执行层：开仓路径盘点与执行通道交接
> 何时用：MT5 多开仓路径并存、要加/退役/交接执行层（EA 腿、轮询 runner、引擎脚本腿）、或出现「嵌入 MT5、跟交易系统融为一体」类指令时。用户架构偏好（李彦明纠正过）：执行层=终端内 MQL5 EA（tick 级），Python 轮询 runner 只做观察/攒 OOS，不要再给「N 秒轮询开单」当方案。

## 单一执行通道铁律
接入任何新执行层前，先盘点全部现存开仓路径，统一到一个执行通道、其余 HALT/降 DRY，再交接。多路径并存的三种事故形态：同 magic 对锁（双向挂同一品种）、双份敞口（同向重单）、急停归因不了（kill switch 白名单没覆盖）。magic 号必须在 magic_registry.json 唯一登记；发现多腿共用一号（其它 agent 加的腿没登记），先重新分配再动执行。

## 现役路径盘点表（动手前逐项实读核对，勿凭记忆）
| 路径 | 文件/进程 | magic | 降级/急停开关 |
|---|---|---|---|
| jince_bot 15s 轮询 runner | jince_bot/runner.py + 启动盯盘.bat + jince_selfheal_watchdog.py | 20261020 | 降 DRY：bat 与看门狗 Popen 配方去 `--execute`、`JINCE_BOT_LIVE=0`（双闩缺一自动 DRY）；急停=jince_bot/kill_switch.py |
| live24 24h 引擎腿 | E:/GoldstrategyEngine/tools/jince_live24.py | 20261103 | 停开新仓=建 `data/LIVE24_HALT`（内置开关；进程可留无害运行，杀进程排 23:00 调试窗） |
| EA 执行腿（终端内 tick 级） | E:/GoldstrategyEngine/mql/EA_L5_Exec.mq5 + multi_agent/trading/ea_advisory_feed.py | 20261103 | 双闩=引擎 armed flag `data/ea_exec_armed.flag` + 图表 InAllowExec；急停=tools/jince_kill_switch_ea.py |
| 引擎 guardian 主链 | guardian_executor.py | 15 白名单 | 总闸 LIVE_TRADING_ENABLED（默认 False） |

## 一体化交接步骤（按序）
1. **枚举开仓路径**：grep tools/ 与 rd_queue（其它 agent 会在夜间加腿，注释/台账是线索）+ tasklist 找 python 活体 + 各 audit jsonl 的 pid；对 magic_registry.json 找未登记/撞号。
2. **策略腿迁进 feed 而非停掉**：引擎 30min 循环算全部决策字段（side/lot/sl_dist/tp_dist/spd_ref/magic_fuse），EA 只读照做、MQL5 零重推公式（0 公式漂移）。OOS 已验证的腿照原参数+原闸源写进 feed（如 XAU 突破腿：M15 收线、简化DI差≥ADX 阈、20bar 突破±0.1%、MA5/20 同向、SL/TP 倍数、点差>1×ATR 拒单、magic 当日已实现亏≥2% 熔断），其闸源（_exp_r_gate 单路径 gate_override）原样引用，证据链不断。
3. **旧执行通道用自带开关停/降**（最小影响、可逆）：live24→HALT 文件；runner→DRY 配方补丁（bat + 自愈看门狗 Popen 参数都要改，只改 bat 会被看门狗复拉回 LIVE）。
4. **急停覆盖新通道**：每腿一个专用 kill switch（只碰本腿 magic、默认 DRY、账号漂移/实盘服务器名拒动、审计 jsonl）。改 magic 分配时同步 kill switch 白名单与 registry，否则急停有盲区。
5. **台账**：magic_registry 备注、rd_queue 项销账（closed+迁移动作留痕）、状态卡顶部新条目、24h 播报键。

## 双闩 arming 时序（安全设计）
- 引擎闩（armed flag 文件）可预先写好：EA 侧闩（图表 InAllowExec）未勾之前 0 发单，预写零风险；
- EA 闩=用户唯一手动步：MT5 把 EA 拖上品种图 + 勾 InAllowExec + 允许算法交易（图表属性跨终端重启保持，EA 自动复挂）；
- 生效延迟=下 30min feed（feed 行带 armed 字段）；解除=删 flag/置 0，同样等下 feed——**立即急停走 kill switch，不等 feed**。

## 已知坑
- 自愈看门狗探活靠 wmic 命令行匹配 + watch_log mtime：相对路径新实例探活 0 命中但日志 fresh=「误报静默跳过」，日志 stale=按新配方复拉；手动拉的实例若没命中探活，可能被下一轮复拉出双实例——单实例锁 dup_exit 去重是设计行为；patch 配方在前、让看门狗自然拉在后。
- feed 里 MT5 短读（initialize→copy_rates/history_deals→shutdown）放在引擎 30min 循环内串行跑可接受；多进程并发 IPC 才是冻死坑（TIMECAP 根因），别在 5min 高频路径加 MT5 读。
- 急停/kill 类脚本写盘审计用 append jsonl，GBK 管道铁律不变（子进程 stdout 只出 ASCII）。
- 日亏/magic 熔断了账口径=只数 OUT/OUT_BY（已平）deals：数 IN（开仓）deals 的 profit≈0，熔断永不触发还给人"熔断了"的假安全感——迁移旧腿的熔断逻辑时先核它对账 entry 类型，已实现盈亏才能"一亏即停"。
- magic 熔断只在"账号漂移/非 demo"时置 1（fail-closed）；MT5 短读失败只降级该腿（side=none + STALE 留痕），**不置全局熔断**——否则每次 IPC 抖一下 EA 就被锁 30min，与显示层 fail-open 的设计相悖。
- Experts 目录里发现未登记的 magic、源文件本地找不到、ex5 字符串全混淆（读不出任何标识）的 ex5=权限状态未知：定性（删除 or 登记，L4 拍板）前**禁止挂图**，并把"急停白名单是否覆盖它"一并核查，否则急停盲区+1。
