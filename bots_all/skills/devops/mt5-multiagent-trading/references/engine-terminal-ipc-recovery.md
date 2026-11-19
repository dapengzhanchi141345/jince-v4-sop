# 引擎终端 IPC 卡死(-10005)重启恢复 SOP (2026-10-07 实练定稿)

> 指针: 本节是 mt5-multiagent-trading SKILL.md「MT5 终端拓扑 & 登录铁律」中"禁止 spawn/kill terminal64"铁律的唯一例外分支, 且因 SKILL.md 超字符上限无法直接挂载, 由本文件承载。动手重启引擎终端前先读本节。

## 适用
巡检/节点报 "MT5 实读降级 (-10005, 'IPC timeout')"，且 terminal64 进程**仍在**（卡死≠挂掉）。

## 诊断序
1. 枚举 terminal64，分清引擎(`C:\Program Files\TMGM MT5 Terminal`, 金策 demo 60137964) vs friend 观察终端(`E:\mt5_friend_observer`, 用户只读 81223578)。`wmic process where "name='terminal64.exe'" get ProcessId,CommandLine` 或 PowerShell Get-Process + Path。
2. 用 ATE python 实读 initialize()：
   - 先软等 10s 再试（IPC 有时自恢复）；失败则重试 3 次间隔 15s。
   - **子进程环境必须净化**：`os.environ.pop('PYTHONPATH'); os.environ.pop('PYTHONHOME')`（父进程 3.11 venv 的 PYTHONPATH 会串进 ATE 3.13，numpy C 扩展加载崩——与本文件 §「Hermes 侧 PATH 污染」同病）。直接 `python -c` 裸调会继承 shell 环境，误报"没模块"。
3. 全败 = IPC 层死锁，走重启。

## 重启（对铁律"禁止 spawn/kill terminal64"的唯一例外）
- **只杀引擎终端**（`Stop-Process` 按 Path=`C:\Program Files\TMGM MT5 Terminal` 匹配的那个 PID），friend 观察终端绝不动。
- 顺序：kill → 等 8s → 起同一可执行（`Start-Process 'C:\Program Files\TMGM MT5 Terminal\terminal64.exe'`）→ 等 60s 握手。
- **恢复必须实读核验**：初始化 OK + login=60137964 + balance 对上才报"已恢复"；核验不过 = 重做一遍，别信"进程起了"。
- 投群三段报告：根因(终端 IPC 卡死非挂掉) / 已做(杀旧起新, 只动引擎终端) / 验过(实读账号+余额)。

## 竞态留痕（不是新故障）
- 重启窗口内（约 70s）撞上节点/巡检的 MT5 实读 → 节点报降级/0品种是正常竞态，节点降级铁律(20s 取不到跳过、派生簿只留痕)已覆盖；下一节点/巡检实读通了自动消，不用补发、不当新异常处理。
- 同理 chief 30min 全链循环若在重启窗口被拖住，看门狗按 35min 容差点名一次属正常，循环补跑完即静默。

## 并发多引擎 IPC 争抢 → 空卷回测 → 哨兵假阴性（另一类 IPC 故障，勿与 -10005 混淆）
上面是**终端侧 IPC 死锁**（terminal64 卡住、-10005）。还有一类是**引擎侧 IPC 争抢**：多个并发 Python 回测引擎各自 `mt5.initialize()` + 高频 `copy_rates_from_pos` 拉 K 线，共享的单一 IPC 管道被几个进程同时霸占 → 全阻塞。症状与 -10005 完全不同，别按"重启终端"处理。

**症状签名（回测卷，不是实读降级）：** `backtest_edge.json` / run_stamp 里 `aborted_by_timecap=true`、每个 `per_symbol` 全 `n=0`、`empty_volume=true`、`breadth_pass=false`，且各 symbol 的 `note` 写 `TIMECAP: 单品种 1560s 内未完成(疑 IPC 卡死), fail-open 跳过`。单品种全策略 simulate 本身只 3~6s、拉 K 线 0.2s，**远低于 1560s/币护栏** → 单币本不该 TIMECAP，能 TIMECAP 只可能是 IPC 被抢。

