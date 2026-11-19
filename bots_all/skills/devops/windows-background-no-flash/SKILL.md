---
name: windows-background-no-flash
description: Use when 要清掉屏幕上闪的命令行黑框/全后台化(服务照跑窗口消失).
---

# Windows 全后台化：清掉屏幕上闪的命令行黑框（python.exe / gh.exe）

用户诉求定式："全部后台化，不能再出在我的屏幕上" / "怎么还有弹窗，赶紧给我处理干净"。诉求不是杀服务，是**服务照跑、窗口消失**。全程不碰聊天/网关/交易核心，改完必须给可验证的"屏幕干净"证据。

## 分层思路（闪屏源不在一层，逐层收）
1. **交易/守护链**（runner、watchdog、patrol、tick push 等常驻脚本）：解释器从带窗 `python.exe` 换**同目录**无窗 `pythonw.exe`；临时一次性 `subprocess.run/Popen` 加 `creationflags=0x08000000`（`CREATE_NO_WINDOW`）。跨平台写法用模块级常量 `_HIDE = 0x08000000 if os.name == "nt" else 0`，只定义一次，避免重复插入。
2. **子进程控制台应用**（gh.exe / git / curl / taskkill）：父进程切到 pythonw 后，每个控制台子进程会被系统**新分配一个控制台** → 照样闪。所有 `subprocess` 调 gh/git/curl 的点都要带隐藏窗标志。用户截图里看到的可能根本不是 python，是 `C:\Program Files\GitHub CLI\gh.exe`——先抓进程命令行定身份，别假设。
3. **调度器自身**（cron 一次性 `python -c "addsitedir...runpy"` 闪、CLI 自 re-exec 启动器）：定位产生该命令行的生成代码（本仓在 `cron/scheduler_script.py` 的 `_windows_cron_python_invocation` + `hermes_cli/venv_sync.py` 的 `relaunch_command`），改默认解释器为 pythonw 兄弟。改前 `find hermes-agent installs -name scheduler_script.py` 找全真实副本（环境 ID 可能截断，别信旧清单，逐个 grep 验 patch 落没落）。
4. **常驻"窗口"其实是 App 本身**：桌面聊天/网关进程（serve / gateway run / kernel）以 python 常驻且**带窗是正常**（就是那个 App 窗口），绝不动；动就断聊天+全部 cron。动手前先把"可杀"与"核心"分清单。
5. **服务/看门狗型闪源（反复 spawn 自带控制台的短命工具）**：你看到闪的黑框本体是系统给每个控制台子进程（tasklist / ipconfig / cmd / powershell）新分配的 **conhost.exe**——闪一下就退，顶层窗口枚举抓不到。真凶常是一个常驻服务或 App 反复 spawn 这类工具（例：Intel 的 i4ToolsService 每几秒 `tasklist` 查自己服务名；教学 lan_server 反复 `ipconfig` 探局域网 IP）。**诊断法：滚动窗口（每 3-5s 采一次全量 Win32_Process）抓"新建又消失"的短命 conhost/tasklist/ipconfig，再沿 ParentProcessId 往上走找父**，别去追工具本身。一旦"杀掉实例、隔几秒又冒"= 此类信号——**立刻停止反复杀**，改去断它背后那个会重新拉起的源头（计划任务 / SCM 服务自启 / App 看门狗 / autostart），见下方"断复发"节。

## 验证"屏幕真干净了"（不靠猜、不等图）
- 枚举系统可见顶层窗口：`Get-Process` 里 `MainWindowHandle -ne 0 -and MainWindowTitle -ne ''` 的进程+标题——这就是用户屏幕的地面真相；闪一下就退的进程枚举抓不到，用 60-90s 循环快照（每 5-10s 采一次全量 `Win32_Process` 的 python 家族 + 完整命令行 + 创建时间），看短命（活几秒到几十秒反复出现）的是哪类。
- 带窗 `python.exe` 计数 + 身份标签（gateway/serve/kernel/gh/git/cron 一次性…）；pythonw 侧计数。**改前后各拍一次**。
- 脚本改动后：逐文件 `python -m py_compile` 按**返回值**判（不通过管道 `| head`，管道会吞掉真实报错造成假绿）；再实跑该脚本的 cron 调用路径（runpy）确认 exit 0。

