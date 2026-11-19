# MT5 实盘取证 & 闸裁定（forensics）

## 终端日志 = IPC 挂时持仓/成交真值源
- 金策 demo 60137964 引擎终端（TradeMaxGlobal-Demo）日志：`C:\Users\Administrator\AppData\Roaming\MetaQuotes\Terminal\7643C0B96C7AD5841307C9E1EB0B9252\logs\YYYYMMDD.log`
- 编码 UTF-16LE（字间夹 \x00）。读取：`open(p,'rb').read().decode('utf-16-le')` 再 `re.sub(r'\x00+','',txt)`；直接 grep/tail 匹配不到。
- 行形如 `deal #516870121 sell 0.01 XAUUSD at 3927.57 done (based on order #663837800)` / `order #... sell stop` / `cancel order #...` / `close #<order>`。挂单、撤单、平单都在这，断网时比 live positions_get 更权威。
- 判"某仓是否仍开"：grep 该 order 号，看后续有没有 `close #<order>` / 反向 deal；无平单 = 服务器端仍开（至最后一条日志事件）。

## 两种"IPC 断"要分开
- 本地 IPC 通道抖：terminal64 进程活、券商连接在，5–10min 自愈，tick 喂降级沿旧数据。
- 终端掉券商连接（严重）：日志 `disconnected from <broker>` + `authorization ... failed (Invalid account)` → `mt5.initialize()` 直接 False、一切读/下单全瞎，不自愈。恢复=李彦明手动重登终端（铁律：我不能 spawn/杀/自动登录）。
- 排障顺序：先 tail 终端日志找 `disconnected`/`Invalid account`；有=掉券商连接找李彦明重登；无=本地 IPC 抖，等自愈。

## live24 绕闸泄漏 + L4"先接三闸再跑"裁定
- jince_live24.py 开单腿 0 读三闸源 / 0 读 exp_r 总闸 / 0 读金腿 retire_freeze → 会开绕闸违规单。
- LIVE24_HALT 瞬态手动文件=漏风点（在→SKIP 不开；被删→直接开新单）。手动文件治标，要换闸源实读。
- L4 裁定（veto_log #3323/#3329）：live24 不杀进程、改"先接三闸再跑"。恢复前置三条（终端重认证、放行任何执行腿前必须全齐）：① 金腿 retire_freeze 接进 live24 开单腿 + 删 LIVE24_HALT 手动依赖；② 冠军 exp_r 总闸（multi_agent/trading/_exp_r_gate.py，已 fail-closed、6 路径在用）接进 live24；③ 演练子账户账本剥离（MAGIC 20261102 那批重标 drill，主/子账统计分家）。三条缺一=live24 维持 0 开新腿（进程留 DRY 观察）。
- 顺序铁律：L5 接三闸出码+DRY 验证 → 李彦明重登终端 → 三闸齐才放行执行腿。终端先活、live24 裸奔=把漏洞重新打开。
- 教训：审计"主账被演练单污染"被洗白时，L4 不撤销对 live24 绕闸开单的裁定——洗白的是演练子账户那批单，不触及 live24 实打实的闸外开单（两码事，别混）。
