# 金策 cron 告警消防水枪分诊（群聊里 5/10/15min 告警成堆时先读本条）

金策一批 no_agent 5/10/15min 定时 job（行情喂 / 看板同步哨兵 / 24h心跳看门狗 / 节点看门狗 / 自动巡检 / 2h效率播报 / 节点深析）每拍都往群聊投递。基础设施一坏就变成"近重复告警洪水"。目标：不逐拍重诊、不刷屏、把稳定根因归并成 2~3 类一次报清。

## Step 0 — 动手前先判新旧（最省的一步）
- 每条投递带时间戳。先用 `date` 取当前时刻，对比投递时间戳。
- 投递时间 **早于当前** = 旧账迟到的批量 flush（gateway/cron 掉线期间堆的），反映的是那个旧时刻的状态，不是现在。
- 规则：旧账拍**不重新诊断**。只有 (a) 状态自上次探针后真变了，或 (b) 用户要动手，才再探活。
- 判"状态有没有变"的信号：症状字面变了（如 tick 喂从"0 品种"变成"WinError 2"）、看门狗 mt5 从 probe-fail 变 running、chief 完成拍从"数天前"变成"几十分钟前"。

## Step 1 — 稳定根因归并，不逐拍报
- 根因稳定（不飘）时，归并成一张 2~3 类根因图，报一次；之后同型拍一律一句话（"同①/②循环拍，无新信息"）。
- 只在：状态真变 / 用户让动手 / 真新增信号（活持仓>0、账户异常、券商侧事件、站点紧急上线）才单独拎出详报。
- 探针做"一次汇总"而非每条告警一套：`date` + 各根因的关键探针（gh 在不在 / terminal64 在不在 / initialize 通不通）合并成一个 terminal 调用。

## 三类失效判定表（症状→类→查→修）
| 症状 | 类 | 怎么查 | 谁修 |
|---|---|---|---|
| 推送侧脚本（看板同步哨兵 / 12 学科站 / 技能·金策全推 / tick_push 远端步）`[WinError 2] 系统找不到指定的文件` | ① `gh` CLI 缺 | `which gh`；这些脚本跑 `subprocess.run(["gh","api",...])`，gh 没装就 WinError 2 | 装 gh + 接 GitHub token；**不是代码 bug** |
| tick 喂"MT5 实读 0 品种" / 节点"未出实价" / `initialize()` 报 `-10003 MetaTrader 5 x64 not found` | ② 引擎终端没跑 | `Get-Process terminal64`；`m.initialize()` | **李彦明本人**起 TMGM 终端 + 手登 60137964（铁律：agent 不 spawn/不代登录）；agent 只 attach 只读验证 |
| 00:10 回测"产物空窗" / "训练枪静默" / 防复发闸催"手动开第一枪" | ③ 引擎 bug 主动暂停 | 读 `cron/jobs.json` 该 job 的 `enabled` + `paused_reason` | 若 paused_reason 是未修 bug（rc=1 / 胜率虚高腿）→ **不盲开**，升级给 @strategy-rd，修好再接开 |
| 后台长跑 job（00:10 全宇宙回测 / 夜间 GitHub 全推）报 `Script timed out after 3600s` 连崩 | ④ 实际跑时长 > cron 默认超时（非 bug、非 hang） | 读 `cron/jobs.json` 该 job `last_error`（= "Script timed out after 3600s"）+ 对照 stamp 文件实测耗时（如回测 `elapsed_s` 9372s=2.6h）。cron 默认脚本超时=3600s、**无每-job 超时字段**（全局 `cron.script_timeout_seconds`/`HERMES_CRON_SCRIPT_TIMEOUT` 动不得——影响所有脚本 job） | 非代码 bug。治法二选一：① 让 wrapper 快退（~60s）+ 引擎 detach（PowerShell `Start-Process` 父化到系统，cron 杀 wrapper 也杀不死引擎，引擎自跑 2.6h 写产物）；② 修引擎后重启用。先**暂停止血**（防第 N+1 次刷屏+省每晚 3600s 空转） |
| agent 型 cron（日结进化 20:00 等）报 `Response remained truncated after 4 continuation attempts` 0 输出 | ⑤ 执行过程烧超输出预算（**非** LLM 模型故障、也非 job prompt 没加预算铁律——prompt 已写 ≤15 行简报仍截断，因截断发生在 SOP 多步执行过程，不在最终答复） | 读 `cron/output/<jobid>/` 当班 .md（含 Error 段 Traceback，final response 0 字节）确认 0 产出 | **主进程手动代跑其底层 SOP**：prompt 里点名的 SOP 文件（如 `jince_rijie_sop.md`）逐条手动执行，台账留痕 `actor=chief-default + note"cron 截断 chief 手动代跑"`，**投递步（总线/群）照做不可省**（日结断档=进化机制断档）；根因复查排 23:00 调试窗（截断根因=SOP 步数/读取量大，修向=拆 SOP 步或改 no_agent 预读数据落盘+LLM 只汇总）。同 prompt 裸重跑=必再截，别重试 |