## PowerShell 在 bash 里执行的坑（本类任务高频踩）
- **多行 if/elseif/foreach 内联 `-Command "..."` 会被 bash 引号拆碎**（`elif` 当命令报 CommandNotFound）→ 把脚本**写成 .ps1 文件**再 `powershell -NoProfile -ExecutionPolicy Bypass -File x.ps1`。
- **中文标签 + 圆括号 + 命令替换 `$(...)` 写进内联复合 `bash -c` 会炸 `eval: syntax error near unexpected token '('`**（本机 git-bash 对含中文/括号的复合命令行解析不稳，一段 `&& echo ===中文===; cmd; $(...)` 叠多段尤其易炸）→ 探测/诊断/多步逻辑一律 `write_file` 成 `.py`（或 .ps1）再 `python x.py` 跑，**别把多段中文+括号+替换内联进单条 terminal 命令**。此规则不限于 PowerShell：任何混合中文+括号+`$(...)` 的复合命令（python heredoc、wmic、grep 链）都适用。
- 输出重定向 `Out-File` 用 ascii 显式指定；中文标签进终端常乱码，标签/结果一律用纯 ASCII 关键词（PID/age/父进程名），需要中文只在 ps1 注释里写。
- **PowerShell 5.1 用 `-File` 读 .ps1 时按本地 ANSI/GBK 码页解析：脚本体里的中文"字符串字面量"会直接炸解析**（报 TerminatorExpected / RedirectionNotSupported / 缺 `}` 等），不是普通乱码——所以 .ps1 里所有字符串字面量保持纯 ASCII，中文只能放注释。写脚本前先想好"每个 Write-Output 的值是英文"，别写完再发现 -File 跑不动。
- 复杂逻辑直接写 .ps1 免 `\$` 转义地狱。
- Python `subprocess.run(["powershell", ...], capture_output=True, text=True)` 捕获 powershell 输出时加 `encoding="utf-8", errors="replace"`：powershell 子进程偶发把 GBK 字节混进管道, 不加会在后台 reader 线程抛 `UnicodeDecodeError`（表象像脚本崩了, 其实主线程早已拿到值, 报错来自被遗弃的 reader 线程）。探测类 powershell 子进程（IM 匹配、Get-CimInstance）尤其要带；判活逻辑以**主线程**返回的 stdout 为准, 别被 reader 线程的 traceback 误导。

## 批量打补丁的安全纪律（血泪）
- 给 N 个文件的 N 处 `subprocess.run(...)` 插入参数：插入点在**匹配右括号之前**，且**保留原右括号**——吞掉 `)` 是这类补丁最典型 bug（嵌套 `_retry(lambda: subprocess.run(...))` 会缺两个）。插完**逐文件 py_compile 按返回值验**，失败立即从备份恢复，绝不带伤往下走。
- 改前每个文件留备份（带时间戳目录）；改后 grep 复核"定义只插一次"（防重复 `_HIDE`）。
- `find`/`rg` 扫带 `python/envs`、`site-packages`、`installs` 的巨型树会超时 → 定向 `find <两三个根> -name 目标` + 剪枝目录，或 Python `os.walk` 时 `dirs[:]` 剪掉大目录。

## 不动的边界
- 聊天运行时（hermes serve 家族）、网关、kernel：带窗/无窗都不杀（杀=断聊天断全部定时任务）。改它们的行为只能走"补丁代码 + 官方 .vbs/启动器重启网关"，不 taskkill 核心。
- 用户自己的 E 盘/教学内容/教学类服务（lan_server 等学情分发）不属交易链，默认不擅动，给可一键无窗化的命令让用户选。
- 实盘订单/持仓照旧只读，本任务不碰交易。

## 断复发（服务/看门狗型闪源，根治顺序）
反复"杀了又冒"的闪源，根治靠断它背后的重启器，顺序错了停不住：
1. **先禁看门狗计划任务**：`Disable-ScheduledTask` 掉会重启该服务的任务（i4Tools/Intel、Language、HybridDrive 等家族），否则下面停了立刻被拉回。
2. `sc.exe config <svc> start= disabled` 再 `sc.exe stop <svc>`——**顺序别反**，服务自启看门狗会在你 stop 前就拉回。
3. `sc config` 无管理员会报"拒绝访问"且实际没改：要么让 USER 右键"终端(管理员)"跑，要么 `Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','...ps1'` 弹**一次** UAC（仅用户明确授权时做），结果写 marker 文件再读，别靠 GUI 确认。
4. 非服务、由 App/计划任务反复拉起的可执行体（如教学 lan_server）：把 exe **禁掉**（`Rename-Item <exe> <exe>.disarmed`，保留可恢复）比反复杀实例干净。**定位 exe 路径优先从运行中进程运行时抓取，别把中文路径当字面量写进 .ps1**（GBK 码页会把字面量路径炸了 rename 直接报错）：`Get-Process -Name lan_server | Select -Expand Path` 拿真实 exe，若此刻没跑就**轮询 2s 一拍等到它被拉起的瞬间抓 Path**（宿主 App 会反复重拉，很快能抓住），再杀实例 + 改当前 exe 及其 `dist` 同份副本。`Get-ChildItem -Recurse` 只作为兜底（E 盘全递归必超时，对 2-3 个候选子树 `-Depth 7` 定位）。
4.1 **宿主 App 会重建 exe 时，只禁磁盘 exe 不够**：WorkBuddy 类 App 在每次任务触发时从自己那份重新拉起 lan_server，磁盘 exe 改名只在下次 App 触发前有效，触发后又会复活。这类闪源要**连宿主那个拉它的任务/App 开关一起断**（或交给对口 bot 根治宿主侧），磁盘 exe 禁用只是"当前静默"，不等于永久。禁完复扫若仍复发，结论就是"病根在宿主 App 的重启任务，不在 exe 本身"，别再空耗于反复禁 exe。
5. **验证=禁后 15-30s 滚动窗口再抓一遍**短命 conhost/tasklist/ipconfig，0 个才算断根；不复发才收工，别"杀一次"就当完。若禁 exe 后 30s 内 0 复发、但随后又被宿主 App 拉起（见 4.1），把"需断宿主重启任务"作为明确遗留写进汇报，别假装已根治。

## 排期（李彦明令）
调试/根治类活（闪框、进程清理、服务调整、断复发）集中在**每晚 23:00 ~ 次日 06:00** 做；白天先做别的、不白天反复弄。各子 bot 同此排期；白天若闪源还在，只报"现状+定位"，动手放夜间窗口。
