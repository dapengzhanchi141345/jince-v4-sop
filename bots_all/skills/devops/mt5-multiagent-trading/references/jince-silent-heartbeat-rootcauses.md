# 金策心跳/全链静默的两个根因（2026-11-03 定位）

## 根因 A：JinCe 计划任务被反复停成 Disabled（chief 心跳"冻结"）
当 chief 全链心跳"冻结"（最后完成拍 >30min 无新拍、watchdog 点名 @chief）时，
**先查驱动它的 Windows 计划任务是否被停成 Disabled，而不是先怀疑脚本崩/429。**

金策三个任务会翻成 State=Disabled 后静默停拍：
- `JinCeAutoCycle` — 驱动全链 auto_cycle（chief 心跳）
- `JinCeWatchdog` — 巡检/看门狗
- `JinCeEventGuard` — 5min 事件快通道

诊断（一条命令看三个状态）：
```
powershell -NoProfile -Command "Get-ScheduledTask -TaskName JinCeAutoCycle,JinCeWatchdog,JinCeEventGuard | ForEach-Object { $_.TaskName+'='+$_.State }"
```
State=Disabled = 元凶。修复 + 验一拍：
```
powershell -NoProfile -Command "Enable-ScheduledTask -TaskName 'JinCeAutoCycle'; Start-ScheduledTask -TaskName 'JinCeAutoCycle'"
tail E:/GoldstrategyEngine/data/auto_cycle.log   # 看 [全链自动运行完成] 是否出新拍
```
每次全链/事件快通道静默，都复核这三个任务有没有又被停（它们会反复 Disabled）。
observed: 02:53 chief 冻结 = JinCeAutoCycle 被停；03:03 事件快通道静默 = JinCeEventGuard 被停。

## 根因 B：MT5 共享终端 8736 IPC 互斥 = 间歇冻死（strategy-rd 实读）
回测引擎 + 实盘 OOS runner + live24 共用终端 8736 → MT5 IPC 层间歇互斥冻死。
症状（同一病根，多处发作）：
- 00:10 每日回测 TIMECAP 出空件（单品种 3060s 未完成 fail-open 跳过，n=0 无 K 线）→ 01:30 验收 FAIL-LOUD（edge 未刷新 >36h）
- 风控闸 LEVEL=2（mt5=False、价源 broker 专线断→全冻结 ban_cancel/ban_modify_sl）把 chief 全链拖慢 50+min（07:27→08:20 空档）
- 03:45 行情喂 "MT5 实读 0 品种"（tick_live 沿用上份）
- live24 引擎凌晨反复死（"夜间断流" 复现：OOS runner 32900→9252→79936、live24 47480→13184），看门狗逐次自愈拉起（持仓 SL/TP 在服务器端、引擎死也不裸奔）

terminal64.exe（8736）本身活着、`mt5.initialize()` 能 attach（读到 login/品种数），但 IPC 握手会**间歇**白磨 → 所以是"时好时坏"而非全断。

根治方向（strategy-rd 提、截至 2026-11-03 尚未落地）：
- 方向 (b) 回测改读**本地缓存 K 线文件**、不碰 live IPC（非破坏、不动实盘终端 8736、不断 OOS 证据链）→ 从根上消"双引擎共终端抢 IPC"。
落地前这些间歇冻会反复发生、靠看门狗 + 上面根因 A 的重新启用逐次救。

## 附带：git dubious ownership（_skills_mirror）
`E:/workbuddy/国外模型/hermes/_skills_mirror` 属主是换户口后的不可映射旧 SID，`git ls-files` 报
dubious ownership。修复已做：`git config --global --add safe.directory "E:/workbuddy/国外模型/hermes/_skills_mirror"`
（safe.directory 已有多个值，必须用 --add 不能单值覆盖）。详见 github-auth 技能 Pitfall 16。
