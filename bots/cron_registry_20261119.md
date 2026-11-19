# Bot 花名册 · cron 注册表 (2026-11-19 全量导出)

共 112 个定时任务 (bot=脚本型no_agent + agent型提示词)。重建法: 逐行 cronjob_manage 注册.

| 名称 | 计划 | 脚本/提示词 | 模式 | 使能 | 投递 |
|---|---|---|---|---|---|
| AUS200撤单重试(市场开即撤) (``) | {'kind': 'once', 'run_at': '2026-11-17T16:00:38.536840+08:00', 'display': 'once in 2h'} | 金策 AUS200 撤单重试(李彦明11-17令'把挂单撤了'的残留件): 用 ATE 通道(D:/workbuddy/binaries/p | agent | False | origin |
| Hermes桌面端·中文路径守护哨·30min (``) | {'kind': 'interval', 'minutes': 30, 'display': 'every 30m'} | hermes_cnpath_guard.py | 脚本 | True | origin |
| P1修复批重派(池WALL解除后) (``) | {'kind': 'once', 'run_at': '2026-11-17T10:57:28.265377+08:00', 'display': 'once in 2h'} | 金策P1修复批重派件(11-17 09:0x主bot挂): 先读 E:\GoldstrategyEngine\data\agnes_key_ | agent | False | origin |
| SNDK闸门复查_1112 (``) | {'kind': 'once', 'run_at': '2026-11-12T23:05:00+08:00', 'display': 'once at 2026-11-12 23:05'} | 22:16做单思路SNDK.NAS空单候选(质量榜期望+0.15R, RR2.0, 扣0.095R成本后+0.055R正期望, 当日唯一过成 | agent | False | origin |
| WorkBuddy桌面端·更新自愈哨·30min (``) | {'kind': 'interval', 'minutes': 30, 'display': 'every 30m'} | workbuddy_postupdate_selfheal.py | 脚本 | True | origin |
| agnes-pool-guard (``) | {'kind': 'cron', 'expr': '*/5 * * * *', 'display': '*/5 * * * *'} | agnes_pool_guard.py | 脚本 | True | local |
| auto-soul-exit-10m (``) | {'kind': 'cron', 'expr': '*/10 * * * *', 'display': '*/10 * * * *'} | auto_soul_exit_watch_1119.py | 脚本 | True | origin |
| auto-soul-sweep-30m (``) | {'kind': 'cron', 'expr': '*/30 * * * *', 'display': '*/30 * * * *'} | auto_soul_sweep_1119.py | 脚本 | True | origin |
| bot-sota-monthly-upgrade (``) | {'kind': 'cron', 'expr': '30 3 1,15 * *', 'display': '30 3 1,15 * *'} | bot_sota_scan.py | agent | True | local |
| bot-soul-smoke-monthly (``) | {'kind': 'cron', 'expr': '30 4 1 * *', 'display': '30 4 1 * *'} | 你是 Hermes 主 bot 的维护任务：每月给金策 3 个交易 bot + 3 个重点专家 bot 的 SOUL/SOTA 做一次冒烟验 | agent | True | local |
| jince-fail-scan-30min (``) | {'kind': 'cron', 'expr': '*/30 * * * *', 'display': '*/30 * * * *'} | jince_rerun_immediate.py | 脚本 | True | origin |
| jince-midday-asia-1005 (``) | {'kind': 'cron', 'expr': '5 10 * * *', 'display': '5 10 * * *'} | jince_midday_deep.py | 脚本 | True | bot-chat |
| jince-midday-europe-1635 (``) | {'kind': 'cron', 'expr': '35 16 * * *', 'display': '35 16 * * *'} | jince_midday_deep.py | 脚本 | True | bot-chat |
| jince-midday-us-2335 (``) | {'kind': 'cron', 'expr': '35 23 * * *', 'display': '35 23 * * *'} | jince_midday_deep.py | 脚本 | True | bot-chat |
| jince-node-london-close-1800 (``) | {'kind': 'cron', 'expr': '5 18 * * *', 'display': '5 18 * * *'} | jince_node.py | 脚本 | True | bot-chat |
| jince-node-london-open-1500 (``) | {'kind': 'cron', 'expr': '5 15 * * *', 'display': '5 15 * * *'} | jince_node.py | 脚本 | True | bot-chat |
| jince-node-ny-close-0200 (``) | {'kind': 'cron', 'expr': '5 2 * * *', 'display': '5 2 * * *'} | jince_node.py | 脚本 | True | bot-chat |
| jince-node-ny-open-2100 (``) | {'kind': 'cron', 'expr': '5 21 * * *', 'display': '5 21 * * *'} | jince_node.py | 脚本 | True | bot-chat |
| jince-node-tokyo-close-1200 (``) | {'kind': 'cron', 'expr': '5 12 * * *', 'display': '5 12 * * *'} | jince_node.py | 脚本 | True | bot-chat |
| jince-node-tokyo-open-0800 (``) | {'kind': 'cron', 'expr': '5 8 * * *', 'display': '5 8 * * *'} | jince_node.py | 脚本 | True | bot-chat |
| jince-synth-meeting-sat (``) | {'kind': 'cron', 'expr': '5 9 * * 6', 'display': '5 9 * * 6'} | jince_synth_meeting.py | 脚本 | True | bot-chat |
| jince-synth-meeting-sun (``) | {'kind': 'cron', 'expr': '5 15 * * 0', 'display': '5 15 * * 0'} | jince_synth_meeting.py | 脚本 | True | bot-chat |
| jince-weekly-review (``) | {'kind': 'cron', 'expr': '5 16 * * 5', 'display': '5 16 * * 5'} | jince_weekly_review.py | 脚本 | True | bot-chat |
| morning-report-1118 (``) | {'kind': 'once', 'run_at': '2026-11-18T07:30:00+08:00', 'display': 'once at 2026-11-18 07:30'} | jince_morning_report_wrapper.py | 脚本 | False | origin |
| order-xp-daily-2015 (``) | {'kind': 'cron', 'expr': '15 20 * * *', 'display': '15 20 * * *'} | order_xp_daily_1119.py | 脚本 | True | origin |
| param-officer-30m (``) | {'kind': 'interval', 'minutes': 30, 'display': 'every 30m'} | jince_param_officer_wrapper.py | 脚本 | True | origin |
| redline-eur-1120-0635 (``) | {'kind': 'once', 'run_at': '2026-11-20T06:35:00+08:00', 'display': 'once at 2026-11-20 06:35'} | jince_redline_force_wrapper.py | 脚本 | True | origin |
| redline-soulwave-1120-0940 (``) | {'kind': 'once', 'run_at': '2026-11-20T09:40:00+08:00', 'display': 'once at 2026-11-20 09:40'} | jince_redline_force_wrapper.py | 脚本 | True | origin |
| redline-v4wave-1119-0840 (``) | {'kind': 'once', 'run_at': '2026-11-19T08:40:00+08:00', 'display': 'once at 2026-11-19 08:40'} | jince_redline_force_wrapper.py | 脚本 | False | origin |
| sentinel-health-30m (``) | {'kind': 'interval', 'minutes': 30, 'display': 'every 30m'} | sentinel_health_wrapper.py | 脚本 | True | origin |
| slv2-eth-2100 (``) | {'kind': 'once', 'run_at': '2026-11-17T21:00:00+08:00', 'display': 'once at 2026-11-17 21:00'} | slv2_eth_1117_wrapper.py | 脚本 | False | origin |
| slv2-eth-2130-retry (``) | {'kind': 'once', 'run_at': '2026-11-17T21:30:00+08:00', 'display': 'once at 2026-11-17 21:30'} | slv2_eth_1117_wrapper.py | 脚本 | False | origin |
| slv2-sol-2100 (``) | {'kind': 'once', 'run_at': '2026-11-17T21:00:00+08:00', 'display': 'once at 2026-11-17 21:00'} | slv2_sol_1117_wrapper.py | 脚本 | False | origin |
| slv2-sol-2130-retry (``) | {'kind': 'once', 'run_at': '2026-11-17T21:30:00+08:00', 'display': 'once at 2026-11-17 21:30'} | slv2_sol_1117_wrapper.py | 脚本 | False | origin |
| soul-wave-btc-2100 (``) | {'kind': 'once', 'run_at': '2026-11-17T21:00:00+08:00', 'display': 'once at 2026-11-17 21:00'} | soul_wave_1117_wrapper.py | 脚本 | False | origin |
| soul-wave-btc-2130-retry (``) | {'kind': 'once', 'run_at': '2026-11-17T21:30:00+08:00', 'display': 'once at 2026-11-17 21:30'} | soul_wave_1117_wrapper.py | 脚本 | False | origin |
| soulwave-auto-2135 (``) | {'kind': 'once', 'run_at': '2026-11-19T21:35:00+08:00', 'display': 'once at 2026-11-19 21:35'} | auto_wave_soul_1119.py | 脚本 | True | origin |
| system-patrol-30m (``) | {'kind': 'cron', 'expr': '*/30 * * * *', 'display': '*/30 * * * *'} | system_patrol_1119.py | 脚本 | True | origin |
| xau-touch-2200 (``) | {'kind': 'once', 'run_at': '2026-11-19T22:00:00+08:00', 'display': 'once at 2026-11-19 22:00'} | xau_wave_touch_1119.py | 脚本 | True | origin |
| xau-touch-2330 (``) | {'kind': 'once', 'run_at': '2026-11-19T23:30:00+08:00', 'display': 'once at 2026-11-19 23:30'} | xau_wave_touch_1119.py | 脚本 | True | origin |
| 各学科网站·凌晨2点升级+部署 (``) | {'kind': 'cron', 'expr': '0 2 * * *', 'display': '0 2 * * *'} | sites_upgrade_and_deploy.py | 脚本 | True | bot-chat |
| 各学科网站·凌晨4点升级 (``) | {'kind': 'cron', 'expr': '30 7 * * *', 'display': '30 7 * * *'} | sites_daily_upgrade.py | 脚本 | False | local |
| 各学科网站·凌晨4点升级+部署 (``) | {'kind': 'cron', 'expr': '0 4 * * *', 'display': '0 4 * * *'} | sites_upgrade_and_deploy.py | 脚本 | False | bot-chat |
| 各学科网站·凌晨5点汇报 (``) | {'kind': 'cron', 'expr': '0 5 * * *', 'display': '0 5 * * *'} | sites_daily_report_0845.py | 脚本 | True | bot-chat |
| 各学科网站·每日2230通报 (``) | {'kind': 'cron', 'expr': '30 22 * * *', 'display': '30 22 * * *'} | sites_daily_report.py | 脚本 | True | local |
| 审查闸哨兵-15m (``) | {'kind': 'interval', 'minutes': 15, 'display': 'every 15m'} | action_review_watch.py | 脚本 | True | weixin:o9cq80y1wgC-Z_7mz1TyQYgux1zU@im.wechat,bot-chat |
| 技能·GitHub 夜间全推 (``) | {'kind': 'cron', 'expr': '30 4 * * *', 'display': '30 4 * * *'} | skills_github_sync.py | 脚本 | False | bot-chat |
| 教联日更流水线·山海拾珍(切轨12-19) (``) | {'kind': 'cron', 'expr': '0 5 * * *', 'display': '0 5 * * *'} | 你是「教联中枢」(教育IP总控调度师), 现在执行每日 05:00 日更流水线。工作目录 E:\workbuddy\公众号。必读文件: ①规 | agent | False | origin |
| 李彦明·数字分身每日培养 (``) | {'kind': 'cron', 'expr': '30 7 * * *', 'display': 'every day at 07:30'} | 你是李彦明的数字分身培养管线（由主 bot default 执行）。任务（全程自主，不问人）：
1) 先读 D:\分身之家\档案\李彦明_分 | agent | True | local |
| 每日晨报-chief-of-staff (``) | {'kind': 'cron', 'expr': '0 7 * * *', 'display': 'every day at 7:00'} | morning_brief_collect.py | agent | True | weixin:o9cq80y1wgC-Z_7mz1TyQYgux1zU@im.wechat,bot-chat |
| 论文课题流水线·格物致知(周六09:00) (``) | {'kind': 'cron', 'expr': '0 9 * * 6', 'display': '0 9 * * 6'} | 你是「格物致知科研智库」主理人，执行每周六 09:00 前沿论文流水线（李老师终审签字制：产出落盘归档，不代发、不投）。必读：E:\work | agent | False | origin |
| 金策 12h强平哨 hc_xau3923_1116 (``) | {'kind': 'once', 'run_at': '2026-11-17T10:13:16.788997+08:00', 'display': 'once at 2026-11-17 10:13'} | 金策 12h 强平哨 hc_xau3923_1116 到点(22:00): 用 ATE 通道(C:/Users/ASUS/.workbudd | agent | False | bot-chat |
| 金策 Agnes key 哨(每日00:05全量探活+429回收) (``) | {'kind': 'cron', 'expr': '5 0 * * *', 'display': '5 0 * * *'} | jince_agnes_key_sentinel.py | 脚本 | True | bot-chat |
| 金策12h强平哨_v4wave三腿_1119 (``) | {'kind': 'once', 'expr': '*/30 * * * *', 'display': '*/30 * * * *', 'run_at': '2026-11-19T09:45:00+08:00'} | sd_forceclose_cron.py | 脚本 | False | origin |
| 金策24h心跳看门狗·每30min点名 (``) | {'kind': 'cron', 'expr': '0,30 * * * *', 'display': '0,30 * * * *'} | jince_heartbeat_watch.py | 脚本 | True | bot-chat |
| 金策2h效率播报 (``) | {'kind': 'cron', 'expr': '0 0,2,4,6,8,10,12,14,16,18,20,22 * * *', 'display': '0 0,2,4,6,8,10,12,14,16,18,20,22 * * *'} | jince_eff_report.py | 脚本 | True | bot-chat |
| 金策MFE/MAE活单追踪·30min (``) | {'kind': 'interval', 'minutes': 30, 'display': 'every 30m'} | jince_mfe_mae_track.py | 脚本 | True | bot-chat |
| 金策·GitHub 夜间全推 (``) | {'kind': 'cron', 'expr': '0 3 * * *', 'display': '0 3 * * *'} | jince_github_sync.py | 脚本 | False | bot-chat |
| 金策·L2代理+regime门·每30min (``) | {'kind': 'cron', 'expr': '*/30 * * * *', 'display': '*/30 * * * *'} | jince_regime_zone_runner.py | 脚本 | True | bot-chat |
| 金策·MC+VaR风控量化哨·每日0745 (``) | {'kind': 'cron', 'expr': '45 7 * * *', 'display': '45 7 * * *'} | jince_mc_var_report.py | 脚本 | True | bot-chat |
| 金策·SD12h强平哨·每30min (``) | {'kind': 'cron', 'expr': '*/30 * * * *', 'display': '*/30 * * * *'} | sd_forceclose_cron.py | 脚本 | True | origin |
| 金策·SD二道波2240补挂 (``) | {'kind': 'once', 'run_at': '2026-11-16T22:40:00+08:00', 'display': 'once at 2026-11-16 22:40'} | sd_place_fx_monday.py | 脚本 | False | origin |
| 金策·SD外汇周一挂单2105 (``) | {'kind': 'once', 'run_at': '2026-11-17T10:12:41.149736+08:00', 'display': 'once at 2026-11-17 10:12'} | sd_place_fx_monday.py | 脚本 | False | origin |
| 金策·kill switch月度纸面演练·0730 (``) | {'kind': 'cron', 'expr': '30 7 1,15 * *', 'display': '30 7 1,15 * *'} | jince_kill_switch_drill.py | 脚本 | True | bot-chat |
| 金策·strategy-rd主动优化深督·每日10点 (``) | {'kind': 'cron', 'expr': '0 10 * * *', 'display': 'every day at 10am'} | 金策主bot执行李彦明11-12令: 深督strategy-rd主动策略优化(主动模式, 每48h一命题, 首交不晚11-14 09:00) | agent | True | local |
| 金策·一键kill switch看守·每1min (``) | {'kind': 'cron', 'expr': '*/1 * * * *', 'display': '*/1 * * * *'} | jince_kill_switch_watch.py | 脚本 | True | bot-chat |
| 金策·交付验活哨·30min(防空交付) (``) | {'kind': 'cron', 'expr': '*/30 * * * *', 'display': '*/30 * * * *'} | 你是金策交付验活哨。monitor 每30min 跑 jince_delivery_verify.py（确定性，复核所有DONE宣称的交付物 | agent | True | bot-chat |
| 金策·任务续跑执行器·每30min (``) | {'kind': 'interval', 'minutes': 30, 'display': 'every 30m'} | 【金策·任务续跑制度】monitor 只有在本批『确有任务到点该续』时才叫醒你(输出不变你被抑制=不烧LLM、不撞429)。台账:E:/Go | agent | True | bot-chat |
| 金策·全链路验证哨·每30min (``) | {'kind': 'cron', 'expr': '*/30 * * * *', 'display': '*/30 * * * *'} | jince_verify_all.py | 脚本 | True | bot-chat |
| 金策·分品系深研R1币系·2330 (``) | {'kind': 'once', 'run_at': '2026-11-14T23:30:00+08:00', 'display': 'once at 2026-11-14 23:30'} | 你是金策 strategy-rd 夜间深研执行臂。本轮主题=币系做单思路全网深学优化。任务: ①读 E:/GoldstrategyEngin | agent | False | bot-chat |
| 金策·分品系深研R2黄金FX·0130 (``) | {'kind': 'once', 'run_at': '2026-11-15T01:30:00+08:00', 'display': 'once at 2026-11-15 01:30'} | 你是金策 strategy-rd 夜间深研执行臂。本轮主题=黄金+外汇品系做单思路优化。任务: ①读 E:/GoldstrategyEngi | agent | False | bot-chat |
| 金策·分品系深研R3股指ORR·0330 (``) | {'kind': 'once', 'run_at': '2026-11-15T03:30:00+08:00', 'display': 'once at 2026-11-15 03:30'} | 你是金策 strategy-rd 夜间深研执行臂。本轮主题=股指/股票 ORB(P5)+财报季做单思路优化。任务: ①读 E:/Goldst | agent | False | bot-chat |
| 金策·分品系深研R4汇总·0530 (``) | {'kind': 'once', 'run_at': '2026-11-15T05:30:00+08:00', 'display': 'once at 2026-11-15 05:30'} | 你是金策 strategy-rd 夜间深研汇总执行臂。本轮=夜间 4 轮深研汇总+执行层参数固化。任务: ①读 E:/Goldstrateg | agent | False | bot-chat |
| 金策·后台训练·全宇宙回测(00:10不限时) (``) | {'kind': 'cron', 'expr': '10 0 * * *', 'display': '10 0 * * *'} | training_full_universe_wrapper.py | 脚本 | True | local |
| 金策·后台训练·每日回测验收 (``) | {'kind': 'cron', 'expr': '30 1 * * *', 'display': '30 1 * * *'} | training_run.py | 脚本 | True | origin |
| 金策·周一开盘哨·1116 06:10 (``) | {'kind': 'once', 'run_at': '2026-11-16T15:16:50.544643+08:00', 'display': 'once at 2026-11-16 15:16'} | 你是金策主bot。周一06:10 BJT: FX 06:00/黄金07:00刚重开。任务: ①读 E:/GoldstrategyEngine | agent | False | bot-chat |
| 金策·哨兵死信开关·每15min (``) | {'kind': 'cron', 'expr': '*/15 * * * *', 'display': '*/15 * * * *'} | jince_sentinel_liveness.py | 脚本 | True | bot-chat |
| 金策·宿主闸验·0030 (``) | {'kind': 'cron', 'expr': '30 0 * * *', 'display': '30 0 * * *'} | training_host_gate_check.py | 脚本 | True | local |
| 金策·币系0.01样本腿6h滚动平仓+方向轮换·进化加速 (``) | {'kind': 'interval', 'minutes': 360, 'display': 'every 360m'} | roll6h_1108.py | 脚本 | True | origin |
| 金策·币系茶歇峰触发哨·1115 00:30 (``) | {'kind': 'once', 'run_at': '2026-11-15T00:30:00+08:00', 'display': 'once at 2026-11-15 00:30'} | 你是金策主bot执行臂。任务: 币系茶歇峰(16-17UTC)触发检查。步骤: ①跑探针 C:/Users/ASUS/.workbuddy/ | agent | False | bot-chat |
| 金策·开单通道自修复链·每5min(拒单=我方问题立即修) (``) | {'kind': 'cron', 'expr': '10,40 * * * *', 'display': '10,40 * * * *'} | order_channel_selfheal_1108.py | 脚本 | True | origin |
| 金策·执行预检日检·0730 (``) | {'kind': 'cron', 'expr': '30 7 * * *', 'display': '30 7 * * *'} | jince_exec_preflight_daily.py | 脚本 | True | bot-chat |
| 金策·换网自适应桥切换哨·每30min (``) | {'kind': 'interval', 'minutes': 30, 'display': 'every 30m'} | bridge_adapt_watch.py | 脚本 | True | origin |
| 金策·故障任务即时补跑哨·每30min (``) | {'kind': 'cron', 'expr': '*/30 * * * *', 'display': '*/30 * * * *'} | 故障补跑哨·红件复核层(v5降级: jince-fail-scan-30min=确定性主层, 本层只做红件复核不重复其活): ①查 jinc | agent | True | origin |
| 金策·数据官哨兵·每30min(K线新鲜度闸+原子刷新) (``) | {'kind': 'cron', 'expr': '*/30 * * * *', 'display': '*/30 * * * *'} | 数据官30min哨兵: 全绿只打[数据官OK]静默; 陈旧/坏件自动MT5原子刷新(npz.tmp->replace); MT5挂=exit | agent | True | bot-chat |
| 金策·方向反馈环·每日巡检 (``) | {'kind': 'cron', 'expr': '30 21 * * *', 'display': '30 21 * * *'} | direction_feedback.py | 脚本 | True | bot-chat |
| 金策·晨间汇总Word·0715 (``) | {'kind': 'once', 'run_at': '2026-11-15T07:15:00+08:00', 'display': 'once at 2026-11-15 07:15'} | 你是金策 chief。晨间汇总: ①读 E:/GoldstrategyEngine/research/family_deep_study_l | agent | False | bot-chat |
| 金策·每日03:00全面深度体检 (``) | {'kind': 'cron', 'expr': '0 3 * * *', 'display': '0 3 * * *'} | jince_daily_healthcheck.py | 脚本 | True | bot-chat |
| 金策·验尸官信箱中继·每6h (``) | {'kind': 'cron', 'expr': '0 2,8,14,20 * * *', 'display': '0 2,8,14,20 * * *'} | 你是金策·验尸官(post-mortem)中继执行。任务: 处理 E:/AgentCommons/bus/inbox/post-mortem | agent | True | local |
| 金策·验尸进化哨·每日0230 (``) | {'kind': 'cron', 'expr': '30 2 * * *', 'display': '30 2 * * *'} | sd_evolution_postmortem.py | 脚本 | True | origin |
| 金策·高流动性K线每日刷新(防断更) (``) | {'kind': 'cron', 'expr': '30 7 * * *', 'display': '30 7 * * *'} | jince_daily_csv_refresh.py | 脚本 | True | local |
| 金策共同体·自动取件哨·每15min (``) | {'kind': 'cron', 'expr': '25,55 * * * *', 'display': '25,55 * * * *'} | jince_commons_pickup.py | 脚本 | True | bot-chat |
| 金策宗师团·08:30开盘前简报 (``) | {'kind': 'cron', 'expr': '30 8 * * *', 'display': '30 8 * * *'} | 你是金策宗师团总调度，执行每日 08:30 开盘前简报（自包含指令，无对话上下文）。步骤：1) terminal 运行 `cd E:\Gol | agent | False | bot-chat |
| 金策宗师团·11-02冬令生死测拉数(一次性闹钟) (``) | {'kind': 'cron', 'expr': '0 9 2 11 *', 'display': '0 9 2 11 *'} | 执行 11-02 冬令生死测拉数(确定性脚本, 不烧 key 分析): 用 terminal 运行 cd E:\GoldstrategyEn | agent | True | bot-chat |
| 金策宗师团·22:00事件日报+复盘 (``) | {'kind': 'cron', 'expr': '0 22 * * *', 'display': '0 22 * * *'} | 你是金策宗师团总调度，执行每日 22:00 事件日报+复盘（自包含指令，无对话上下文）。步骤：1) terminal 运行 `cd E:\G | agent | True | bot-chat |
| 金策宗师团·全链扫描 (``) | {'kind': 'cron', 'expr': '45 13,18,21 * * 1-5', 'display': '45 13,18,21 * * 1-5'} | jince_fullchain_scan.py | 脚本 | True | bot-chat |
| 金策宗师团·月度P4出徒评审 (``) | {'kind': 'cron', 'expr': '0 9 1 * *', 'display': '0 9 1 * *'} | 你是金策宗师团总调度，执行每月 P4 出徒评审（自包含指令，无对话上下文）。步骤：1) terminal 运行 `cd E:\Goldstr | agent | True | bot-chat |
| 金策家属盈亏·2005 (``) | {'kind': 'cron', 'expr': '5 20 * * *', 'display': '5 20 * * *'} | family_pnl_summary.py | 脚本 | True | bot-chat |
| 金策技术验证面板·2010 (``) | {'kind': 'cron', 'expr': '10 20 * * *', 'display': '10 20 * * *'} | jince_learn_verify.py | 脚本 | True | local |
| 金策日结进化·2000 (``) | {'kind': 'cron', 'expr': '0 20 * * *', 'display': 'every day at 8pm'} | 你是金策日结进化哨（每日20:00）。第一步先读 E:/workbuddy/国外模型/hermes/scripts/jince_rijie_ | agent | True | bot-chat |
| 金策晨学哨·0900 (``) | {'kind': 'cron', 'expr': '0 9 * * *', 'display': 'every day at 9am'} | 你是金策学习进化机制的晨学哨（每日 09:00 任务，新会话无上下文）。执行六步：①跑 E:\AgentCommons\bin\common | agent | True | bot-chat |
| 金策每日体检汇报·0845投群 (``) | {'kind': 'cron', 'expr': '45 8 * * *', 'display': '45 8 * * *'} | jince_health_report.py | 脚本 | True | bot-chat |
| 金策每日学习进化升级·2130 (``) | {'kind': 'cron', 'expr': '30 21 * * *', 'display': '30 21 * * *'} | 每日学习进化(18:30前完成): strategy-rd 从 rd_queue 领1条研究课题(无新题则复验已知最强setup/攒样本), | agent | True | bot-chat |
| 金策看板同步哨兵·每10min (``) | {'kind': 'cron', 'expr': '20,50 * * * *', 'display': '20,50 * * * *'} | jince_dashboard_sync_guard.py | 脚本 | True | bot-chat |
| 金策群主持·白天带节奏 (``) | {'kind': 'cron', 'expr': '0 21 * * *', 'display': '0 21 * * *'} | jince_group_host.py | 脚本 | True | bot-chat |
| 金策自动巡检·节点+实读+三件套 (``) | {'kind': 'cron', 'expr': '*/30 * * * *', 'display': '*/30 * * * *'} | jince_auto_patrol.py | 脚本 | True | bot-chat |
| 金策节点看门狗·每15分钟 (``) | {'kind': 'cron', 'expr': '15,45 * * * *', 'display': '15,45 * * * *'} | jince_watchdog.py | 脚本 | True | bot-chat |
| 金策行情实时喂·每5min (``) | {'kind': 'cron', 'expr': '5,35 * * * *', 'display': '5,35 * * * *'} | jince_tick_push.py | 脚本 | True | bot-chat |
| 金策通宵巡检报0030 (``) | {'kind': 'once', 'run_at': '2026-11-13T00:30:00+08:00', 'display': 'once at 2026-11-13 00:30'} | 金策总调度执行 11-13 00:30 通宵巡检报。步骤: 1) terminal 跑 cd E:/GoldstrategyEngine & | agent | False | weixin:o9cq80y1wgC-Z_7mz1TyQYgux1zU@im.wechat |
| 金策通宵巡检报0300 (``) | {'kind': 'once', 'run_at': '2026-11-13T03:00:00+08:00', 'display': 'once at 2026-11-13 03:00'} | 金策总调度执行 11-13 03:00 通宵巡检报。步骤: 1) terminal 跑 cd E:/GoldstrategyEngine & | agent | False | weixin:o9cq80y1wgC-Z_7mz1TyQYgux1zU@im.wechat |
| 金策验尸官交付监测·每日1015 (``) | {'kind': 'cron', 'expr': '15 10 * * *', 'display': 'every day at 10:15'} | jince_postmortem_monitor.py | 脚本 | True | origin |
| 金策验尸官周报归纳·周五 (``) | {'kind': 'cron', 'expr': '40 21 * * 5', 'display': 'every friday at 21:40'} | 收集金策验尸官(@post-mortem)本周复盘周报: 读 E:/AgentCommons/bus/outbox/post-mortem/ | agent | True | origin |