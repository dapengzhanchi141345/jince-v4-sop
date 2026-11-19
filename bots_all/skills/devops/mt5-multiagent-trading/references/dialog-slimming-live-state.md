# 对话瘦身铁律 + 真值源/终端运维(11-13/14 两轮, 李彦明两令'对话框太满/太慢, 深度优化')

## 对话瘦身总纲(稳态零投递)
- 原则: 所有 no_agent 确定性拍, **稳态=空 stdout(真静默, cron 空输出不发任何东西)**; 只在 状态翻转/异常/有增量信息 时出声; 留痕一律落本地 jsonl 台账, 不投群。
- 已上闸的拍(11-14 二轮验活通过):
  1. MFE/MAE 追踪(jince_mfe_mae_track.py): stdout 内容 hash 闸(scripts/mfe_last_delivered.json), 内容不变=0 字节; 变化才投(fail-open: 闸自身异常照投不吞消息)。
  2. 节点看门狗(jince_watchdog.py)心跳行: 指纹语义归一(gateway 'ok'/'ok(探活超时,fail-open不判挂)' 同判 up, 防探活抖动致指纹每拍变/稳态闸永不成立=11-14 上午纯心跳 15min 一刷的根因) + 同日稳态(watchdog_heartbeat_gate.json 带 day 字段, 状态翻转才报)。
  3. 体检(jince_daily_healthcheck.py 03:00): all_ok→本地 healthcheck_silent_log.jsonl 留痕+空输出; 有异常/有待续跑才报。08:45 汇报(jince_health_report.py)同口径(纯全绿静默, 有 reg 待续跑项照报)。
  4. 群主持(jgrouphost0900): 一天只留 21:00 收口场(cron '0 21 * * *'); 09/14 场=节点卡复读无增量, 已砍。
  5. 08:30 开盘前简报(ac80590fc779): 已 pause(与 08:05 节点卡+09:00 晨学哨重叠且 LLM 驱动易中断; 要恢复随时 resume)。
  6. 取件哨(jince_commons_pickup.py): 同主题同日去重(jince_commons_pickup_seen_subj.json), 主题尾时刻戳双式归一(\s+\d{1,2}:\d{2}$ 与 \s+\d{1,2}\s+\d{2}$ 两种都去, 防 'V4.1(现状优先) 07:40' 与 '做单思路 17 18' 两族刷屏); 换版本(主题变)照报。验活: 4 件同日重发归 1 报+再跑 0 字节。
- 总线周期重发处置(11-14 实证): 对方(进化营)收不到我方 ACK 会按'未回执重发'机制小时级重发(11-07 起 V4.1 重发 7 天, archive 几十件); 我方 5 张 ACK 全在 bus/outbox/hermes(对方 drain 才搬走, 11-14 09:01 对方 drain 56 封入箱才通)。解法=补投 ACK(五问要点全文直接写正文, 不依赖对方取件链路)+高优先级停止指令(outbox 20261114T102500-cmd-stop-v41); 我方取件哨同日同主题静默兜底。
- 投递层卡: 节点卡投不进群=看门狗重投(45min 冷却, 2h 重申)+22:00 兜底销账(内容落 discussion_log 零丢失); 根治开关=用户双击 E:\workbuddy\国外模型\hermes\一键重启网关.bat(网关存储间歇死, 探活超时 fail-open 不判挂)。

## 真值源 live_state.json 运维
- 写者=yushi(御史); 刷新命令: `E:\AgentCommons\yushi\bin\snapshot.cmd --shared`。坑: `E:\AgentCommons\bin\snapshot.cmd` 不存在(404, bin 下只有 commons/relay/state); state.cmd 只读不写(state.ps1 提示行里才有 yushi 路径)。
- 判据: ts 字段超 30min=过期, 报持仓/挂单/净值前先刷; 节点卡读过期 live_state 会拿陈旧持仓(11-14 10:05 卡列已销账的 KLAC/AVGO 实证), 卡上'⚠️ 非实盘断言'标是安全线, 但主 bot 发现过期要当场刷。
- 快照也会漏仓(11-14 10:10 快照 6 张 vs MT5 实读 7 张, 漏 EUSTX50)——两源不一致时以 MT5 活体实读为准, 并重新刷快照对齐。

## 终端 64 IPC 冻死窗运维
- terminal64.exe(账户 60137964)约 2h 自重启, 重启窗 30-60s IPC 冻死: ATE `mt5.initialize()` 无封顶会挂死到外层超时(11-14 12:44 MFE 拍挂 300s exit1 根因)。
- 铁律: 所有走 ATE 实读的脚本, initialize 一律 15s 封顶(_mfe_mae_track.py 已修, 线程 join(15) 模式; 节点卡脚本自带'initialize 握手 15s 封顶')。冻死窗表现=行情喂报'MT5 实读 0 品种, 沿用上份 tick'(exit1, 瞬态自愈, 等 30-60s 重读即可)。
- 进程确认: tasklist | grep terminal64(PID 在=终端活着, initialize 挂=重启窗内, 不是终端死)。
- **live_state 假零仓窗(11-15 实踩)**: terminal64 自重启/重登窗内, yushi 快照读到「进程活但未登录好」=positions 写 0(真实 7 张被写成 0, 共享真值源短暂错档, 其他岗那几分钟读 live_state 会把活仓误判空仓)。判据: live_state positions=0 **且** 1h 内 order_lifecycle.jsonl 无平仓记录=假零(真清仓必有账本平仓行)。已上防呆哨 jince_auto_patrol.py check_livestate_zero(): 命中判据→自动重跑 snapshot.cmd --shared, 刷回>0 报「已自愈」/仍 0 报「真零仓待核」, 同日同态静默、状态翻转即报。注意 native Python subprocess 调 bat 用 `cmd /c`(单斜杠, MSYS 双斜杠是 bash 侧写法)+ errors='ignore' 防 GBK 输出解码炸(§4/§5 坑)。

## L2拍 regime 门运维(11-14 夜修)
- jince_regime_zone_runner.py 由 cron 解释器跑, 该解释器**无 MetaTrader5 模块** → 本地 import 必挂(regime 全 UNKNOWN, 'No module named MetaTrader5' 实证)。
- 修法: regime 计算体拆成 `E:\GoldstrategyEngine\data\_regime_calc.py`, runner 用 ATE(`C:\Users\ASUS\.workbuddy\binaries\python\envs\ate\Scripts\python.exe`)spawn 子进程(90s 超时, 剥 PYTHONHOME/PYTHONPATH), JSON 一行合并回原结构; ATE 不可用回退旧本地逻辑(防呆不崩)。验活: 8 品种全出真 regime(BTC/ETH/SOL/XRP=HIGHVOL, XAU/US30=RANGE)。
- 时间戳坑: Python `strptime` 不认 shell 风格 `%F %T`(strftime 宽容/strptime 严格不对称), 首写时间戳即爆 ValueError(cron 拍 exit-1 根因); 一律用全指令 `%Y-%m-%d %H:%M:%S` + try/except 畸形 ts fail-safe。