**根因实锤法（不猜）：** 看两趟补卷/引擎进程的 `CreationDate`——若一个手动 spawn 的引擎和一个看门狗/自动枪的引擎**创建时刻仅差几十毫秒**、各起一个引擎 → 双引擎同时霸 IPC 就是根因（非回测逻辑慢、非引擎触价 bug）。先清干净残留 Python 引擎进程、IPC 验活（单次 `copy_rates_from_pos` 0.01s 拉通），再**单引擎独占**直跑一趟干净补卷。

**治本：** 回测入口加**单实例原子锁**（O_EXCL 锁文件 + PID 验活 + TTL 过期自愈）防双发；注意 GBK 解码坑（`wmic`/`tasklist` 子进程输出走 GBK 管道，解码要容错）。上锁前先确认锁不会把**合法的单趟**也误拦停——本会话一趟干净补卷只跑 4 分钟(240s)就 `rc=0` 退出、`empty_volume=true`，大概率是新加的原子锁/fail-open timecap 把合法单趟也卡了，重跑前先核锁逻辑。

**假阴性哨兵铁律（空卷不出结论）：** `sentinels_high_wr_legs=0` 在**空卷（全 n=0、没跑出任何腿）**时是**假 0**——没数据当然读 0，不等于底层 bug 修好了。任何"哨兵清零=已修好"的判定，必须先确认那趟卷是**非空卷**（有真实成交 n>0 的腿）。销账三件缺一不可：**非空卷 + 哨兵真清零 + breadth_pass**；缺件的"哨兵=0"一律不销账、不放大。这条同族于"统计对比必须同分母"铁律——空卷/子集胜出是选择效应不是 edge。

**验收件实读姿势（防子代理误报出件）：** 子代理说"补卷出件/哨兵清零"时，**自己读 run_stamp + backtest_edge.json 验活**：看 `ts`/`elapsed_s`（只跑几分钟 rc=0 = 没真跑）、`empty_volume`、`breadth_pass`、`per_symbol` 的 n。`backtest_edge.json.generated` 停在旧时间戳 = 这趟没重写它、还是旧空卷。子代理"出件成功"的自报**不是事实**，以实读文件为准。

## `Authorization failed` (-6) ≠ -10005 卡死：终端重启作废常驻层句柄（2026-11-03 实锤）
用户报"账号一直登着，怎么一直显示登不上/连不上"时走本节（区分"终端登录态"与"外部程序 IPC 连接态"两层，**勿杀终端修"登录"**）。两类故障症状不同，别按"重启终端"处理。

- **机制**：Python 库经 IPC 管道 attach 终端；terminal64 进程重启（用户手登/看门狗自拉/终端自更新）瞬间作废所有旧连接。常驻长活进程（console/watchdog/live24 类）不自 re-initialize → 持续报降级；**30min 全链每拍是新子代进程，天然重 attach，下拍自愈**——降级显示最多滞后终端重启一条全链拍。
- **症状签名**：`initialize` 报 `(-6, 'Terminal: Authorization failed')` / `[训练] MT5读降级(fail-open)`，而终端 UI 登录正常、terminal64 进程活着。区别于 -10005：-10005 = 终端进程卡死须杀重启；Authorization = 句柄世代错位，不用动终端。
- **诊断序（全只读）**：
  1. 验终端进程换代：`wmic process where "name='terminal64.exe'" get ProcessId,CreationDate` —— CreationDate 新于降级起时 = "终端被重启过"坐实（旧句柄死即根因）；没重启过才往终端侧连接限制查。
  2. 钉降级窗：`grep -an "Authorization failed" data/auto_cycle.log | tail -3`（末次降级拍）＋ `grep -an "全链自动运行完成" data/auto_cycle.log | tail -4`（拍→行号映射）；最后一条降级拍之后有干净的 `MT5 60137964 ... -> _tmp_mt5snap.json` 行且 `_tmp_mt5snap.json` mtime 更新 = 已自愈。
  3. 新进程探活（决定性证据）：ATE python（`E:\GoldstrategyEngine\python\envs\ate\Scripts\python.exe`）跑 `import MetaTrader5 as mt5`（**模块名是 `MetaTrader5`，裸 `import mt5` 报 ModuleNotFoundError**，引擎探针脚本同款写法）→ `initialize()` / `account_info()` / `terminal_info().connected` / `positions_get()` 全通 = 终端与登录无问题，死的是常驻层旧句柄。定时任务实际解释器（任务 XML 里读，与引擎本地 ATE 不是同一份）别拿来探活；探活一律用已验过能 import MetaTrader5 的那份。
  4. 给用户汇报模板（大白话）："您的登录一直正常，坏的是'我们的程序连终端'这根线；终端 X 时重启过，主链 Y 拍起四连拍全干净；您屏幕若还显示'登不上' = 降级窗旧数展示（STALE 标），不是当下实况。"
