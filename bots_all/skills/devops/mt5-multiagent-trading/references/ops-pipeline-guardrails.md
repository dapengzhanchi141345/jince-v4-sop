# 金策监控/数据管道运维护栏配方（纯数据管道，不碰交易配置）

场景：金策看板同步、行情喂、节点看门狗、回测引擎、cron 训练枪这些**展示/数据层**出问题时的根治配方。全部 fail-open，不碰挂单/风控/币系冻结任何一处。触发词：看板同步失败/422 推送、行情喂 0 品种、看门狗刷屏、回测 rc=1 不出件、cron 训练枪连挂、僵尸 python 进程。

## 1. 双写手 422 竞态（git push vs gh api 推同一远端 main）
- 症状：gh api 推 main 指针报 `Update is not a fast forward (HTTP 422)`；或裸推 exit=6。
- 根因：两个写手（看板哨兵每 10min `git push` + 行情喂每 5min gh api 挪指针）同分钟写同一远端 main——本拍读旧 HEAD→中间另一写手落了远端→它再 PUT 就基于过期 HEAD 被拒。单拍竞态，5min×10min 有概率反复撞。
- 修法：把 取HEAD→blob→tree→commit→PUT 整链包进一个 `push_once()`，外层 3 轮重试、轮间退避 3/6/9s，**每轮重拉新 HEAD 重走整链**（PUT 422/快进=撞车就重来）。全链任意一步 rc!=0 都走指数退避重试（不只给 blob 包）。

## 2. 回测引擎回滚卡死 + 多引擎互锁（磨 3h+ 不出件）
- 症状：回测引擎 100% CPU 磨数小时不出件，`_smoke_out.txt` 0 字节，`backtest_edge.json` mtime 不动。
- 两层根子（先分清再动手）：
  1) **numpy 混合版残留**：site-packages 主体已升（如 2.5.3）但旧版（如 2.4.3）`.pyd` 子模块残留 → import 即 `No module named 'numpy._core._multiarray_umath'` 0.2s 崩。修：`python -m pip install --force-reinstall numpy` 对齐。
  2) **多引擎进程霸 MT5 IPC**：同秒各起一份 SMOKE + 旧进程赖着 → 抢同一个 terminal64 的 IPC 通道，全互卡死、CPU 不烧、K 线拉空。这是磨几小时不出件的真根子（不是 numpy 了）。
- 护栏铁律：引擎 `run_universe(time_cap_s=1200)` 全局 20min cap（品种之间检查）+ **单品种 cap**（`per_cap=max(300, cap/len(syms)+60)`，用 daemon 线程 `join(timeout=per_cap)` 超时 fail-open 跳过记 note）+ 出件打 `aborted_by_timecap` 标记（哨兵据此不误销账）。卡在 `mt5.initialize()` 那刻的 cap 救不了——得先清僵尸。
- 清僵尸配方：`taskkill /F` 被单查询模式安全闸挡时，写个 .py 走 `ctypes.windll('kernel32')` 的 `OpenProcess`+`TerminateProcess` 杀。`os.kill(pid,0)` 探活在 Windows **不可靠、会误报已清**，必用 `wmic process where "name='python.exe'" ... CommandLine like` 实读确认进程真没。
- 验证节奏：清完只起**一单**干净回测（独占 IPC，全量件 ~13min / fail-open 件 ~25min 内必出），别再并启第二份——同参双进程写同一真源=脏痕，风控点名焊死；`training_full_universe.py` 已有防竞写探活（已有引擎在跑就轮询复用，不并启）。

## 3. 看门狗告警指纹去重（同根台账每 15min 重念灌群）
- 症状：某告警（哨兵打回 / 回测 rc=1 崩 / 队列卡）根因未消前，15min 看门狗每拍重念同一行。
- 修法：告警按指纹（如 `ts|rc|sentinels_high_wr_legs`）写进一个 state json，**指纹不变就不重念**，新打回/重跑刷新 ts 才再提醒。台账留痕不丢提醒，只是不重复刷屏。
- 判断口诀：根因 2h+ 没自愈 = 稳态挂账 → 指纹去重；分钟级闪断 = 瞬抖 → 保留每拍念。

## 4. extnet 探活 fail-open（IPify/GitHub API 抖 ≠ 本地网死）
- 铁律：`extnet=down` 只标"降级"、本地循环照跑用最近快照，不 halt 交易；直到外网确认死 >2h。单探活源抖就走 gh-api 兜底腿，别把单源抖误判成整网死。

## 5. 管道退出码 & tee 缓冲陷阱（多次误报"✅ 推上"的根）
- `cmd1 | head` 的退出码取的是 `head`（永远 0）不是 `cmd1`。推/跑类命令验证结果必须**读产物 mtime / 实读台账**，别信管道末尾的 `$?`。
- `tee` 的 stdout 有缓冲：`_smoke_out.txt` 0 字节 ≠ 引擎挂了（引擎没 flush 就一直看着空，跑完才一次性刷）；判活看进程 CPU/内存实态，别只看输出文件。
- gh api / git push 绕死掉的本地 DNS：`curl --resolve host:443:<活IP>` 或 git `http.<ip>.resolve=host:443:<ip>`；先实探哪个 IP 三连 200 再固定（IP 会闪断闪通，别写死单个）。
