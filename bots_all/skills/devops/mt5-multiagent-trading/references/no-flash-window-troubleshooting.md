# Windows 无窗后台化 & 闪屏（gh/python 黑框）排障

**适用症状**：用户反复报"屏幕上老冒 python.exe / gh.exe 黑框 我没法看屏幕 全部后台化 别再出现"。金策 bot 链、全链循环、Hermes 核心 cron、GitHub 同步脚本的常驻/一次性子进程会把带窗 console 一闪一闪糊在用户屏幕上。

## 三层闪源（按糊屏频次排）
1. **gh.exe / git.exe / curl（用户实际最常看到的就是这个）**：子进程无 `CREATE_NO_WINDOW` 时，父进程是无窗 pythonw 也会让系统给每个 console-app 子进程新开一个控制台 = 闪一下。金策 6 个同步/巡检脚本调 `gh api` 每 5min/03:00/看板守护都闪。**修法**：给该脚本里每个 `subprocess.run(["gh",...])` / git / curl 调用加 `creationflags=0x08000000`（Windows 守卫 `_HIDE = 0x08000000 if os.name=="nt" else 0`）。
2. **金策 bot 链 + 全链循环（jince_bot/runner.py、side_hand/hand.py、selfheal watchdog、auto_run_cycle.py PY、jince_auto_patrol.py / jince_tick_push.py / jince_watchdog.py 的 ATE 子进程）**：解释器 `python.exe`→`pythonw.exe` 兄弟；短命 ATE 信号子进程加 `CREATE_NO_WINDOW`。
3. **Hermes 核心 cron 调度器（`hermes-agent/cron/scheduler_script.py::_windows_cron_python_invocation()`）+ `venv_sync` 的 committed-venv re-exec 启动器**：默认用带窗 store python.exe 跑每个 scheduled 脚本。patch managed_python 分支偏好 `pythonw.exe` 兄弟；改完必须**重启 gateway** 才加载（桌面 serve/kernel 不动，它们是本机桌面 App 运行时，杀了断聊天）。核心 runtimes（hermes serve / gateway run / hermes kernel）保持 python.exe 不动 = 设计如此，不是闪源。

## 诊断铁律：用进程树，别信屏幕/截图
- `vision_analyze` 读用户截图**额度墙 + 滞后**，不是第一手。直接 `Get-CimInstance Win32_Process -Filter "Name='python.exe'"`（+ `pythonw.exe`）枚举**所有带窗进程**，按 CommandLine 分类：`RUNTIME_SERVE/GATEWAY/KERNEL`（活、父是 Hermes.exe 桌面 App）= 不碰；`source_completion / gateway status / 一次性 -c runpy / gh 短命`（父是 bash/服务、活 2-44s 反复冒）= 闪源。闪源是**短命一次性进程**（活几秒就退），截图拍到的常是它闪现那一下 + gh.exe。
- 先分清**哪些真带窗（有 conhost 控制台）哪些只是无窗后台**——只收拾带窗的，常驻核心别误杀。杀核心（serve/gateway/kernel）= 断桌面聊天 + 断全部 cron。

## 批量 patch 子进程隐藏标志的两个血坑
- **保留收尾右括号**：手写 balanced-paren 扫描器给 `subprocess.run(...)` 插 `creationflags=` 时，**必须把匹配的 `)` 也 emit 回去**（`out += ")"; i = close+1`）。漏了 = 直接 `SyntaxError: invalid syntax / perhaps you forgot a comma`。插 `_HIDE` 常量定义时插到**首个顶层 `import` 行之后**且只插一次（别插进函数体）。
- **编译验货别被管道假绿**：`... | head -1` 取的是 head 的 exit code，不是 py_compile 的——文件真坏也显示 OK。用 `python -m py_compile file` 的**真实 returncode** 判（或 `subprocess.run([py,'-m','py_compile',f]).returncode==0`），改前先把原文件备份到带时间戳目录（可逆），改完逐个验。
- patch 幂等：inner 文本已含 `creationflags` 就跳过，别重复插。

## 收口口径
全清 = 金策侧带窗 `python.exe` 匹配关键词计数=0、无窗 `pythonw` jince_bot 链正常、gh.exe 此刻"活着的=0"（间歇调用已加隐藏标志）、tick_live.json 还在按 5min 喂。教学侧的 `lan_server.py`（E 盘、用户"不擅启 E 侧"）按铁律不擅动，留一句"可一键无窗化"给用户拍板。
