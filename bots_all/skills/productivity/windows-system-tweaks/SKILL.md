---
name: windows-system-tweaks
description: Use when 改 Windows 系统设置/注册表/语言输入法/语音识别语言等系统级开关。
---

# Windows 系统设置修改

针对本机 Windows（10/11）做系统级开关/注册表修改的标准做法。用户偏好：直接替他改完、给逐步骤+精确路径，别让他自己点。

## 核心工作流

1. **读取现状**：先查相关注册表/设置确认当前值，再改，避免盲写。
   - 读：`reg query "HKCU\\..." 2>&1 | head -40`（路径用双反斜杠转义；输出可能乱码，用键名+结构判断）。
   - 读 PowerShell 原生属性：`powershell -NoProfile -Command "Get-ItemProperty -Path 'HKCU:\\Control Panel\\...' | Format-List"`。
2. **修改**：用 PowerShell 写注册表，比 `reg add` 更稳、可带注释逻辑：
   - `powershell -NoProfile -Command "Set-ItemProperty -Path 'HKCU:\\...' -Name 'x' -Value 'y'"`
3. **回读验证**：改完立即 `Get-ItemProperty` 读回，确认落盘（write_file/terminal 结果里的 verified 不算，注册表要自己读回）。
4. **报告**：用中文大白话说清改了什么、下一步用户要做的操作（哪一步点哪里），不贴英文缩写堆叠。

## 关键坑（踩过的）

- **PowerShell 变量被嵌套吃掉**：通过 `execute_code` 的 `terminal(cmd)` 传含 `$` 的 PowerShell（如 `$r = ...; if ($null -ne $r)`）会被 heredoc 字符串拼接转义搞坏（`$` 被吞、报 "CommandNotFound"）。**解法：不套 execute_code，直接用 terminal 工具跑 `powershell -NoProfile -Command "..."`**，双引号包 PowerShell 脚本，`$` 保留。简单单行赋值/读写都没问题，只有多行脚本带 `$变量` 才危险，那就写 .ps1 文件或拆成多个单行 `-Command`。
- **键不存在不能 Set-ItemProperty**：`Set-ItemProperty` 对不存在的父键报 PathNotFound。**解法：先 `New-Item -Path 'HKCU:\\...' -Force | Out-Null` 再 Set**。`Get-ItemProperty` 报"找不到"要先 `New-Item`。
- **reg query / PowerShell 控制台输出中文是 GBK 乱码**：本机终端 bash 是 POSIX，中文显示成 `???` 或 GBK 字节。**别被乱码骗了——这是终端编码问题，不是系统问题**。判断值对不对用键名+结构（如 `0804`=zh-CN 简体），不要靠可读中文。需要可读时用 `Get-CimInstance Win32_OperatingSystem` 拿 Caption/Version（也是乱码但可判断），或把结果写文件再 read_file。
- **语言码速查**：`0804`=中文(简体)、`0409`=英语(美国)、`zh-Hans-CN`=简体。`HKCU\Control Panel\International\User` 下 `InputLocale`（当前输入法）、`LanguageProfileMap`（语言偏好映射）、`Locale`/`sLanguage`(CHS)。语音输入引擎跟 `LanguageProfileMap` 关联，锁成 `{zh-Hans-CN:zh-Hans-CN,0804:0804,0409:0804}` 可让语音/输入法回落中文简体。
- **改完要提醒重启/重新进才生效**：多数 `HKCU` 立即生效；`HKLM\SYSTEM` 或系统语言包要重启。改语音/输入法一般立即生效，Win+H 重开即可。
- **git-bash 调 schtasks 等部分原生 exe 会 Permission denied（管理员会话也一样）**：MSYS bash 直接跑 `schtasks /create` 被挡——一律走 `powershell -NoProfile -ExecutionPolicy Bypass -File xxx.ps1`（write_file 写 .ps1 再执行），`Register-ScheduledTask`/`Start-ScheduledTask`/`Get-ScheduledTask` 正常可用；查任务表也用 `Get-ScheduledTask | Select TaskName,State` 代替 schtasks /query。写 .ps1 注意：哈希表字面量多键用**分号**不用逗号（`@{a=1; b=2}` 合法，`@{a=1, b=2}` 语法错，write_file 代写易翻车，写完先跑一遍验证）。

## 常见子任务速查

- **锁默认输入法/语言为中文简体**：`New-Item 'HKCU:\\Control Panel\\International\\User' -Force` → `Set-ItemProperty -Name 'InputLocale' -Value '0804:00000804'` + `-Name 'LanguageProfileMap' -Value '{zh-Hans-CN:zh-Hans-CN,0804:0804,0409:0804}'`。
- **查系统当前语言**：`powershell -NoProfile -Command "Get-WinUserLanguageList"`（首行 LanguageTag 即当前）。
- **查区域/时区**：`reg query "HKCU\\Control Panel\\International" | head -20` 看 Locale/LocaleName。

## 红线

- 改 `HKLM` 需管理员；本机无 admin 时只能改 `HKCU`，改不了就明说哪步需要管理员，别假装成功。
- 不动金策 4 把专属 key 等铁律里的敏感区。