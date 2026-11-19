# 脑手分离 ZMQ relay 验证 (稳妥版→最强版过渡, 2026-10-20)

全网最优公约数: MT5/CFD 胜负手在**可靠性**不在速度 (broker 帮你路由成交, 做不了币圈 HFT 级)。可靠性层=终端自动登录/健康探活/断线重连/序列号防漏/成交确认/断线补漏/boot 对账。

## 落地代码 (新 bot 的脑手执行层骨架, 不碰金策 15195 行活引擎)
根目录 `E:\workbuddy\内容中心\交付\AI交易bot方案_20261019\jince_bot\`
- `protocol.py` — 消息契约 + 安全网关纯函数 `check_safety_config` + `make_order_seq`
- `side_hand/hand.py` — 手侧: attach 官方 MetaTrader5 库(不写 MQL5 EA/不编 DLL/不 spawn 终端) + PULL 指令 + 成交 + 序列号回执 + boot 对账 HELLO + 就绪文件 + 安全网关实读复检
- `side_brain/brain.py` — 脑侧: PUSH 指令 + PULL 回执 + 序列号核对 + 幂等去重 + 配置级安全网关预检
- `signal_bridge.py` — 复用金策 top_trader.decide() 出提案 (monkey-patch load_kline→market_intuition 真读)
- `runner.py` — 24/7 常驻 (Session 手侧长驻 + 单实例锁 + 自愈) / 单轮 两种模式
- `verify/e2e_test.py` `verify/signal_driven_test.py` — 端到端验货
- `.venv` — 独立 venv, 装了 pyzmq + MetaTrader5 (不污染金策 ate env)

## 两条路 (都不用换账号/换 broker, demo 先跑)
- **稳妥版(生产主力, 现在跑)**: 脑手同机, 官方 MetaTrader5 Python 库 attach。最简单 0 额外组件, 最快验证 edge。
- **最强版(未来, 零改动切)**: 脑手分离, 上 ZMQ 桥 (脑 Linux 云 + 手 Windows 云)。多一个薄 relay。跑通同套 protocol/手侧代码, 换 host 即分离。
- 顺序铁律: **先证明能赚钱 (稳妥版跑 edge), 再谈扛得住 (ZMQ 分离做 7×24 生产)** — 别一上来搞最复杂。

## 设计要点 (做到顶的可靠性层)
- **手侧默认 DRY**: 只组装真实订单 + 读真实价, 不真 `order_send`; `--execute` 才真下。0 资金风险验证。
- **安全网关三道墙** (check_safety_config 配置级 + account_safety_live 实读复检):
  - 墙1 服务器名含 Live/Real → 拒 (防连实盘服务器)
  - 墙2 账号漂移 (实读 != 期望) → 拒 (防终端登错号)
  - 实盘总闸 allow_live_trading: **只在真下单 (dry=False) 时拦**; DRY (dry=True) 在总闸未开时放行 (安全演练不碰真钱)。← 关键职责边界, 别把总闸混进配置级预检否则 DRY 验货被卡。
  - trade_mode 该券商 demo 也返 0 不可信, 靠服务器名+账号号兜住, 只记录不卡死。
- **幂等去重**: 同一 `client_order_id` 手侧只执行一次 (防脑侧重发双下单)。
- **序列号防漏**: 每条指令带递增 seq, 每条回执带对应 seq; 脑侧超时未收 = 疑似漏单 (断线补漏信号), 写 lost 列表。
- **成交确认**: 读 `order_send.retcode`, 白名单 {10009,10008,10010,10018}, 不在=失败绝不假装成功。
- **boot 对账**: 手侧启动先读真实 positions/orders 并 HELLO 回报, 不假设空仓。
- **断线重连**: PULL/PUSH socket 断即重连, 指令队列不丢。
- **指令透传绝对 SL/TP**: 协议加 `abs_sl/abs_tp` (AI 建议的结构价), 手侧优先用绝对价; 没有才 sl_pts/tp_pts 相对 tick 算。SL/TP 贴价 bug 即价差当点数的坑。

## 验货证据 (XAUUSD, demo 60137964, DRY 0 资金, 全通)
- 脑→ZMQ→手→attach MT5→组装真实订单→成交回传→序列号核对→幂等去重。
- 真实价 4141.88 / SL 4141.58 / TP 4142.48 实读拿到; 幂等同单三次只下一次; 序列号全核无漏单。
- **24/7 常驻 (runner.py --loop 1800, Session 手侧长驻)**: cycle 1 实跑 executed=5/lost=0/all_dry=true/acked=[1..5], 就绪文件 pid=101036 safety=true account=60137964, 重启后 0 次手侧宕机跳过。审计 `GoldstrategyEngine\data\jince_bot_runner_audit.jsonl` (event=cycle mode=persistent 行=循环真转起来的硬证据)。
- 信号驱动: top_trader.decide 真读版出 6 单 (heat 1.27%), 9/10 品种 source=MT5_LIVE, 取 5 单走脑→ZMQ→手 DRY 全 sent=True dry=True。
- runner 手数重算: 金策 symbol_universe pip_usd (ate dump → `_pip_specs.json` 解耦), ADAUSD lot=0.05 (不再全塌 0.01)。

## 金策固有 bug (记录, 不碰活代码, 交 strategy-rd 五验)
- **top_trader sl_pips 币系量纲 bug (2026-10-20 实测精确)**: 贵金属/外汇分支 (XAU/XAG/XTI/XBR 用 价差/0.01, JPY 用 价差/0.01) 算得对 — XAUUSD 50 美元价差→5000pips 与 symbol_universe pip=0.01 一致, 手数塌到 0.01 是**宽止损的正常风险结果**, 非 bug。**真正 bug 在币系/非贵金属非 JPY 品种** (如 BCHUSD): 没走对分支, sl_pips 算出 104114 (10 美元价差→10 万 pips, 量纲错 1 万倍), 手数全错。DRY 不影响安全, **开实盘前必须修** (按 symbol_universe pip 字段统一换算), 交 strategy-rd 五验拍板。
- **本地对策 (runner 层, 不碰活代码)**: `runner.py` 对全部品种用 symbol_universe pip 规格 + pip_usd 手数公式重算, 就地算对。

## 踩坑 (永久)
1. **验证脚本里 proc.stdout.read() 会阻塞** (手侧还在 serve 写 stdout) → 手侧后台跑, 验证走审计/回执, 不落 read。
2. **手侧 serve 主循环不自行退出**: 结尾 proc.terminate()+wait(4)+kill 兜底, 别裸 terminate。
3. **taskkill //IM python.exe //F 在 bash 下写法错 + 杀全量 python 被 smart approval 拦** (会杀其它 agent); 残留手侧让后台脚本自然 kill 或 kill_residual.ps1 (按命令行匹配 jince_bot 路径), 别全量杀 python。MSYS bash 下 taskkill 用单个 `/IM` 不用 `//IM`。
4. **zmq PULL(bind 手) ↔ PUSH(connect 脑)**: 脑侧 emit 前手侧必须已 bind + attach MT5; 起脚本 sleep 后先发 PING 探活再发单。
5. **venv 装 pyzmq**: 给 jince_bot 建独立 `.venv`, `pyzmq + MetaTrader5` 装里面, 走 venv python 跑脚本。
6. **MSYS bash 里 inline PowerShell 的 `$var` 被吃** → 写 `.ps1` 文件再 `-File` 执行, 别 inline。
7. 内层 `-c "..." %格式化` 脚本若本身含 `%` (print 带 %d) 会与外层格式化冲突 → 内层改用 json.dumps 输出, 不写 %。
8. **zmq ctx.term() 阻塞**: 有活 socket 时直接 term() 会挂死常驻循环 → 先 sock.close(linger=0) 再 term (脑侧 close/手侧 finally 都改过)。
9. **单实例锁防双开抢端口**: 两个 runner 同时跑会抢 5555/5556 → 手侧 bind 崩 → 循环卡死。msvcrt 文件排它锁 (进程死 OS 自动释放), 常驻 runner 起前先抢锁, 抢不到静默退。
10. **共享一条 recv socket 会吞回执 → "疑漏单"幽灵**: 脑侧 wait_fill / query_account / close_all / close_symbols 若各自 `recv_string`, 开单回执(FILL) 被"实读账户"那一下误读就永久丢, 后续 wait_fill 超时标 lost, 心跳一直挂"疑漏单"。正解: 加一个 `self._inbound` 统一收件缓冲, 所有 recv 都进缓冲, 非目标 FILL 一律 `append` 绝不丢, 后续 wait_fill 先扫缓冲再读 socket。心跳"疑漏单 N"清 0 = 修对的证据。
11. **24/7 重启不丢魂: 日亏熔断/开单计数必须落盘 + 时区写死**: 当日 breaker/day_orders 只在内存里, 24/7 一重启就清零, 熔断了还能重开新单 = 保命失效。正解: 把当日状态写 `jince_bot_daystate.json`, runner 启动先按"同一天"读回恢复(不清零), 日切换/熔断/开单时随写随落。日亏日单数一律用**写死的北京时间 UTC+8**(`datetime.now(timezone(timedelta(hours=8)))`), 不靠系统时区/broker 时间, 时区被改不会漏/误触发。
12. **风控数字做单一源(防两套漂移)**: 单笔风险/heat/日亏/日单数/magic 全写进一个 `bot_risk.py` 单一源, runner + kill_switch 都 import 它, 别在 runner 里再各写一份常量 —— AI 说了不算, 这些是代码硬闸, 单一源才改得动、审得清。
13. **Windows 按命令行匹配 jince_bot 进程会漏杀 uv cpython 子进程**: uv `.venv\Scripts\python.exe` 是 shim, 它 fork 的 cpython 子进程命令行里可能只带相对/短路径、不含 `jince_bot` 全路径, 于是 `-match 'jince_bot'` 匹配不到真 runner。可靠匹配 = 按脚本名 `runner.py|hand.py`(+ `内容中心` 路径双保险) 一起 match, 别只按项目目录名。误判"进程没了"再重启 = 双开抢端口, 先按脚本名核实。
14. **从 Python 生成 .bat 用 str.replace 别用 % 格式化**: .bat 里 `set /p CONF`/`%CONF%`/`if %CONF%==Y` 的 `%` 会和 Python 的 `%` 格式化冲突报 "not all arguments converted"。写 .bat 走 `open(...,'wb').write(template.replace('%PY%',py).replace('%KILL%',kill))`。中文 Windows 双击 .bat 必须 **GBK 编码**写文件, 否则中文乱码。
15. **一键急停 .bat 三件事全做**: ① 撤全部挂单+平全部持仓(只碰本系统 magic, 绝不误伤手工仓, 默认 --execute 前加按 Y 确认防误触) ② 落当日 breaker=True(24/7 循环今天不再重开, 清掉=删 daystate.json 恢复) ③ 全程写审计。急停不依赖脑手 ZMQ relay, 独立 attach MT5, relay 死了照样能用。

