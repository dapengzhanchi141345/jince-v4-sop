# MQL5 终端内 EA：无头编译、安装、进程活体判定（本机实操）
> 何时用：改/编译/安装 MQL5 EA，或要判断本 host 上 python/pythonw 服务活体、做无窗口 daemon 化拉起时。与 mt5-indicator-authoring 技能互补（那边管指标/EA 写法，这边管金策系统内的编译-安装-活体流程）。

## MetaEditor 无头编译（0 黑框）
```cmd
"C:\Program Files\TMGM MT5 Terminal\MetaEditor64.exe" /compile:"E:\...\mql\EA_X.mq5" /log:"E:\...\mql\ea_x.log"
```
- 编译日志是 **UTF-16LE**：`open(log,'rb').read().decode('utf-16-le')` 解码，看尾部 `Result: 0 errors, N warnings`；iconv/直接 cat 会打不出内容。
- 前置铁律（已知坑）：先确认该 build 的编译器真能出 .ex5（某 build 的 /compile 只做 syntax-check，日志 0,0 报 `error 208: MQL5 files compilation is not supported` 且不出 ex5）——先拿 10 行 mini EA 试编再写大文件。
- 0 errors 后，ex5+源 mq5 一起拷到终端数据目录 `C:\Users\Administrator\AppData\Roaming\MetaQuotes\Terminal\<hash>\MQL5\Experts\`（TMGM 引擎终端 hash 目录；装 ex5 进目录 ≠ 生效，必须挂上品种图才跑；图表属性跨终端重启保持，EA 自动复挂）。
- 用户唯一手动步=把 EA 拖上图表+勾执行闩（InAllowExec 类 input）+允许算法交易；零歧义给到按钮级。

## 执行腿 EA 的 MQL5 契约（「哑执行器」模式）
- 决策字段全来自引擎 CSV feed（纯 ASCII）；MQL5 侧 StringFind 解析 key=value——**键名互不为子串**（StringFind 取首个命中，短键撞上含它的长键会读错值）；解析不出的字段给显式默认值（不靠结构体零初始化的侥幸，MQL5 struct 全局零初始化但局部 SymLine 要手设默认）。
- 新单闸全 fail-closed：STALE feed / 账号漂移 / 非 demo / 手数 0 / 熔断未知 / SL-TP 距 < stop level → HOLD+留痕原因；**平仓路径永远不挂闸**（卡住=仓位裸奔）。
- 日限单/去重用自己的审计日志计数，日志不可读=从严（视为达到上限）；下单 retcode 白名单 10009/10008/10010 为成功，10018=休市跳过（与 MT5 Python 库同族口径）。

## 本 host 进程活体判定（持久坑）
- `Win32_Process.CommandLine` 对 pythonw 经常返回空、或只有绝对解释器+绝对脚本路径才匹配（uv/相对路径形态 0 命中）——判活体用「日志 mtime + audit jsonl 最新 pid + tasklist PID」，别拿 wmic/CIM 命令行匹配当唯一依据；杀残留前先确认 PID 不是 hermes 自己的 kernel（`hermes_kernel_runner.py` 会误中 `*runner.py*` 模式）。
- MSYS bash 里 `python - <<'EOF'` 空 heredoc 连写会掉进交互式 REPL 刷屏（traceback 洪水+超时）：一次性启动器写成脚本文件再 `python launcher.py`。
- 无窗口 daemon 复拉配方：一次性 python 脚本 Popen（pythonw 解释器、`creationflags=0x8` DETACHED_PROCESS、stdout/stderr 重定向到既有日志文件、cwd+env 显式传、解释器与脚本路径全绝对——绝对路径还让看门狗 wmic 探活命中）；脚本自身立即退出，进程 detached 独立活。
- 改服务行为前先改「启动配方」（bat/看门狗 Popen 参数），再让调度方自然复拉；手动强拉容易与自愈看门狗抢实例。
