# 金策·码改闭环工作制度（11-15 李彦明令制度化: 全面深度优化后立即执行, 以后不用提醒, 不能有bug）

## 铁律（每次代码改动后必走, 顺序不可乱）
1. **py_compile** 先过（不过=不上线）
2. **热切换**: 杀旧引擎 pid（一魔一号锁防双实例）→ 拉新（D:/workbuddy/binaries/python/versions/3.13.12/python.exe jince_live24.py, cwd=E:/GoldstrategyEngine/tools, OMP/MKL/NUMEXPR_NUM_THREADS=1 防OOM, creationflags=0x08000000）
3. **三验（拿证据不猜）**:
   - `data/live24_magic_30261103.lock`=JSON{pid,ts_unix,magic}: pid活+ts_unix心跳<3min
   - 源码标记 grep: B0_VOL_K / _regime_gate / per = PER_SYMBOL（缺=被回滚, 红报）
   - 进程 StartTime > 代码 mtime（否则=旧码在跑, 红报）
4. **留痕**: task_ledger.json + 状态卡 + rd_queue/总线按型
5. **自动复检**: `hermes\scripts\jince_verify_all.py`（确定性0LLM）每30min cron `da880a3a22e8` no_agent: 引擎三验+L2采集器pid/tick<5min+regime/zones<45min+MC/VaR<26h(日频07:45一次)+kill_switch非TRIGGERED+深研log存在; 全绿静默, 红报一行投群
   - **哨产物新鲜度阈值必须匹配任务周期**: 日频哨（每日一次）的产物合法静默窗=次日同触发点前, 阈值=周期+容差（日频=26h, 非 15h）——把高频哨的 15h 阈值抄到日频项上, 每天 23:45-07:45 必误报一轮, 修=改阈值+清 `__pycache__` 旧字节码（pyc 缓存会让改后首拍仍按旧口径出文案）

## 优化后立即执行（不待指令）
- 过五验的参数=当轮直接落执行层（杀旧起新+三验+留痕）; 不过=WATCH攒样留痕
- 仅L5（实盘手数/对外发送/资金/kill复位）留李彦明拍板
- 「不能有bug」=每改动带数据有效性闸（来源+快照+新鲜度, 缺=显式FAIL）+验证哨30min内兜底复检到

## 已知坑
- ATE绑定: Tick无tick_volume(用volume)/deal.entry=1=平仓行/TradeOrder.price_open/撤挂单TRADE_ACTION_REMOVE/json拒bool(转int)
- tasklist/powershell输出GBK, subprocess必errors='replace'; bash里powershell的$_会被bash吃(用python转译)
- 看门狗拉引擎=D:/workbuddy/binaries路径; 手工拉新码必杀旧pid, 否则一魔一号锁自退
- **宿主父链闸与触发源必须同步（11-16 宿主闸③假FAIL根因）**: 宿主闸③销据规格="taskeng 自动枪父链追到调度器根"。回测触发源从 Windows 计划任务迁到 Hermes cron no_agent 后规格没同步→父链断在 pythonw, 宿主闸**永久 FAIL**, 池单闸持续 suspended（放大 0）——安全侧无错但把出徒放大卡死在假故障上。判"哨/闸持续 FAIL"先分清**真停摆 vs 规格失配**：查原触发源任务是否还存在于计划任务表（schtasks /Query 全表 grep 任务名, 注意 grep 时别把含 "hermes" 的行过滤掉漏看）；任务已消失但活还在别家调度器跑=失配。修=最小影响: 重建原计划任务（taskeng 触发, 闸规格一字不动）+ 保留新调度器做备份枪 + 脚本自带单实例锁（lock.meta pid 活体探测）防双跑; 验收=下一次自动触发后读 stamp 父链含 taskeng 即 PASS