## 24/7 盯盘模式 (watch, 非批处理; 用户令"跟人工一样时刻盯盘 随时开单随时平仓")
`runner.py --poll 15 --signal-refresh 60` = 盯盘模式, 不是 30min 批处理: 主循环每 poll_s(15s) 干四件 —— ①手侧自检自愈 ②实读账户(净值/持仓/挂单/浮盈) ③日亏熔断+持仓管理(金策不再持有该品种 / 信号反转 → 主动离场 close_symbols, 只碰 magic) ④有未触发信号立刻开单。机会最多 poll_s 秒开单、持仓失效最多 poll_s 秒离场。**"想"是异步的、"盯"是快的**: 金策 propose(子进程 30-60s)放后台线程每 signal_refresh_s(60s) 连轴转, 结果存 `sig_state`, 主循环只读最新不阻塞。心跳每 15s 一行(开单/去重/持仓 各给原因 + 信号 N s 前) = 盯盘活着的人工一眼证据。持仓管理仅在信号有效(plans_total>0)时离场, fail-safe 不误平。

## uv shim pid 错配 (2026-10-20 最深坑, 常驻 24/7 卡死根因)
`.venv\Scripts\python.exe` 是 uv 管理的前端 shim, 它 fork 出 cpython-3.11 真进程执行 hand.py。所以:
- `subprocess.pid` (shim) **永远 ≠** hand.py 里 `os.getpid()` (真进程) → 按 pid 匹配 boot 对账/hello 审计**必失败**。
- 失败链: 脑侧判手侧"死" → 反复杀手侧重连 3 次全失败 → `cycle_skip_hand_down` → 24/7 循环假死 (日志有 `[cycle N]` 但 executed=0)。
- **正解 (已落地)**: 手侧 attach 成功后写就绪文件 `E:\GoldstrategyEngine\data\jince_bot_hand_ready.json` ({ready, ts, pid, safety, account}); 脑侧起手侧前先 os.remove 旧文件 (单实例锁保证只有本 session 手侧在写); 判活 = 读就绪文件 且 ts ≥ 本次 boot 时刻。就绪文件 pid 字段仅供记录, 绝不用于匹配。
- **症状识别**: `jince_bot_runner_audit.jsonl` 里反复 `hand_dead_reconnect` + `cycle_skip_hand_down` + `[cycle N] executed=0` = 十有八九是 pid/时间窗误判, 不是手侧真死 (看 hand_audit 其实 hello 全 success)。

## 与金策引擎关系
这是**新 bot 的脑手执行层骨架**, 将来接 LLM 研判 (metatrader-mcp-server 范式) + RL (gym-mtsim), 就是「AI 建议、确定性代码下单」: 脑侧出提案, 手侧经安全网关+序列号+幂等执行。稳妥版先跑 edge, 验证过再上 ZMQ 分离版做 7×24 生产。