- **处置**：0 码；重启常驻层进程一次即可（杀进程权 = 用户一字域/授权执行窗），主链自愈不动终端。常驻层重启后若仍报旧降级 → 验它是否真拿到新一代句柄（再跑第 3 步探活对拍）。

## 僵尸锁 + 自愈复拉循环（引擎"起了就死→每 5min 复拉 ×3"风压）
症状签名：`wmic` 扫 backtest_engine 批次显示**同一时刻多起引擎、CreationDate 各差几十毫秒、每 5min 一整批换新 PID**，而 `backtest_edge.json` 一直停在旧卷 = 新引擎没跑成，循环只是"起→秒死→被自愈重拉"。
- **诊断序（先查后杀，别逐个杀引擎当止血）**：① 读 `data/*.lock`（backtest_engine.lock 等）——lock 里 holder PID 已死 = 陈旧锁，新引擎起即退出；② 找谁在复拉：父 PID 落到 hermes 网关（正常，cron 脚本都是网关子进程）没用，要看**哪个脚本/任务在 Start-Process 引擎**（self-heal cron、watchdog、或某个守护循环）；③ 复拉源判活手段本身先验（下条 wmic 坑）。
- **收口顺序（最小影响）**：删陈旧锁 → 暂停自愈/复拉型 cron（`hermes -p <profile> cron pause <job>`，别删，修复到位后 resume）→ 拉**单**干净引擎 → 验单实例存活（读锁文件 holder PID + 进程 CreationDate，不靠 wmic 行数）。
- **wmic 复合条件坑（本 Win11 机实测）**：`wmic process where "name like 'python%' and commandline like '%xxx%'"` 这类**复合 LIKE 条件会静默返回 0 行**（单 name/单 commandline 条件各自能命中），拿它做"引擎在不在"判活的脚本会永远判"不在"→ 每拍重拉 = 风压根源。写活体探测前**先拿同条件实跑一次确认有输出**；探测改单条件 wmic / PowerShell `Get-CimInstance Win32_Process` / Python 原生枚举；判"进程活着"以锁文件 holder PID + CreationDate 为准，不以 wmic 行数为准。
- **杀进程审批礼仪（夜间/用户不在）**：主 bot 的 taskkill 走 smart-approval，用户睡觉时**反复试杀 = 每 1 分钟空超时一次还刷屏**；blocked 后不重发、不换等价写法绕（如 Python os.kill）——把待杀清单（留哪个 PID、杀哪几个、为何）派给 strategy-rd（其 profile 侧无此审批门）或排进用户明早授权窗，同时确保"不杀也不伤人"（单实例锁在位时多引擎只会撞锁静默死）。

## 关联
- 看板/远端推送的 443 间歇墙与本故障无关（extnet=down 是常态 fail-open 降级），别合并归因。
- 空卷不出结论 / 同分母铁律、五验口径见 `leg-polish-five-test.md`；回测/进化加速节奏见 `evolution-acceleration-and-inspection_20261010.md`。
