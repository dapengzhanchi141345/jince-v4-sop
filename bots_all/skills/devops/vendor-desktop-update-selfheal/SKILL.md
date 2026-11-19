---
name: vendor-desktop-update-selfheal
description: 厂商桌面端一更新就出bug/版本失同步, 诊断+装自愈哨SOP。
version: "1.0"
author: Hermes Agent
license: internal
metadata:
  hermes:
    tags: [windows, electron, workbuddy, desktop, update, watchdog, selfheal, version-desync]
    related_skills: [windows-scheduled-task-ops, windows-background-no-flash, workbuddy-local-conversations]
---

厂商桌面端（WorkBuddy 等 Electron App）自动更新后"出 bug"的诊断 + 自愈哨安装。

## When to Use
- 用户说"桌面端一更新就出 bug""桌面 App 更新后闪退/功能时灵时不灵/变卡""能不能自己优化一下"。
- 厂商 Electron App（WorkBuddy/Hermes 桌面/MT5 终端等）自动更新后需定位根因并装"更新后自动体检+自愈"哨兵，让用户零动手。
- 版本失同步（主程序升了、渲染端/标记文件没跟上）排查。

诉求定式："一更新就出 bug，你**自己优化一下**"＝定位根因 + 装更新后自动体检/自愈哨兵。全程保守：不碰厂商 asar、不杀活进程。

## 诊断五读（先定位，不猜）
1. **exe 真实版本（权威源）**：`powershell (Get-Item '<App>.exe').VersionInfo.ProductVersion`。以 exe 为准，别信日志里打印的版本号。
2. **版本标记文件（失同步高发点）**：找 `renderer-version.json` / `startup-seed-version.json` / `*-version.json`。WorkBuddy 常见路径 `D:\workbuddy\.workbuddy\app\renderer-version.json` 与 `D:\workbuddy\startup-seed-version.json`。exe 版本 vs 标记文件版本不一致 = 更新只换了主程序、渲染端标记没跟上（"一更新就抽"的典型根）。
3. **崩溃记录（症状实锤）**：`D:\workbuddy\logs\Crash-Log\crash-report-*.json` 读 `entries[]` → `child_process_crash`（CLI exit:1，常牵扯插件 mod 加载）、`renderer_js_error`（如 queryRecommend 8s 超时）；主线程/扩展日志在 `D:\workbuddy\.workbuddy\logs\2026-MM-DD\`。
4. **残留/僵尸进程**：`Get-Process <App> | Select Id,StartTime,Responding`。更新时刻（近 30min）批量拉起的进程=僵尸嫌疑——**只点名不杀**（用户可能正用着）。
5. **先查有没有现成哨**：`ls logs/ | grep -iE 'update|watch|guard|sentinel|heal'`，别重复造轮子；有就在其上加，没有才新建。

## 安全边界（保守自愈）
- **只改工作区里的版本标记文件**（用户数据区，可备份可回滚），**不碰 `Program Files`/厂商 asar**。
- 每次写文件先 `shutil.copy2` 备份 `*.bak_<ts>`。
- 不杀活进程、不强行重启正在用的 App；厂商自身逻辑 bug（查询超时/子进程崩）只到"对齐标记 + 点名残留 + 报告"为止，不承诺根治。

## 装自愈哨（watchdog 模式，用户零动手）
1. 写**确定性**脚本（读 exe 版本 → 失同步自动对齐 → 判"刚更新"→ 点名近 30min 残留进程 → 落 report.json）。脚本放**稳定目录**（如 `hermes\ops\...`），别放会被 24h 清理的 scratch。
2. 挂 **no_agent cron** 每 30min 跑它；**全绿时 stdout 为空 = 静默不投递，有异常才投一行**（watchdog 模式，免刷屏）。
3. cron 的 `script` 字段**相对 `hermes\scripts\` 解析**：把脚本副本 `cp` 进该目录，调用时只写文件名（写绝对路径会被拒）。
4. 验活：手动跑一遍确认 exit 0 + 全绿静默；看 cron `next_run_at` 已排上。

## 坑
- exe 版本号常带 `.0` 尾（`5.9.3.0`）vs 标记文件 `5.9.3`——比对前归一（去尾部 `.0`），否则永远判"失同步"。
- 标记文件可能是对象（`{"version":...}`）也可能裸字符串——写回时**保持原结构**，别把对象写成字符串（读回 key 名再写回同名 key）。
- bash 调 powershell 取版本，输出走 GBK：subprocess 捕获加 `encoding="gbk", errors="replace"`，否则 reader 线程 UnicodeDecodeError（表象像脚本崩了，主线程其实拿到了值）。
- 判"近 30min 启动"要用 `StartTime` 与 `time.time()` 比，别用日志 mtime（那是日志落盘时刻，非进程拉起时刻）。

## 汇报口径（李彦明偏好）
- 大白话报：根（版本失同步）→ 果（子进程崩/查询超时）→ 已修（标记对齐+备份在）→ 已装（哨每 30min 自动体检，全绿静默、有异常才报）→ 台账留痕号。技术活全做完，落到用户手上的步骤=零。