## 手动开"被暂停的 cron"之前
- 防复发闸会周期性要求"@hermes 手动开第一枪"。开之前**必读** `cron/jobs.json` 里该 job 的 `enabled` 与 `paused_reason`。
- 若它是因已知未修 bug 被**故意** `enabled=False` 暂停 → 压着别开（盲开=重刷 rc=1/假失败，正撞 paused_reason 想防的），改升级 owner（@strategy-rd）。开枪的前提 = bug 已修 + 数据源（② 终端）在。

## 暂停 / 重启用一个 cron job = 直接编辑 `cron/jobs.json`（hermes CLI 会挂）
- 本机 `hermes cron pause/run` CLI 启动慢、常 >60s 超时——别等它。**直接改 `E:\workbuddy\国外模型\hermes\cron\jobs.json`**（JSON round-trip，只动目标 job 一条，不影响其他 job）：
  - **暂停**：先 `shutil.copy(P, P+".bak_<tag>")` 留备份，然后该 job `enabled=False` + `state="paused"` + `paused_at=<iso now>` + `paused_reason=<人话根因+谁暂停+何时重启用>`。
  - **重启用**：`enabled=True` + `state="scheduled"` + `paused_at=None` + `paused_reason` 更新为重启用理由。写回 `json.dump(ensure_ascii=False, indent=2)`。
- 改完不必重启 gateway——调度器下次读 jobs.json 即生效；已暂停 job 的 `next_run_at` 不会误发。
- `paused_reason` 写**全根因**（多重叠加逐条列 + 谁负责修 + 重启用条件），后续接手的会话/子 agent 读一眼就知道状态，不用重诊。

## 验证"快退+detach 引擎"型 wrapper 的触发坑（2026-11-04 实踩）
- wrapper 设计成 ~60s 快退：防竞写（wmic 查到 backtest_engine 在跑就写 in-progress stamp 不并启）；无竞写则 PowerShell `Start-Process` 把引擎父化到系统（`$env:PYTHONPATH=$null; Start-Process -FilePath <ate-python> -ArgumentList ... -RedirectStandardOutput ... -PassThru`）后写 launched stamp 即退。**引擎幸存任何 wrapper/shell 拆卸。**
- **坑 A 双引擎：** 单次前台触发却起了 2 个 backtest_engine（同秒起）——wmic 防竞写漏判了同窗启动的引擎，或 Start-Process 行 spawn 了两次。触发后**必查引擎进程数=1**（`wmic process where "commandline like '%backtest_engine%'" get ProcessId,CreationDate`）；>1 = 双引擎霸 MT5 IPC = TIMECAP 空卷病根复发，要处置（杀多余需用户点头，见 live24-and-orphan-backtest）。
- **坑 B wrapper 挂死没快退：** 前台跑 wrapper 若被我这边的 terminal 超时杀掉（如 160s），wrapper 可能在"Start-Process 之后、写 stamp 之前"被打断 → 引擎已起但 stamp 还是旧的。判据：触发后看 stamp 的 `ts`/`engine_pid` 有没有更新；没更新但引擎在跑 = 半途中断，不是引擎没起。powershell 冷启动 + ATE `m.initialize()` precheck 能把整枪拖过 160s，别把"~60s"当硬承诺。

## 诊断坑（省时间）
- **ATE 解释器是 pointer venv**：`C:\Users\ASUS\...\envs\ate` 壳里 `engine_pkgs.pth` 指向 `E:\GoldstrategyEngine\python\envs\ate\Lib\site-packages`（MetaTrader5 真身在那）。C: 侧"import MetaTrader5 失败/没了"多半是 C: 壳被清，**不是包丢**——重建 C: 壳即恢复 import。先查这个再下"环境丢了"结论。
- `mt5.initialize()` 不带 path = 挂**默认在跑**的那个终端；`-10003 not found` = 没有在跑的终端（属②），不是 ATE/Python 的锅。
- 区分"0 品种"（initialize 挂/终端断，②）与"WinError 2"（subprocess 找不到可执行文件，多为 gh 缺，①）——两者报错字面不同，根因不同。
