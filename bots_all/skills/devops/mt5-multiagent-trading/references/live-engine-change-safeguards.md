# 实盘引擎改动安全件（jince_live24.py 及同类确定性格）

## 抑制/去重窗必须成败分流（实盘风险级）
平仓/下单前的"抑制窗"（防重复发送/防重记）**只在成功时入窗**：成功（如 rc=10009 仓位已不存在）记 timestamp，窗内静默；**失败/异常必须 pop 该 key 放行重试**——全局 timestamp 不分成败会把"第一次发送失败（10030/网络/IPC 超时）"也堵死 10min，斩亏单/12h 强平/事件窗硬平第一次失败后就失效 = 实盘风险。判据：任何"防重"逻辑先问"失败后下一循环能不能重试"，不能 = 缺陷。

## close 语义单测 recipe（不碰实盘）
不 import 主循环文件（会连 MT5 跑主循环）：①`open().read()` 抽目标函数段（`SRC.index(a):SRC.index(b)`）②`exec(seg, ns)` 注入假依赖：FakeMT5（静态常量 TRADE_ACTION_DEAL/ORDER_*/`order_send(req)` 可控 retcode + calls 记录）、假 log_trade 落 list ③四场景断言：成功入窗→重调被抑制 / 失败后 key 被 pop→重试发出 / 多 ticket 互不干扰 / 异常放行。场景断言全过才算改对；py_compile 只证语法不证语义。

## 引擎重启: taskkill ~5min 拖尾，等看门狗接力
`taskkill /F` 引擎进程后 MT5 IPC/COM 资源拖尾 ~5min（多次实测同型）：拖尾期内手动拉起会被锁文件挡住（报"另一实例持锁"），属正常非故障。**规则：kill 后不立即手动拉起，等看门狗拖尾期后自动拉起，然后验锁 PID + 活仓 SL/TP 未被动 + 无双实例**；手动拉起只在确需缩短真空期时用，且被锁挡 = 等再看门狗，别连环 kill。
**本机 git-bash 杀进程坑**: `taskkill //F //PID` 在此 host(MSYS 路径转换关闭)会把 `//F` 原样传进去报"无效的参数/选项"——杀进程一律 `powershell -NoProfile -Command "Stop-Process -Id <pid> -Force"`; 查运行中引擎的启动时刻/命令行用 `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` 过滤 CommandLine 含 jince_live24(别信 tasklist 裸 pid, Windows pid 会复用)。

## MT5 numpy 坑（rates 扫描脚本）
`copy_rates_range/copy_rates` 返回 numpy 数组：`if not rates` 抛 `truth value ambiguous`（连炸 2 次的坑）——一律 `len(rates) == 0`；下标访问后取 float。脚本首跑先小规模干跑一次暴露这类坑，再上全量网格。

## 参数网格退化自检
网格扫描写完先自检**每个网格维度真的进了模拟体**：某维度只在"未触发=维持现状"兜底、模拟体没引用它 = 该维度 4 档全同值，N×M 组合实际退化成 N 组（曾 12 组合退化成 3）。自检法：对两档同结果断言 fail 应能触发；或读模拟体源码确认每个参数被引用。结论报表里注明实际有效组合数。

## 早锁利/棘轮类策略的结构性负判据
"峰值浮盈≥X 解锁→回吐至锁线砍"类早锁利：在**含大赢家的分母上**会把大赢家尾部利润切掉，表现为全参数组合净期望负 delta（样本扩大 2 倍后 9 样本的 3.29x 优势可完全反转）。判"调参能救"前先扫全网格：全组合负 = 结构性负，撤下换赢家（或融合进已验证机制），别再逐档磨参数；局部最优只在大赢家缺席的分母上存在 = 选择效应。

## 实盘体检（"实盘不能有 bug" 令的标准动作）
收到该令时跑一套：①py_compile 引擎 ②改动函数语义单测 ③单实例验（锁文件 PID = 活体 = wmic 进程三一致）④活仓 SL/TP 齐读（magic 实读）⑤ghost/重复日志哨（同 sym+ticket+reason 短窗去重计数）⑥台账留痕。全绿才报"无 bug"，报哪缺哪。

## L24 特性 flag 门控（候选修复上引擎的隔离机制）
候选参数/SL-TP 修复类改动**不直改默认行为**，走 flag 门控：`data/l24_feature_flags.json` = {magic, 各 flag 键, ts, note}，引擎启动读入，键 magic 必须等于本实例魔号才生效；magic 不符/文件缺失 = 零行为变化（进化营实例与 REAL 天然免疫）。flag 键例：`rrpref`（R:R 优先地板）、`adx_max`（入场 ADX 上限）、`atrop_syms`（列名单品种改走 ATR 基准点位 SL/TP、不做 60 根结构加宽——修"结构加宽 SL>6ATR → 2R 地板被 12ATR 封顶压死 → 质量闸必拒"死锁）。**生效时序坑（实测踩过）: flag 常量在 import 期读入——写 flag 文件必须在 kill/重启之前；重启后验新实例 CreationDate 晚于 flag 文件写入时刻，早于 = 该实例跑的是旧值，必须再杀一次**。五验不过的候选保持默认关闸不删码（留痕可翻回）；灰度裁定粒度 = 按品种名单（任一品种明确变差 => 该品种出局，不拖累过闸品种，不翻全族）；WATCH 级（5 折 <4/5 正）只上单品种 DEMO 灰度 + rd_watchlist 前向 OOS 接力指针，攒够样本同分母复验才 PROMOTE 全族。翻闸留痕三件套：task_ledger + rd_ledger + flag 文件 note 互指。
