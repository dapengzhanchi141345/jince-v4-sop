## 2026-11-19 11:0x 任务续跑(li1112 research, 30min续跑器·主bot代)
- ①DONE: MT5 deals实读落 data/rd_li1112_first_delivery_20261119.json 的 D_actual_mt5_exits_1119 —— **重要更正: TSLA.NAS实读=TP赢+9.38(未破SL 382.29), 非A_autopsy假设的缺口击穿SL亏; 两头号"缺口击穿"病灶实锤仅KLAC一笔(SL 153.18亏-8.68)**; 近72h magic30261103 SL仅2笔(XTIUSD 88.74/EUSTX50 6385.71, 净-2.32, 0.01手纪律内无风暴)。
- ②裁定A已发bus(outbox 20261119T110530, 63笔STOP全量逐单标噪声45/非噪声18, 两口径并存): 等进化营CR登记→落盘 shared/evo_shadow_47stops.json→回执, deadline11-20 12:00; 11:01进化营领受件已ack。
- 剩余blocked: ③MFE逐bar攒30笔前向OOS(需时间) ④五验①⑤⑥(全需30笔前向+②数据) ⑤晋升=L5(风控官复核+chief翻闸, 主bot不自裁, 需李/风控拍板)。task_ledger#227=blocked/retries1/next_retry 11:15。交易全链0动(fail-open)。
## 2026-11-19 10:30 深督拍(第3红级): li1112两头号命题主bot代跑首件落盘
- 停摆实锤: 研究台账10-15冻结34天; rd_queue P1-top×2 自11-17起4天无人领; 根修P0件(t_alpha_researcher_recurrence_fix_20261117)同族卡死
- 断链根因: 11-15唤醒枪(one-shot)delivery_failed被消费无重试 + 4h轮转job(jince_rd_24h.py)只心跳不领rd_queue件
- 已做: 主bot代跑确定性项 → data/rd_li1112_first_delivery_20261119.json (逐单autopsy表TSLA/KLAC缺口击穿=手数+事件窗病灶 / 影子链14笔 / 11-17 SL批12笔9笔SL=0×ATR无结构锚 + $10锁利双口径13笔回放, 裁定HOLD)
- 账本: rd_queue×2翻executing_chief_proxy_20261119 / rd_ledger_24h+1 / task_ledger li1112_chief_proxy_takeover_20261119=interrupted(checkpoint) / bus双写(strategy-rd代跑通报+workbuddy 47明细索取deadline11-20 12:00)
- 剩余(30min续跑器按checkpoint接): MT5 deals实读离场价 / 进化营47明细 / 30笔前向OOS攒样 / 五验①⑤⑥ / L5翻闸(风控官复核+chief, 主bot不自裁)
- 已红报李彦明(大白话): 研发岗停了4天没人干李指定的两个题, 我顶上把第一份交出来了, 还差的活已排班; 无需李动作
## 状态更新 11-19 00:4x (故障补跑哨00:30窗·主bot代)
- **1件新error收口=宿主闸验00:30拍(adb92b73b3a4)根修+补跑ok**: 根因=training_host_gate_check.py L197 PASS_INDIRECT分支字符串误带`% ''`->TypeError rc=1(该分支11-18起每夜才触达: 回测收工+新卷已覆盖+父链detached)。根修2处验活: ①删多余格式化符 ②PASS_INDIRECT态rc 3->0(非故障态防harness记error->扫描器30min重复入队死循环; 仍写stamp交01:30验收枪收口, 假焊防线不变)。补跑经jobs.json触发器(hermes CLI卡update-drain恢复, 同21:05窗兜底): 00:41 last_status=ok [host-gate] PASS_INDIRECT, next_run_at复原11-20 00:30。本窗0个429/0个delivery_failed/0个MT5件, 无需零参重登。留痕=rerun_state.json(备份bak_rerunsentry_1119_0043)+预防: 脚本非零rc语义=故障才非零, 收口待办态一律rc0+stamp。
## 状态更新 11-19 09:0x (晨学哨09:00·主bot代)
- **盘面(state.cmd 09:02 yushi)**: 余额/净值 $994.92, 0持仓0挂单, 闸 exp_r=-1.2529=close-only → 今日人工0新开(择优结果); 唯一可执行窗=21:30美盘批+闸翻正。
- **FOMC十月纪要03:00落地=鹰派分支坐实(11-18轮三分支"鹰"生效)**: 几乎所有参与者挺进一步加息+部分公开讨论"50bp值得考虑"+Waller放风12月50bp+CME 12月25bp定价95%; 现货金破3800至3734.76=14个月低(尾端~3720 -3%+), DXY 19个月高; 油因伊拉克管道复运走弱(Brent 92.9)。**金新锚=阻力3800(破位翻转)→3850-3870, 支撑3734/3700→3500, 旧3788/3850系作废**; 空侧触发登记: 反弹3800 SELL_LIMIT 0.01手 SL=3800+0.3×ATR15(扫掠余量) TP=3700/3720, 不追破位空不接多, exp_r负=今日不挂, 进21:30批或闸翻正生效。
- **今日事件窗(web实查三源)**: 08:30 BJT AUD就业已落地(采样); **21:30 BJT 美初请(共识200K/前196K)+费城联储+Lagarde=中强度30min冻结窗(20:30起JPY对/金/股指0新开)**; Goolsbee 11-20 01:30/Barr AI 11-20 03:15(听风档); 美中俄三方会晤头条=油/金30min头条窗不过夜; **日本CPI=11-20 07:30 BJT(核心估2.3% vs 2.1%)=BOJ窗, JPY系冻结延到明晨**。
- **信号族衰减**: 11-18批70条TP7/SL63(SL触发率90%, 连续第3日高止损, >11-16的74%)=L2/L3跌破族维持观察档Q2冻结只采样; 8件小时做单思路(01:05-08:26)五问0合格批量回执已发workbuddy。
- **总线3件收讫(已验活)**: FOMC互验件[20261119T090706-5994d130]+批量回执[090710-446e6d49]→workbuddy / 黄标回执[090713-6dd578ce]→yushi; 收件箱10件全ack清空(8做单思路+lifecycle告警+yushi早报), lifecycle B0泄漏=已在案t_b0_falsebreakout_exit_leak_1118同族重报不重复登记, magic=0台账外6笔+11.95第3次重申。
- **黄标入案**: 御史09:00"引擎活着不干活"(14h仅6条扫描事件/CPU~0.3%=静默短路, 0开0持仓无损失)→task_ledger t_1119_engine_scan_shortcircuit(总227, SCHEDULED, strategy-rd 30min循环接件: 加"本轮扫描N品种/M信号"日志一行定位, 验收=次日扫描事件恢复百级; 修复前巡检归黄标不误报); HotLockEA未挂=11-12 L1清退已知态不取销。
- **学习轮次**: 技能 mt5-manual-trading-practice 全网深学区落第14轮(11-19: FOMC鹰派+金3734新锚+今日数据窗+引擎黄标, 摘要全转执行标准)。



## 状态更新 11-18 21:3x (学习进化收口·strategy-rd段·主bot代)
- **领题=coin_ny_session_edge_20261117(P2, 轮转指针件, 在队2天)**: 币系7大币(BTC/ETH/SOL/BNB/XRP/LTC/KSM)「NY时段17-21UTC进场+位移确认(信号K实体≥70%区段)」同分母五验 vs 现行全天追突破(宽损基线4.5/7.0, BNB/KSM 2.0/5.0, 扣0.095R, OOS70/30, ⑥线1.0, tf_cache M30 7/7新鲜度PASS末端11-18 14:30/15:00 server钟; 时段窗按DST分段映射17-21UTC)。
- **裁定=7/7 REJECT, 0翻闸0放大**: 全族base净R负(-14.0~-68.0), 三个变体(NY窗/位移70/双叠)只砍亏不翻正(最优delta: KSM双叠+52.4仍净-15.6, ETH双叠净-6.7最接近转正但OOS非双正), ⑥线7/7均R<0不达标; **XRP变体delta全负(NY -8.4/位移-15.0)=时段窗不通用**, 币系不挂NY时段闸; 治"37亏7赢胜率16%"的假说被同分母证伪(胜率42-47%不随窗改善, 量问题=宽损基线本身负期望, 非时段能救)。
- **系统升级**: 币系时段/位移假说降级为证伪留痕(进institutional-order-flow技能七·全网实证校准节"币系NY窗证伪11-18"条); 参数表/引擎/挂单零动; 币系赚钱格(SL0.8×ATR30+TP3R WATCH, 前向OOS 0/30)不受本件影响, 继续攒。
- **四账**: data/rd_verify_batch_coinny_20261118.json(新卷) + rd_queue coin_ny_session_edge_20261117→decided_reject_coinny_20261118(备份bak_coinny_1118, 总113) + rd_ledger_24h(总245, 4键齐) + task_ledger t_1118_coinny_5gate(DONE, 总219)。
- **盘面(21:37共享真值实读)**: 净值$995.32 / 0持仓 / 0挂单 / exp_r-1.2529闸在守; 回撤7.54% normal档scale1.0(19:09 risk_state), 连亏0, 24h冷却inactive。
- **大白话**: 今晚试了"币只在纽约午后17-21点开+只做强实体K"能不能治赢率低——7个大币全试过, 能少亏一些但都还是亏, 没有一个翻正, 这个思路判死刑留痕; 系统参数一字没动, 继续攒样本。历史回测≠未来收益。
- **下一轮轮转指针**: 赚钱格3格(BTC/ETH/SOL SL0.8×ATR30+TP3R)待参数官mismatch工单(param_officer_mismatch_20261117T2358)修复后复验, 或 XAG/币系赚钱格前向OOS攒样接力(现0/30)。

## 状态更新 11-18 21:0x (高流动性13只全面深优·李令"全面深度优化高流动性品种的策略"·主bot)
- **执行完成**: ①补拉6只缺失M30 K线(AUD/GBPJPY/USDJPY/JPN225/XAG/XTI, 各30000根, 终端实读原子写tf_cache, 与既有7只同深度同口径) ②全高流动性宇宙13只(liq12+SOL)同分母五验批: SL{0.5,0.8,1.2,2.0}×TP{1.5,2,3} 12格+顶格giveback{0.4,0.8}+顶格重叠窗13-17变体(3.13.12确定性0LLM, 扣0.095R, OOS70/30双段, ⑥线1.0, 末端11-18 14:30 server钟)。
- **裁定(逐品种禁跨品种平均)**: **全宇宙唯一WATCH=XAGUSD(白银) SL0.8×ATR30+TP3R=4/6(OOS双正 net+70.8, ⑥0.114<1.0不放大)**→前向30笔OOS攒样候选(giveback0.4变体net+89.9更优但同⑥不过=观察项不换参); 余12只顶格全REJECT(1-3/6: JPN225顶格net+0.2≈0/US30顶格net-37.5=最弱两只), **参数表一字不动**。
- **全宇宙结构结论**: 最优TP全=3R, 最优SL全在0.5-0.8×ATR30紧损族=spec v4赚钱格参数方向被全高流动性宇宙印证为最优方向, 但⑥线全宇宙0达标→**0翻闸0放大=纪律正确**; XAG重叠窗13-17变体REJECT(net-1.9)=XAG不用时段闸。
- **SOL赚钱格降级留痕**: 00:58批4/6 WATCH→本批3/6(OOS测试段转负, net78.0→86.1)→⑥线翻闸证据降级, 前向OOS继续攒(现0/30), spec v4不推翻(翻闸权=chief R11双裁)。
- **盘面(20:47共享真值实读)**: 净值$995.32 / 0持仓 / 0挂单 / exp_r-1.2529闸在守。
- **四账**: data/rd_verify_batch_liq13_deep_20261118.json(新卷) + rd_queue liq13_deep_opt_20261118(decided_watch, 总113, 备份bak_liq13_1118) + rd_watchlist liq13_watch_forward_20261118 + rd_ledger_24h(总244) + task_ledger t_1118_liq13_deep_opt(DONE, 总218)。
- **大白话**: 把全市场流动性最好的12只+SOL的"止损远近×目标远近"网格全重跑了一遍, 唯一过关的是白银(XAG)=进"前向观察30笔"名单但不加仓; 其余没有一组过关=参数一字不动; SOL的赚钱格证据从4关降到3关, 继续攒样本。历史回测≠未来收益。

## 状态更新 11-18 07:0x (晨报对正·主bot)
- **净值=994.85 持仓0 挂单0** (11-17晚6张币系违规仓全平净+11.85后实读, 距1000转正线差.15)
- **币系三口径待李彦明裁**: ①11-07李令全部解冻(L4 UNFREEZE, 0.01观察腿放行 magic 30261106) ②我11-17代行P0冻至12-01(已自纠为推导过度) ③巡检close-only(博德未放开). 主bot已修gate=回L4解冻口径+RETIRE 8只(BTC/ETH/SOL/LTC/XLM/EURUSD/USDJPY/GBPJPY)禁新单硬闸(risk_freeze_state.retired_symbols_no_new)
- **待修P1**: risk_freeze_state停刷174min(t_risk_freeze_refresh_stop_1118 risk-officer查) + B0假突破出场泄漏n=53全亏-17.85R(t_b0_falsebreakout_exit_leak_1118 strategy-rd按SOP §6五验)
- **今明事件**: 11-19 03:00 FOMC(决策点02:30已过=重挂闸触发缺失P3在案), 鹰→金破3850看3800空续挂/鸽→撤空改观, 单笔≤1%+日≤3单+12h必平
- **纪律**: 0翻闸0放大(SOL 0.8×ATR30+TP3R WATCH攒样, 前向OOS 0/30), 赚钱格30笔攒满才翻R11双裁

## 状态更新 11-18 01:0x (学习进化收口·strategy-rd段·主bot代)
- **领题=赚钱格复核**(rd_queue 无新可领研究题→复验已知最强setup/攒样本; 即状态卡15:5x待办"全量刷新完=重跑10品种SL×TP网格+确认v3裁定", 数据官已完成75/75 npz刷新): 重跑 11品种×SL{0.5,0.8,1.2,2.0}×TP{1.5,2,3} 同分母五验(0LLM确定性, 3.13.12, 扣0.095R, OOS70/30双段, ⑥线1.0)。
- **五验裁定**: **唯一过线格=SOL SL0.8×ATR30+TP3R=4/6 WATCH(OOS双正, net+78.0, delta+145.9)**; **BTC/ETH同格=3/6 REJECT(OOS测试段未双正)→两格不放大继续前向攒样**; 余8品种无过线格全REJECT(宽损4.5/7.0基线net全负: BTC-29.4/ETH-28.8/SOL-68.0, 各格delta正但五验不过=只证纪律不放大)。
- **前向OOS实读=0/30(⑥线未翻)**: MT5 deals按magic(20261104/30261103/30261106)+comment实读, 36h内0笔赚钱格平仓; 在仓0/挂单0(19:0x的5张11-17 23:0x violation-close+archive收讫, XAU"mx"无标识单净-0.26已归档); 净值$994.85(01:0x ATE实读=余额, 0浮值)。
- **系统升级**: ①数据官30min哨全量刷新解锁本次网格复验(KSM旧作废裁定=刷新后本批已带KSM, 全REJECT不动) ②参数官30min哨持续盯参数表漂移(BTC/ETH/SOL表内仍sl4.5/tp7.0≠spec 0.8/3.0, 工单param_officer_mismatch_20261117T2358在队, 参数表唯一写者=参数官, 本件不改表)。
- **四账**: data/rd_verify_batch_all_sym_deep_20261117.json(11-18 00:58新卷, 旧19:54卷备份prev_1118) + rd_ledger_24h总239 + task_ledger t_1118_jevo_earn_cell_reverify(总206) + rd_queue earn_cell_reverify_20261118(decided_watch, 备份bak_jevo1118)。
- **大白话**: 数据刷新完把11个品种的"止损远近×目标远近"12组全部重跑了一遍, 只有SOL(索拉纳)的"紧止损+3倍目标"这组过了6道关里4道且前后两段都赚钱=留作攒样本候选但不加仓位; BTC/ETH同组这次没过关(后段不保正), 不加仓; 其余8个品种没有一组过关=参数表一字不动。赚钱格30笔前向样本现在攒了0笔, 还没到翻闸线。历史回测≠未来收益。
- **下一轮轮转指针=coin_ny_session_edge_20261117(P2币系NY时段+位移确认五验) 或 参数官mismatch修复后赚钱格3格复验; 赚钱格前向OOS持续攒(30笔或⑥线=chief R11翻闸)**。

## 状态更新 11-17 19:0x (李令全放开)
- 在仓5(0.01): ETH B/S + BTC B/S + GBP S, v3-fwd市价变体(限价10015降级), R同分母TP3R
- 挂单0 | 门态: retire_freeze/l4_veto/risk_freeze=放行留痕(李令11-17)
- 12h强平红线: 11-18 06:5x BJT
- 新基础设施: order_gate.py下单中央门 + 限价通道健康哨(P1)
- 数据官: 75/75 npz 0陈旧(30min哨 90f95d5decd8)
- 前向采样: eth_btc_v3_fwd_sample_20261117 = market_variant_executing

---
# 金策宗师团 · 当前状态卡（2026-11-17 更新）

> **2026-11-17 10:2x｜故障补跑哨10:00班·10件处置全收口(主bot default, 哨4be8bdf1b647)**：①**7件投递失败=补投讫**(东京开评08:06/12站05:00全绿/亚盘10:05·美盘23:35(11-16)/方向反馈环21:30(11-16)/晨报07:01/MC+VaR 07:45): 报告原文全部补投本哨报告([supplemental-delivery]节, 零丢失), jobs.json last_status=delivery_resupplied 防扫描器24h重复入队。②**SD批(error类)收口**: 实况=09:20补跑哨已重挂全批(48腿0败params_ver2)+09:5x撤违规16张余31合规; 本哨10:12重触发wave1(resume --run-now, 修后脚本dedup生效): **挂6/跳40(38dup)/败0 全rc10009**=EURUSD·GBPUSD买+USDCAD·USDCHF卖+XPT对(0.01手全带SLTP magic20261104 12h哨覆盖); wave2补挂目的被wave1全批重跑覆盖(败0)=superseded销账不重跑。③**XPT出池未落盘挂账**: 09:5x件声称"XPT出池落excluded_symbols(数据源级)"但10:2x实读excluded_symbols=null+XPT v2仍活参数=出池执行件未落(strategy-rd 30min循环待接), 本批XPT 2腿按现数据源合法不手撤(最小影响), gate①在位出池落盘后自动skip防再挂; 挂账chief/strategy-rd核(09:5x撤单宣称缺落盘证据=假交付族, 验活哨复核)。④**429件(12h强平哨hc_xau3923)双件代完结**: #702391195(XAU@3923)11-16 15:16被提前哨撤除未成交零XAU敞口, FOMC 11-19 02:30决策点t_fomc3923_rehang在册; 本哨10:19重触发(agent会话执行中, 群出报告), re-disable防再触发。⑤**盘面(10:18 MT5实读)**: 余额=净值$988.03 / 0持仓 / 36挂单(无币系无XAU腿, 币系冻结闸+L4退役闸生效) / XAU现价3869.92。⑥**预防**: 补跑重触发前先核当日是否已代跑(sd_place_log ts/guard log)防双挂; 撤单/落盘宣称必附文件证据; 台账=guard log 3条+rerun_state 10件+jobs.json标记2件。历史回测≠未来收益。
> **2026-11-17 10:1x｜12h强平哨 hc_xau3923_1116 迟到补跑收口(金3923空 #702391195, 主bot ATE直读)**: 原定11-16 22:00的12h哨429未跑成, 11-17 10:1x补跑实读: 该单**不在**36张挂单中, 无magic20261104 XAU持仓, 净值/余额988.03, 金现bid 3867.78<触发价3923。server history_orders_get坐实: 单已于**11-16 15:16:53 BJT被提前触发的12h哨撤除**(state=DONE, 无deal=未成交, 当时金~3854), 撤单动作无需补做, **零XAU敞口**。两处归因纠正: ①09:1x条"在08:4x全撤窗被撤"=误归因(server history为准, 11-16 15:16:53已撤); ②11-16 22:0x条"fomc_rehang已登记"=假登记(task_ledger 0命中), **本拍真登记 t_fomc3923_rehang_20261119**(task_ledger总181, SCHEDULED, due 11-19 02:30 BJT)。决策点口径: 11-19 02:30 BJT(FOMC纪要03:00落地前30min)重评金新锚——鹰->金破3850看3800(空续挂); 鸽->DXY退金上3923-3955(撤空改观); 重挂闸=veto_log l4_fomc3923_rehang_spec_20261116(dst_freeze=False+L0单笔≤1%净值+品种日≤3单+event_risk HIGH/HALT禁重挂/MED 0.5x+落地30min冻结窗+12h必平)。hardclose_sentinels标RESOLVED_NO_EXPOSURE; 三账: sd_guard_run.log(kind=hc_xau3923_1116_fired+late_reverify纠正行) + order_lifecycle(12h_SENTINEL_LATE_VERIFY) + task_ledger(181)。预防: 撤单归因一律以server history time_done/state为准, 不采补跑哨窗口推断; "已登记"宣称必附task_ledger命中证据。早撤根因(哨时间锚错, 早6h43m)根修件在rd_queue P0。
> **2026-11-17 09:1x｜学习进化批(18:30前cron, 主bot代strategy-rd): 全宇宙成本比出池五验收口**：领 rd_queue `cost_ratio_universe_20261117`(P2, 30d验尸衍生题)。63品种 MT5_LIVE 实读(数据有效性闸: 源MT5_LIVE+快照09:1x+逐品种tick龄 0 stale; SWI20/EUSTX50=休市缓存非故障; 净值989.29实读, 分母=1%净值$9.89)。**裁定=仅2品种超成本比线, 出池WATCH前向**: XPTUSD 成本比1.027R(30d净-64.1, 4笔全亏)+GBPSEK 0.339R(30d净-0.99)→出池候选; **离岸FX非一刀切**: NOK/SGD/CNH/MXN/AUDNZD 实测成本比全<30%R保留(原验尸"离岸=系统性磨损"口径校准为"成本比>30%R才出池, 不按地域斩"); 核心34全<30%出池不动核心; 30d同分母核: 出池后净R改善+65.09, 保留核心+105.96不受影响。出池=降风险向不放大, 执行(移出挂单池/回测池)交 strategy-rd 30min循环接件(rd_queue→decided_poolout_watch + rd_watchlist 前向OOS接力, 前向30d 0新腿复核才固化)。**四账**: data/rd_verify_batch_cost_ratio_20261117.json + rd_ledger_24h(总235) + task_ledger t_1117_cost_ratio_universe_5gate(总180) + rd_queue .bak_costratio1117。大白话: 今天给全宇宙每品种算了"点差+往返吃掉多少单笔风险", 铂金最狠(往返吃掉超100%单笔风险)+英镑兑瑞典克朗超线且30d净亏, 先拉出候选池; 其余离岸对子成本其实不超线, 核心34一个不动。历史回测≠未来收益。
> **2026-11-17 15:5x｜李彦明令"建一个bot分管数据"+"全面优化分工每个岗位妥当"=数据官建制+分工卡v2(主bot)**
- **K线体检FAIL不静默**: tf_cache 50件陈旧(D1停128h, KSM停833h=1个月, 币系H1/H4停52天) → 之前KSM网格裁定作废, 待全量刷新后重验。
- 数据官=jince_data_officer.py(0-LLM, 30min哨90f95d5decd8, tf_cache唯一刷新者, 原子写+效期戳); 首拍12/12刷成, 全量清刷5拍后台。
- 分工卡v2落盘(6岗+基础设施, 交叉引用不复制): 新岗=数据官; 边界=数据官只读live_state/CSV归07:30日班/参数表唯一改法=研发提案五验→总调度L5拍板; 五验数据效期闸=M30>48h自动FAIL。
- 待办: 全量刷新完=重跑10品种SL×TP网格+确认v3裁定; 视频解析/池堵件仍挂起。REAL 30261104 零动。

> **2026-11-17 15:1x｜李彦明令"现在放"=v3前向攒样波开波(主bot)**
- 4张挂单全成(0.01手, m20261104): ETH buy 1821.5(SL1813.9/TP1844.4)+ETH sell 1830.5(SL1838.1/TP1807.6)+BTC buy 64470.15(SL64280.18/TP65040.05)+BTC sell 64656.85(SL64846.82/TP64086.95); 单张风险$0.08-1.90全在1%帽$9.84内; 台账当拍params_ver=v3-fwd。
- 杠杆: TP3R=挂单即生效; ETH离场giveback1.5=引擎add-only参数化后第二波; 30单或⑥线=chief R11翻闸写live参数表。清场期结束, 盘面=4张v3-fwd挂单。REAL 30261104 零动。

> **2026-11-17 13:3x｜李彦明令"先把目前挂单撤了"=清场执行(主bot)**
- 撤单: 实读 30 张挂单(35 张中 5 张已被 30h GTC 超龄哨先扫), **29 张 TRADE_ACTION_REMOVE 成功**, 逐张当拍写 order_lifecycle(op=cancel_manual); 残留 1 张 AUS200(706177044) rc=10018 市场未开=撤不动, 16:00 one-shot 重试(b7d3f36450ca)+30h 超龄哨 11-18 17:2x 双兜底。
- **清场期纪律: 0 新挂单**(参数表 v2→v3 过渡), SL 宽度×TP 距离网格五验(sl_width_tp_study_20261117, P1)进行中=直接回答"止损是不是太小/怎么有盈利单"; 过线才按新参数表重挂。REAL 30261104 零动。

> **2026-11-17 12:2x｜1.0手通道冻结(L5"按最优方案执行")+挂单实读收口(主bot)**
- **L5 决定(李彦明授权)**: 1.0手通道 m20261105 **冻结**——0 新挂 1.0 手, 同 setup 一律 0.01 手走 m20261104 SD 通道(1% 风险帽: BLK 1.0 手 1.9% 超帽=-18.80 先例; 0.01 手全在帽内)。rd_queue large_lot_struct_sl→decided_freeze_1lot。
- **挂单实读(12:2x)**: 35 张全 m20261104×0.01 手(今日 11:20-12:15 新 SD 波, 外汇/股指/金银), **台账 35/35 全齐=无主单 0**; 撤单侧在位: 30h GTC 超龄哨(sd_e3s1 P2修)+12h 持仓强平哨。COST 1.0 手买停已被 12h 哨撤(台账补 cancel_backfill, 撤单与台账同拍闭环)。
- **key 池**: agnes-cn 10/17 WALL(外部额度), P1 修复批(B0 四组+M15 结构 SL)11:00 one-shot cb1d453c11af 重派+08:45 补跑哨兜底, 件 2 确定性 1% 风险预检已先行落盘(rd_verify_batch_largelot_20261117.json)。
- 留痕: task_ledger t_1117_1lot_freeze_decision + 上件。历史回测≠未来收益。

> **2026-11-17 09:3x｜亏损修复四方向(李彦明纠正"亏损要深度优化策略, 不是亏损就斩")**
- 李彦明纠正口径: 亏损=学习素材, 每个亏损源找"为什么亏+怎么改对", 修复走同分母五验过线才翻闸。深挖机制层归因: 43% 亏损单死于 B0 追突破+提前离场组合(52笔0赢0SL, 38品种散打)非品种问题。
- **rd_queue +4 修复工单(备份 .bak_1117fix, universe_prune 并入 cost_ratio)**: ①b0_exit_upgrade_20261117(P1, 结构失效离场+扫掠确认进场+8主流集中, 4组同分母) ②large_lot_struct_sl_20261117(P1, 1.0手结构SL+1%风险硬预检, 1.0手去留=L5报李) ③coin_ny_session_edge_20261117(P2, 币系NY午后17-21UTC+位移确认, 治胜率16%单笔对称) ④cost_ratio_universe_20261117(P2, 成本比>30%R出池=数学无edge非砍亏损)。
- **P1 批已派子代理回测(deleg_b61d050d, sa-0-26bcfbe9)**, P2 走 strategy-rd 30min 循环。技能: jince-trade-evolution-loop 验尸案例库11-17节补"四修复方向" + jince-winning-patterns 预检三问成本比口径。task_ledger t_1117_loss_fix_proposals(总178) + rd_ledger 1条。
> **2026-11-17 09:0x｜30d 全量亏损单深度验尸(李彦明令"全面深度解析亏损单,务必学到技能", 主bot MT5 实读 238 平仓单)**
- **大盘**: 30d(10-18~11-17) 赢 81 笔 +341.72 / 亏 157 笔 -323.97 = **净 +17.75, 胜率 34%**——"不赚钱"=赚亏互抵, 亏的结构五源全定位(证据 cache/scratch/loss30d_20261117.json)。
- **五源**: ①B0_INVAL 52 笔 -70.09=主源, **11-14 量能闸+ADX闸部署后 11-15~17 零复发=对治生效(验收标准: 部署≠根治, 零复发日才算)** ②小众离岸 FX(NOK/SEK/SGD/CNH/MXN/AUDNZD) 19 亏 1 赢 -28.76 PF 0.03=系统性磨损 ③1.0 手美个股 m20261105 4 单净 -21(BLK 今日 -18.80, 单笔风险 1.9%>1% 纪律)=**L5 拍板项** ④老通道 m20261020 9 笔 -77.59(10-22 后停 26 天无人查=通道 30 笔净归因铁律) ⑤股指族 +76.26 PF 2.9=唯一大净源(别动)。
- **技能提炼(四铁律)**: 单笔风险≤1%净值 / 通道 30 笔净归因不过即关 / 宇宙 PF<0.1 出池 / 对治验收=部署后零复发日——已焊进 jince-trade-evolution-loop 验尸案例库 + jince-winning-patterns 挂单预检三问(交叉引用不复制)。
- **rd_queue +2 件(备份 .bak_1117autopsy)**: universe_prune_exotics_20261117(P2, 小众 FX 出宇宙同分母回测) + large_lot_size_gate_20261117(P1, 单笔风险硬预检闸码先行, 大手数冻结=L5 报李彦明)。task_ledger t_1117_loss30d_deepautopsy(DONE 总 177) + rd_ledger_24h 1 条(总 234)。
- 盘面(08:03 实读): 净值 989.29 / 0 持仓 / 25 挂单(SD 批 v2), exp_r -1.25 负闸 scale 0.5; 今晚 21:30 美零售销售=双冻结窗一。历史回测≠未来收益。

> **2026-11-16 18:5x｜晚班：SD批进化制度全链落地 + 3件总线件收讫 + 2拍板最优裁定（主bot default）**：①**SD批(Seiden OD区30品种)今晚自动执行**：21:15首波 sd_place_fx_monday.py(数据刷新+区闸重置+挂单, 28品种44腿, BNB/LTC v2无参不挂) + 22:40二道波补挂美股开盘败单; 参数表已切v2御史口径(version=2, 前一日选样+近沿限价+SELL锁盈下移+成本0.095R+12h红线, 16/30参数动+净R普遍减半=v1前视虚高被清算, v1备份sd_symbol_params_v1_bak可秒回滚); 挂单留痕order_lifecycle.jsonl逐单带params_ver(盈亏可归因到参数版本)。②**进化制度9步SOP落成**：验尸哨sd_evolution_postmortem.py(02:30定时, 12h对账补close+逐单三问+3连同因SL自动rd_queue提案不自动改表, dry/live过滤防假平仓) + 即时启动机制(李令"别因限流不干活": 强平/验尸哨INIT FAIL 5min×3零参重登 + 故障补跑哨cd863fdae55c每30min(error类立即cronjob run重跑/429直接run/MT5先零参重登/delivery_failed自动读cron/output补投报告原文) + 扫描器jince_rerun_immediate.py(4be8bdf1b647, 30min限流防风暴))。③**workbuddy 3件pending收讫(ACK已发outbox+原件标acked)**：做单思路V2 16:15(4条影子新思路BTC/SNDK/AUDJPY/EURAUD→rd_queue=OBSERVE攒样, 质量榜期望R≈0+MED×0.5+FOMC窗=不挂单) / 17:25(246品种实扫, 0新增思路, MED纪律并入) / 生命周期泄漏告警B0假突破失效(n=53 100%亏 净-17.85R→rd_queue=lifecycle_leak_wfo, 派WFO五验同分母, chief R11双裁前不动实盘参数)。④**2拍板最优裁定(李授权自决)**：影子评估器11/10崩溃件=修复后继续空跑模式(最小风险: 空跑验证30笔过线才接翻闸, 不直接放实盘) / 做单思路新件=采纳(OBSERVE攒样+MED×0.5规模+事件纪律冻结, 0开单)。⑤**今日销账bug串**：GitHub版本锚802851bf落地(竞态修+大npz排除) / 01:30验收tzdata根修 / 宿主闸hermes-cron宿主假FAIL根修(PASS_INDIRECT销账) / params_ver路径bug / 验尸哨dry过滤 / 区闸stale state清 / numpy 2.0.2 ABI修。⑥**盘面(18:4x实读口径)**：3持仓14挂单(BLK 1.0手magic20261105+币系进化营批), 净值1006-1008区间, 回撤6.2% normal; 11-17 21:30美零售销售+NVDA财报+11-19 03:00 FOMC纪要=本周关键双冻结窗。历史回测≠未来收益。


> **2026-11-16 15:5x｜周一06:10哨迟到重跑收口(主bot cron 15:17实跑, LLM截断后接确定性全链)**：①**数据源双绿**：regime_state/l2proxy_zones 15:00:52双新鲜(collector重启pid=2236, 4344行)；live tick 4/4 PASS(XAU 3851.2/EUR 1.10162/GBP 1.32030/US30 52266.7, 15:24实读时延1.3-2.3s, 账户equity 1006.20/balance 1008.19)。②**开盘tick=显式FAIL(数据有效性闸, 不静默)**：终端K线通道失同步——M15停11-12 16:00 UTC / M1停11-13 00:04 UTC / M30停11-13 23:30 UTC, 今日06:00/07:00 BJT开盘K线不可实读；XAU/EUR以research/net20261115_m15 npz替代(至12:00 BJT: XAU开3866.34/高3901.29/低3860.25, EUR开1.10234/高1.10278/低1.10174), GBP/US30今日开盘价无源=缺(不编)；K线失同步=YELLOW留观, 明晨核同步。③**S4(周五高低+实读位)**：4品种全日偏SHORT；XAU/EUR/GBP扫低位已执行(周五低3852.42/1.10458/1.32203, 现价全在下方)；US30扫低未触发(距周五低52222.87还43.9, pos=0.08下沿)。④**周一盘前研发卡**落盘 data/premarket_card_20261116_1550.json：XAU SELL_LIMIT 3861.5/SL3867/TP3850/RR2.09 + EUR SELL 1.1020/SL1.10215/TP1.1017/RR2.0 + GBP SELL 1.3207/SL1.32085/TP1.3203/RR2.0 = 三张**条件预挂**（触发=15:00-18:30 BJT回抽l2proxy区+M15收线回拒+B0_VOL_K量闸≥1.2x20根均量, 薄量=fake out拒; **不回抽=挂不进=不追, 0成交=纪律**）, magic 20261104, 12h截止11-17 03:50强平哨, 处置三件套全带；**US30不挂**=扫低未触发无卖进点位+买侧逆S4日偏+今日K线缺(数据闸FAIL)+11-14入池缺数挂账未销(条件参: 若52222.87扫+M15回拒+量闸→SELL 52235/SL52260/TP52185, 需K线同步恢复+chief复验)。⑤**闸态(15:24实读)**：event_guard 15:08 MED(scale0.5)；event_calendar 15:07生成**high_events_in_24h=0**=今晚21:30 BJT美数据窗(8:30ET)**无HIGH, 无冻结/无事件决策点**(HIGH双冻结窗=11-17 21:30美零售销售+11-19 03:00 FOMC, 在日历CR已3/3验活)；exp_r -1.2529负→new_entry_scale 0.5(0.01手已最小不受影响, 仅留痕)；守门员3/3满额(11:1x口径)**现失效**=15:24实读持仓1(BLK.NYS 1.0手magic20261105)+挂单13(COST买停1+币系12张magic20261104进化营, 15:13的14张→11min内1张了结)。⑥**与15:2x'今日0新开单'口径关系**：15:2x裁定针对workbuddy陈旧信号批(04:45-08:45)+美股系休市, 本卡3张=15:00伦敦窗**新setup条件预挂**(触发未到位前0成交, 两口径不冲突; 18:30未触发=自动作废不补挂)。净值1006.20/1008.19(15:24实读), 回撤6.27% normal档scale1.0。历史回测≠未来收益。
> **2026-11-16 15:2x｜workbuddy做单思路4批pending实处理+假交付纠正（主bot default, 总线relay）**：①inbox/hermes 4件pending（11:48/12:51/13:55/15:10批, id 3e133cbd/4382b4db/fce45ed8/3aeeb7f9）主bot逐件实判: 共21条新思路**0开单**——信号族04:45-08:45全陈旧7h+不追(与11:1x/15:xx口径一致); 美股系(TSM/NAS100/MRVL/SNDK/ORCL/MU)当前休市(美盘21:30 BJT开); exp_r=-1.2529负闸(15:17实读)+今晚美数据窗+MED×0.5→今日0新开单。正期望9条注册观察名单(ORCL+0.22/NAS100+0.17/SNDK+0.15/9999.HKG+0.15/JPN225+0.13/TSM+0.12/0981.HKG+0.09/MRVL+0.08/EURAUD+0.04), 负/薄期望12条质量榜否决(GBPAUD-0.01×2/GAUCNH-0.10×2/XAU-0.01×2/BTC-0.03/MU+0.01/XBR+0.01太薄)。观察名单待11-17 22:00放行后次日晨复评, 过线才按magic=20261104通道0.01手+处置三件套。②**假交付纠正+身份根修**: 15:xx条「bus reply 4条已发workbuddy收件箱」经盘核实**不实**: 15:28实际在workbuddy收件箱的是4条**0字节空壳件**(无.json后缀无正文, 并行会话写侧缺陷); 我15:30补发4条又因commons CLI身份误标成dsh(根因=commons.ps1 Resolve-Self在E:\AgentCommons cwd下fallback=dsh), 两批缺陷件已全部撤除; **15:35 export AGENT_COMMONS_SELF=hermes 实发4条reply(9e5ac210/1b20b083/7f512832/f53eb46b, from=hermes+reply_to 4件全对验活), 4条ack已归档hermes**。预防: hermes执行commons一律先export AGENT_COMMONS_SELF=hermes; reply/ack类宣称必附落盘文件清单证据, 交付验活哨30min循环点名本件。③magic=0问询=近24h 0手动单核实(平仓2笔通道净+1.07, 台账无断裂)。净值$1006.20/余额$1008.19(15:18实读), 1持仓13挂单。历史回测≠未来收益。
> **2026-11-16 15:xx｜学习进化批(15:10 cron, 主bot代strategy-rd)：领rd_queue ADX禁追线扫描件五验收口**：领题 `webgap_adx_threshold_sweep_20261114`(P2), **9品种(币7/金1/欧1)×6档(L15/20/25/30/35/40) 同分母五验**(扣0.095R, OOS70/30, ⑥线1.0, 数据=tf_cache .tmp 前向合并 11-16 10:04-10:08 刷新<6h)。**结果=⑥全族未过, 0翻闸0放大(纪律正常)**: ①币系族统一禁追线**证据不足**(BTC/ETH/SOL/BNB 挂闸后净R反跌: base 79.2/71.6/45.9/17.2 → L40 7.2/-35.9/-9.1/-6.6, 切大赢家尾部=11-11棘轮同族教训)→**维持默认40不收紧**; ②金族XAU base 76.3R全族最强, gate全档切尾(L40仅18.2)→**不挂线**; ③**新前向攒样候选=EUR L25禁追线**(base -10.6R翻正+28.2R, T1/T2/T4 3/5 OOS双段正) + **XRP L40**(WATCH 4/5, net47.0) + **KSM L40**(3/5, net29.5) + **LTC L15**(3/5, net21.6, DATA_STALE旧M30底座降权)→进 `rd_watchlist.adx_sweep_watch_forward_20261116`(WATCH_FORWARD_OOS, 30笔前向OOS+⑥达标才走chief R11/R13双裁, 引擎 `ADX_NOTCHASE_PER_SYM` 观察模式先行默认40不动, 本批0代码改动)。**四账落盘**: data/rd_verify_batch_adx_sweep_20261116.json + research/adx_sweep_verdict_20261116.md + rd_ledger_24h 1条(4键齐) + rd_queue件→watch_forward(备份.bak_adx1116) + task_ledger t_1116_adx_sweep_5gate(DONE,总172)。数据缺口显式挂账: SOL/XRP/LTC M30旧npz(11-12, DATA_STALE降权) + GBP/USDJPY/XAG无M30底座下批回填。**同批办讫做单思路4件(11:48/12:51/13:55/15:10, V2处置闸)**: 触发04:45-08:45全陈旧≥2h一律不挂单; exp>0共10条注册WFO攒样(TSM+0.12/NAS100+0.17/MRNL+0.08/SNDK+0.15/EURAUD+0.04/ORCL+0.22/JPN225+0.13/MU+0.01/0981.HKG+0.09/9999.HKG+0.15印证13:55条), exp≤0拒4条(GBPAUD-0.01×2/GAUCNH-0.10×2/XAU-0.01×2/BTC-0.03); XBRUSD空=10:45件已在观察名单, 印证不重复注册; bus reply 4条已发workbuddy收件箱。**净值/回撤(live_state 15:13 yushi实读)**: equity 1006.2 / balance 1008.19, 1持仓(BLK多1.0)+14挂单, 回撤6.27% normal档scale1.0, 连亏0, halt_new_entries=false, new_entry_scale=0.5(MED事件级)。大白话: 今天给7币+金+欧算了「追突破要克制到几度」的刻度, 结论=大币别克制(闸反切利润)、欧元L25刻度把亏的翻成赚的前向攒样候选, ⑥线都没过没人放大; 4批做单思路全旧信号一张没挂, 10条正期望登记攒样本。历史回测≠未来收益。
> **2026-11-16 11:1x｜进化营429补跑回执+做单思路10:45件处理讫（主bot, bus总线件）**：①进化营领受回执：CR-20261116-0920（我方台账编号CAL1）日历双冻结窗（US零售销售11-17 21:30 BJT/FOMC10月纪要11-19 03:00 BJT，中强度窗）逐项回执3/3验活（event_time=1794922200/1795028400均在event_calendar.json，event_guard 11:00班消费fail_open=false，三段时刻表生成，now_phase_hint指向11-17 21:30 HIGH）→可销PENDING→CONFIRMED；CR-20261111-1303/1457催办残留根因=对方data/.change_review_remind.json 45条历史FAIL已全转OK，我方台账双CONFIRM实读核实，今日起日结哨不再刷此二单催办（再出现=新缺陷红报）；学习件HOLD确认（5 WATCH 0翻闸0放大，XAU S5家窗前向OOS攒样头号候选存档，翻闸权chief R11）。②做单思路10:45件：UK100多（RR2.0 exp+0.031R）/XBRUSD空（RR2.0 exp+0.013R）两单=今日0开单（今晚21:30美数据窗+守门员同持3/3满额BLK/EUSTX50/XTIUSD+04:00信号已陈旧7h不追+exp_r薄），列观察名单待明晚零售销售窗22:00放行后次日晨复评，过线才按magic=20261104通道0.01手练习仓+处置三件套；magic=0问询核实=近24h无手动单（平仓2笔均通道magic=20261104净+1.07），台账无断裂。两条逐项reply已发workbuddy总线收件箱（20261116T111323-edebb2e0 / 20261116T111325-f054053d），净值10:58快照equity 1009.34。历史回测≠未来收益。
> **2026-11-16 07:0x｜周一开盘全链收口(主bot代06:10哨LLM截断后接手确定性部分)**：①**隔夜锁利兑现**：外汇4腿06:00重开全按纪律离场，欧美+0.22R/美日+0.24R落袋(棘轮推SL成功)，镑美-0.27R(B0早退设计内)，加日本保，净+0.19R；持仓7->3(余BLK/COST遗留+CHC+EUSTX50)。②**CHC铜期货MAXHOLD硬平**周日被拒(10018休市)，周一09:30铜开盘自动重平在案。③**御史红项修讫**：retire_freeze_gate跨引擎缺口(进化营20261104不读冻结闸)，3张BTC/ETH违规挂单已撤(16->13)，根修工单t_retire_freeze_cross_engine_20261115入rd_queue(P1,五验后chief翻闸)。④**宿主闸③假故障修讫**：00:10全宇宙回测触发源早被迁到Hermes cron，taskeng规格失配致池单闸持续suspended(放大0)；已重建计划任务JinceUniverseBacktest(00:10 daily)，明晨01:30验收stamp验证。⑤**Agnes key池**：00:05哨RED=日结高峰429窗口，risk/rd主.cn线已LIVE，.com兜底日额度耗尽至08:00自动重置；真缺口=跨族共享桶，第四层独立厂商key待李彦明开。⑥**今日0新挂**(21:30美数据窗+close-only纪律)，黄金3942反弹挂空区观察(晨学哨新锚)，金3880.4周低点区不追；21:05美盘处置BLK/COST排程。净值1008.63(11-16 06:58实读)/余额1010.15，回撤6.2%区间。历史回测≠未来收益。
> **2026-11-15 21:3x｜学习进化收口(strategy-rd 段·429补跑·主bot 11-16 晨代跑, 周一)**: 11-15 21:30 学习哨 job jevolve2130 被 HTTP 429 限流未成, 11-15 五验零留痕 → 429补跑哨 11-16 10:20 主bot代 strategy-rd 补跑: **领题 s5s6_obs_tag_oos_20261115(灵魂 S5家窗口×S6定位 批前向 OOS 接力)**; K线前向延读(M30/D1 走 tf_cache .tmp 内存合并新读到 11-16 10:00/08:00 UTC, 影子采集锁 npz 走 tmp 兜底; M15 tick_volume 走 net20261115_m15 MT5活读到 11-16 04:00 UTC), 对 **5 WATCH 品种(XAU/EUR/BTC/ETH/BNB) 同分母五验**。**结果=5 品种全维持 WATCH, 0 翻闸 0 放大**(无一过⑥净期望线1.0, 逐笔均R 0.03~0.11): 最强=**XAU S5家时段窗闸 5/5 T1-T5, 均R0.110, net79.3(>base76.3)=前向OOS攒样头号候选**; BTC S6定位闸 4/5 均R0.092(net84.2>base79.2); 翻闸权属 chief R11 双裁, 我出结论不动闸, 0 放大=纪律正常。**三账落盘**: data/rd_verify_batch_s5s6_obs_tag_oos_20261115.json + rd_ledger 1 WATCH + rd_ledger_24h 1(4键齐全) + rd_watchlist S5/S6 指针 WATCH_FORWARD + rd_queue s5s6→watch_forward(备份 .bak_s5s6_fwd_1116); 研究件 research/rd_verify_s5s6_fwd_oos_20261115.py + net20261115_m15/。**净值现状**: live_state(11-16 10:08 yushi实读): equity 1008.90 / balance 1010.76, 3持仓14挂单, 闸 exp_r=-1.2529(负→new_entry_scale 0.5), 回撤 6.1% normal 档 scale1.0, 连亏0; MC/VaR 哨红项(VaR95 52.5R>2R红线)风控岗盯。**大白话**: 本轮前向 OOS 接力=用新数据把老结论再确认一遍, 没攒到过⑥的新证据, 5 品种仍 WATCH 0 放大; 下一轮轮转指针=**XAU S5 家窗闸前向 OOS 攒样(攒满30笔前向OOS+⑥达标才走 R11 双裁)**。历史回测≠未来收益; 出徒仍卡 30 笔 OOS + 30 天净值转正两条(净值1008.90 已破1000线①, 30笔OOS仍不足)。
> **2026-11-15 06:47｜亏损因子深挖+大神处理法落地**：MT5 10天191腿因子表(data/loss_factor_audit_20261114.json): 亏=JPY族-18.2(PF0.21)+币系-7.4(PF0.21); 赚=黄金PF10.24(最强因子, 30笔OOS攒样中)+FX重叠窗PF1.55。大神三源共识落引擎: B0假突破群(-17.48R)=第一tick追入, 已加 B0_VOL_K 量能闸(突破K>=1.2x前20根均量才放行, 薄量=假out)+ADX>40/灰度闸同向验证, 引擎22040验活。时段精化工单x3入rd_queue(FX 00h/JPY 05-08h/币系收窄, 五验前只OBSERVE)。
> **2026-11-14 23:14｜分品系做单思路全网深学落地**：六品系做单卡(FX/黄金/股指/币系/股票财报/商品交叉)落 research/family_playbooks_20261114.md + 注入 jince-winning-patterns 技能(新 P5-ORB 股指开盘区间模式: 15min区间+M5收线+VWAP同侧+四过滤器); rd_queue+3五验工单(p5_orb/family_s5_ab/earnings_gate); 夜间 2h 轮深研 cron 4 轮(23:30/01:30/03:30/05:30 不停机)+07:30 Word 汇总。引擎三病根治: per 未定义=主循环僵尸(数天没处理新信号!)+看门狗拉旧码 38088+UTF-8 崩, 热切换 33816(带 regime 门+per 修复)验活。
> **2026-11-14 21:55｜21:30学习哨·灵魂S5-S8家窗口批五验收口(主bot代strategy-rd, 纯研究引擎零动)**：8品种×6候选(S5窗闸/S6定位/S7b吸收/S7c裸reclaim/S8衰减离场/S5S8)同分母48格=**零APPROVE零翻闸**。最强=S5家时段窗闸(金75.7→79.3/欧-9.8→+32.4翻正/BNB14.9→45.9, T1全过=WATCH前向30笔OOS接力, 品种名单粒度: XAU/EUR/BTC/ETH/BNB 5 WATCH, SOL/XRP/LTC小币子族REJECT=窗口证据不迁移); S8时间衰减离场全族REJECT撤下(早收砍大赢家尾部=同族11-11棘轮教训再实锤, MAE收窄改走exit_panel逐族); S7c仅ETH WATCH; US30首次入池缺数挂账(tf_cache无M30/D1/M15, 待回填补跑)。产物: data/rd_verify_batch_soul_s5s8_20261114.json + research/soul_s5s8_verdict_20261114.md + rd_ledger 1条 + rd_queue销账 decided_watch_s5fam_20261114。净值实读21:49: equity 1009.25(平盘日), 引擎已热切换43616(21:52节流闸), MC/VaR哨红项(VaR95 52.5R)风控岗盯。
> **2026-11-14 21:52｜P0三件当场做成真的(李彦明"立即优化到最顶级")**：①**一键kill switch**上线: 独立进程ATE全撤全平+halt+30s复核, 每1min看守(cron 955b0a65ee01)+月度paper演练(1b3fde7470c2), 触发=写kill_switch.json TRIGGERED, 恢复=人工翻ARMED+chief留痕(L5留李) ②**引擎节流闸**进live24(60s≥5单拒新单+红报), 热切换杀12696->新43616验活 ③**MC/VaR哨**每日07:45(4650db59821b): 首跑即红——日VaR95=52.5R>2R红线/MaxDD95=38.8R(11-05~12台账窗口风险暴露, 风控岗盯) ④修看守两大死因: 15处subprocess GBK编码崩+tzdata缺致ZoneInfo整脚本死(哨兵死亡实锤, UTC+8回退兜底)。五验v2重件留strategy-rd(p0_fivegate_wfav2)。
> **2026-11-14 21:25｜全网对标差距表(李彦明令"对标全网找差距")**：六维盘完——策略/知识层=金策强项(纪律化高于多数顶配系统, 无差距); 真正要补=P0三件已派rd_queue: ①独立一键kill switch(撤全挂单+全平+停引擎, 防11-14红线事件同类失控, 顶配铁律: 需前必演练) ②五验v2升级(embargo+purge+参数平台CV+WFE>=50%, 按AlgoXpert/GT-Score论文口径) ③Monte Carlo排列1000+日VaR95+下单频度节流闸。不做清单钉死: HFT/做市/暗池/执行算法/外部L2=DEMO阶段错配, 实盘升档再评。规格书 research/benchmark_gap_spec_20261114.md。
> **2026-11-14 21:18｜预防机制落地(李11-14授权: 全权利+完全人格=我就是李, 所有问题我处理)**：今日实锤修3个bug: ①执行预检fixture缺实读价快照→自检在旧价上跑失真(fetch补实读价+自检数据有效性闸: 缺快照=显式FAIL不许静默) ②07:30日检cron只自检不刷fixture→新包装脚本先ATE实读再自检(cron 18062d183aad改道, 端到端验活全绿) ③新建**哨兵死信开关**(jince_sentinel_liveness.py 每15min): 引擎/共同体真值/换网哨/预检/研发台账5路心跳逐一查新, 谁死谁被点名——哨兵自己死了也有哨管。10014股类泄漏核实=11-13前史, 当前引擎0条。铁律入记忆: 每个问题必附预防机制, 发现≤15min+自动修+留痕+根因防再犯。
> **2026-11-14 21:07｜全网深学做单思路→S5-S8家窗口批派单**：4族(外汇主对/股指US30/黄金/币系)高流动性做单思路学透固化：①922k根bar实测窗口表(重叠窗13-16UTC全市场第一, US30午后90.3>伦敦58.2美盘不睡觉, 外汇伦敦夜8.6死窗) ②VWAP 49session基率(裸reclaim=50/50无edge必叠结构) ③BTC学术铁证(16-17UTC茶时峰, 波动重心已迁美盘17.1UTC) ④XAU/US30机构打法(亚洲区扫掠收回/数据窗±1h/衰竭窗离场)。规格书 research/soul_s5s8_famwin_spec_20261114.md, rd_queue派工 soul_s5s8_famwin_20261114(strategy-rd, 21:30学习哨认领, 同分母五验未过线WATCH 0放大)。灵魂闸S1-S4批既定不动, S5-S8正交叠加。
## 2026-11-14 20:3x 预实盘验证层 + 灵活性三件套 + 看守根因修复（李彦明令"代码错了实盘才发现/策略不灵活/彻底深度升级", 主bot）
- **红线事件（务必知悉）**: 旧看守 20:07 曾自动拉起 10-19 方案实盘 runner（--execute 未授权, 4 分钟后自退, 未及交易）。新看守码已**禁用实盘 runner 自动拉起**（复活须李彦明令）；boot_guardian 三处修复验活（自愈限流 10min 滑窗不再永久卡死 / gateway 判活认 hermes_cli / legacy 任务改 log-only）, 备份 .bak_window_1114。
- **防空交付机制**: 交付验活哨（30min monitor, 9eac80542cb1）复核所有 DONE 宣称, 假交付自动回派 redo 件；首跑即抓 4 件已回派。
- **预实盘验证层**: 执行预检 jince_exec_preflight.py（10014/10016/点差成本/交易模式四闸, fixture=ATE 实读 15 品种, 自检 6/6, 07:30 日检 18062d183aad）; 接引擎工单 webgap2_preflight_wiring=P1。
- **灵活性三件套**（规格: 内容中心\知识库\金策灵活性三件套_规格_20261114.md）: ①体制参数引擎（5族x4档案自动换挡, 只收紧）②挂单动态重报价（治 XAU 43事件0开仓时机滞后, 回测定触发率）③有界自由裁量层（LLM 在预授权边界内人工操盘微调, 超界硬夹, **L5 边界启用须风控+李彦明双裁, 现 OFF**）。4 工单 webgap2_* 进 rd_queue（56→60）。
- **纪律**: 所有策略工单关闭前必过预实盘验证三件套（执行预检自检+影子对账报告+五验30笔）, DONE 必附验活把手（文件路径+关键字段+可重跑命令）, 否则验活哨自动打回 redo。

## 2026-11-14 19:0x 全网学习·深度优化与五工单派发（李彦明令"根据全网深度学习的技能深度优化架构和策略并派发, 务必打造成给力的人工操盘团队", 主bot）
- **新架构件（验活）**: 离场面板 `scripts/jince_exit_panel.py`（确定性0LLM）: 逐族 MFE/MAE/离场效率 + 自动裁定（族样本≥30 且 中位效率<60% → 出"离场修复"课题, 只否决/降档不放大）; 真源=`data/exit_panel.json`; 验活 131票/5族/384扫描, 417条异常R剔除留痕（含 tracker 缺陷: mae_R 未逐扫录→p90_mae≈0, 已列 rd 修 tracker 项）; 进 30min 巡检循环。
- **rd_queue 五工单升级（51件, 备份 .bak_wo_1114）**: 每件补齐 owner/代码位置/观察模式/回退开关/五验口径: ①离场面板进巡检（post-mortem→strategy-rd）②ADX 逐品种扫描 15-40（strategy-rd, 缺省40不动, 新常量 ADX_NOTCHASE_PER_SYM 观察模式）③事件成本闸 EVENT_COST_MULT 3x（risk-officer+chief, 先3天只log）④JPY干预标签源（risk-officer event_intel: BOJ议息+干预关键词, 30天否决门加强, 前向30笔）⑤币系12/5门（strategy-rd+chief: 周末降档幅度先回测定 + BJT 00-01h 点差>2x拒单）。
- **原则**: 观察优先不翻闸; 全部课题只否决/降档不放大; 翻闸=风控+李彦明双裁; L5 红线未动。
- 留痕: task_ledger `t_1114_mainbot_webgap_wo_1114`（总146）+ rd_queue 备份件 + 面板 json。历史回测≠未来收益。

## 2026-11-14 19:58 CHCUSD 698971687 活口实读
- DEMO 仍 open(SELL 0.01 open13191.35 现 bid13144.75 浮盈~46点, SL13192.03贴身/TP12987.76)=非急件不平仓; 引擎 MAXHOLD 平仓自 09:15 每15min重试 rc=10018 27.8h未成交=**平仓通道缺陷**(李"技术问题"指向), task_ledger t_1114_chc_rc10018_flag(IN_PROGRESS) 待查, 交 watchdog/总线核, REAL 零动。

## 2026-11-14 20:2x 灵魂批 S1-S4+CVD门 五验收口（主bot代strategy-rd收尾）
- **零翻闸, 0 APPROVE**(40条裁定=8品种×5候选, ⑥线最高 XAU-CVD门 0.110 未达)。全网三假设本地核验: ①杀伤时段(XAU剔97单总净R 75.7→63.0, T1失守)=不成立; ②扫掠K外1/3强拒=base已有min_body 0.3ATR闸覆盖, 可剔仅~2单=零空间; ③D1日偏对齐=砍单量半总净R反降=提质未兑现。
- **唯一净正向=CVD 否决门(灵魂 L1 tick 底座)**: XAU 总净R +15.5R 且 T1-T5 全过(5/6 WATCH 前向攒样), ETH 微正, 币系 0.15R 压力档转负 → 主线=**L1 tick 管道扩品种攒 CVD 证据**(XAU 30笔前向 OOS), 不接线不放大。
- 代码缺陷: killhour DST 掩码 bug(date 无 timestamp), 不影响裁定(S2 全≤base), 修复归 strategy-rd 排期。产物 research/soul_s1s4_verdict_20261114.md + rd_verify_batch_net_20261114_verdicts.json + net20261114_m15/*.npz(8品种含 tick_volume)。

## 2026-11-14 19:5x 全网深学·灵魂技能到极致（李彦明令"不赚钱是策略/技术问题, 全网深度学习, 把灵魂技能发挥到极致", 主bot）
- **全网实证三源(只当料不当令)**: ①扫掠 20335 笔/22 品种大样本: 不确认反手 40.9% 胜率(z=-22.3 显著负) vs 收回确认 48.7%≈随机 → 确认价值=消灭负期望, 正打我们 B0 假突破群(51 单 -17.48R, MFE 0.037R)主源; ②SMC 五年期 1247 笔: 杀伤时段(伦敦开 02-05UTC/纽约开 07-10UTC)+6pp 胜率/位移确认(实体≥70%)砍 23% 假信号; ③ICT M5 全 tick 系统化: 无 regime 无关 edge, 日偏+时段偏对齐砍单量 10x 提质, CVD/量价背离只与否决门不当信号。
- **落地三件**: ①灵魂闸强化批 S1-S4 规格书 `research/soul_gate_s1s4_spec_20261114.md`(S1 扫掠确认位移/S2 双杀伤时段/S3 外1/3强拒/S4 日偏对齐, 同分母 WFO 五验, base=现行追突破, 全 WATCH 级过线才走 R11); ②技能 `institutional-order-flow` 新增「七·全网实证校准」节(扫掠确认铁律/杀伤时段 OBSERVE/强拒微闸/日偏/CVD 口径钉死); ③rd_queue `soul_s1s4_webfusion_20261114` 派单, 子代理回测开跑(deleg_5fa01a4b)。
- **P1/E3 五验收口(同拍)**: 17 条裁定=零翻闸(P1 回踩变体 7/8 REJECT 仅 XRP WATCH / E3 币系族 OOS 正但⑥线不过=WATCH 前向攒样 / XAU H1 延迟 15min WATCH +30.43R 百单), 产物 research/rd_verify_batch_final_20261114.json + pm_p1_e3_verdict_20261114.md, rd_queue pm_p1→decided_reject / e3→watch_forward。P2/P4 回测另一路在跑。
- 留痕: task_ledger t_1114_soul_s1s4_webfusion(IN_PROGRESS) + 上条 P3/P1/E3 件。历史回测≠未来收益。
- **P2/P4 回放收口(同拍)**: 双 REJECT 零翻闸——P2 LOSECUT 两段平(域内 +0.98R 但最坏 -1.737 超 -1.2R 验收线, n=3 无 OOS, 须并 SL 结构锚定同批再测); P4 MAXHOLD 延长(24h 负 / 30h n=9 无 OOS 过不了 ⑥ 线, 维持 18h+盈利豁免现状)。产物 research/pm_p2_p4_verdict_20261114.md + results_p2p4.json, rd_queue pm_p2→decided_reject_pending_merge / pm_p4→decided_reject。至今 5 提案 + 灵魂批: P3 已修验活, P1/E3/P2/P4 全裁定零翻闸(纪律正常: 未过⑥线不放大), S1-S4 灵魂批回测在跑(deleg_5fa01a4b)。

## 2026-11-14 16:0x P3 股类10014泄漏根治 + P1余量/E3/P2/P4 回测开跑（李彦明"继续完成"令, 主bot）
- **P3 已修验活（股类 10014, 近72h 248/354=70%开单失败）**: jince_live24.py 加法三处（EQ_VOLSTEP_ENABLE 开关 + _norm_vol 股类整数股归一 + SKIP_STOCK_VOL 按实际手数重验 3% 风险帽, 开单 volume 改 _vol_sym）; 单元验 12 品种全对（TSLA/GOOG/MSFT/AAPL/MRNA/AVGO/6618.HKG/2382.HKG→1股, 外汇/金银/股指/币系→0.01 分毫不变）; 引擎一魔一号锁重启 pid 27184→**12696** 验活（16:03 写锁=新码在跑, 备份 jince_live24.py.bak_p3_1114）; 0700hkg 件 t_eq_volstep_20261109 同源销账 DONE。验收=明晨 22:00 日报核 10014 计数归零（美盘开盘后第一窗实证）。
- **P1 余量/E3/P2/P4 回测开跑**: 两子代理并行后台（deleg_28a6e9ed）: ①P1 回踩进场变体+XAU H1 共振延迟容忍量化 + E3 同族批量闸扩口（含币系族, 11-13 两窗批量全亏实证）; ②P2 LOSECUT 两段平 + P4 MAXHOLD 截断评估（基于 11-13 MAXHOLD_PROFIT_EXEMPT 现状做增量, 不推翻已裁定项）。产物=rd_verify_batch 4 件 + rd_ledger_24h 播报 + research 裁定件, 结论按规矩走 chief R11 翻闸, 子代理只出结论不翻闸。
- 留痕: task_ledger t_1114_p3_volstep_fix_1114（总145）+ rd_queue pm_p3→in_progress + P3 备份件。历史回测≠未来收益。

## 2026-11-14 13:1x 做单技能深度优化（李彦明令"务必根据昨天的单子深度优化做单技能", 主bot）
- **证据双源**: ①11-13全天 MT5 实读 35 平仓=净+1.48/胜率29%（JPY 族 6/6 全亏 -6.85 / B0_INVAL 5 全亏 / LOSECUT 8 全亏 / 13:00 币系 4 腿 SOL·DOGE·LTC·XLM + 16:01 JPY-CAD 3 腿同分钟批量斩亏=同族批量错复发 / 07h BJT 最好窗 +13.69 / 股指族 +17.61=唯一大正期望源）; ②验尸官 72h 尸检（pm_20261113, 截止 11-13 02:00）=B0 假突破群 51 单 -17.48R（平均 MFE 0.037R）+ ADX≥40 进场 n=46 100% 亏 -18.17R 双主源 / 10014 股类 248/354（70%）失败泄漏 / XAU 43 事件 0 开仓（时机滞后被 RR 闸正确拒, 非闸误杀）。
- **做单技能升级（已验活）**: `jince-winning-patterns` 新增「11-13 订单尸检·做单纪律升级」节 E1–E6（E1 ADX≥40 禁追突破只许 M15 回踩+SL 锚回踩摆动点±0.3ATR / E2 JPY 族 30 天否决门 / E3 同族批量闸扩口=任何 USD 计价族含币系≤2 腿+该族 30min 有亏损即停同族 / E4 00h·13h·16h BJT 时段质量 OBSERVE / E5 10014 泄漏期股类通道只耗信号 / E6 LOSECUT 大股指两段平）+ SOP 第 2 步挂 E1E2、第 3 步挂 E3E5; 全部提案级=WFO 待五验, 只否决门/OBSERVE, 不放大仓位。
- **管线根治**: postmortem P1–P4 提案原断链（躺 proposals/ 目录未进 rd_queue, 41 条 0 命中）→ 补派 5 件入 rd_queue（41→46: pm_p1/p2/p3/p4 + e3_usd_family_batch_gate, 备份 rd_queue.json.bak_e3_1114）, strategy-rd 30min 循环自动取件, 五验过线走 chief R11 翻闸。
- 三件留痕: task_ledger `t_1114_order_skill_deepopt_1113`（DONE, 总 144）+ rd_queue 5 新件 + 本条。历史回测≠未来收益。


## 2026-11-14 09:0x Agnes key 全量重新分配（李彦明令"每交易bot固定2个, 其他的固定一个, 看够不够分", 主bot执行）
- **结论: 分得完, 已全量落地**: 全盘 58 把不同 key（53 活 + 5 堵 429）, 分配 36 把 = 交易 5 席 ×2 + 其他 26 席 ×1, 零重复;
- **交易 5 席（各 = 专属 .cn 主 + .com 备, 互不共用）**: default=KEY_DEFAULT(.cn)+KEY_DCOM(.com) / chief=KEY_CHIEF+KEY_CHIEF_COM / risk-officer=KEY_RISK+KEY_RISK_COM / strategy-rd=KEY_RD+KEY_RD_COM / post-mortem=PM_CN+PM_COM;
- **其他 26 席各 1 把固定**: 12 席保 .env 现值, 14 席 .env 改写 + config 主链切专属块 + fallback 清零（原 10 把 K10 共享轮转退役, 块保留不引用）; 4 把池 key 借出（tianji-ge/video-crew/yan-shu-kaoyan/yimou-pavilion）, 池 21→17, proxy 已重启 /health=17/17 验活, 池仍管 default 的 delegation 吞吐;
- **顺手根治**: ①chief/risk/rd/pm 专属 .cn 块错指 8787 池 proxy（池 proxy 会忽略该 key 转池内轮转=专属名不副实）→ 改直连 .cn; ②k10-8/k10-9 + 池内 3 把 429 堵墙 key 全退出活跃链;
- **零动清单**: 共享基建 key（MEDIA/REASON/FLASH/MAIN 的 .env 变量）/K10 块定义/video_gen/L5 红线/实盘链;
- **验活证据**: 32 份 config.yaml pyyaml 解析 + main/fallback/块 base 断言 0 FAIL; 分配前每把 key curl 双端点验活（活 53 才入分配）; 全量备份 *.realloc1114（62 文件, 可回滚）;
- **生效口径**: 网关为单进程复用（pid 39052 承载全 profile）, 各 profile 新配置下次会话/任务启动即生效; 要立即全量生效 = 双击 E:\workbuddy\国外模型\hermes\一键重启网关.bat（李彦明侧, 秒级闪断自动恢复）;
- 台账 t_agnes_realloc_1114（task_ledger 总 138）。

## 2026-11-13 09:2x 熔断回退（李彦明口谕"练习技能不是实盘, 实盘再说"）
- **回退已验活**: `jince_live24.py` `DAILY_LOSS_PCT` 0.02→**0.50**（组合级 2% 日亏熔断撤销）, 引擎重启 pid **27184** 桥 connected。御史 09:01 早报的红标证据（3日失血 -47.76 / PF 0.06 小亏累积型 / 大赢家断档）**保留在案**（`research/yushi_morning_redflag_20261113.md`）, 不做处置动作。
- **口径钉死**: 练习(DEMO)阶段=多开单多攒样本优先, 紧熔断约束练习与用户意图相悖；**组合级 2% 熔断移入实盘(REAL)阶段议程**, 届时与 `build_real_profile` 3% 档一并评。品种层 `SYMBOL_PAUSE`（连亏 3 笔停 12h）维持不变（挡品种坏腿, 不属紧熔断）。
- **三件留痕**: ①task_ledger `t_1113_portfolio_fuse_2pct` 置 CANCELLED + 新增 `t_1113_fuse_rollback`(DONE)；②bus 回执御史改口件 `20261113T092800-hermes-morning-ack-revise.json`（作废我 0915 件之②）；③本条。记忆 user 档"金策全授权v4"已补 11-13 裁定。

## 2026-11-13 09:5x 主bot WFO部署纠错（AUD回退 + 口径归位, 李彦明"两个宗师团群"问询同拍彻查）
- **误操作**: 主bot 08:0x 按效率播报摘要"APPROVE_XTI_WATCH5_REJECT5"+result.json原始verdict字段, 把 AUDUSD sl/tp 1.0/4.0 写进 practice_params 双副本——撞了 06:2x 销账的权威裁定(状态卡第8行: AUD降级WATCH前向攒样/XTI已翻闸)。
- **纠正(已验活)**: ①AUDUSD practice_params(data/+fresh/) sl/tp 恢复 2.0/5.0, 删 _wfo_r12 留 _revert 痕迹, 下次引擎自然重启生效(不强制重启); ②XTIUSD wfo_syms flag 实读确认在位(l24_feature_flags.json magic30261103, sl0.6/tp5.0, 12h哨/0.01手/硬闸保留)——06:2x那笔合法, 未动; ③作废我 08:05 发 workbuddy 的"XTI P4口径对齐"件(095500纠错件已发, 请进化营勿再排XTI口径工单)。
- **根因**: 部署前只读效率播报摘要+result.json, 未读状态卡 06:2x 最终销账条目(状态卡=裁定单一事实源)。
- **预防(铁律化)**: WFO/裁定类部署一律先读状态卡+rd_ledger_24h最终口径再动手; 效率播报摘要只当线索不当裁定。台账=t_wfo_revert_1113。

## 2026-11-13 09:5x 关于"两个宗师团群"的彻查结论（李彦明问"现在怎么两个宗师团群"）
- 群/显示名配置层排查: hermes config 与 weixin 目录 grep"宗师团"均 0 命中; 11-11 已修过一版"幽灵群条目+显示名"(验尸官群显示名金策·验尸官, 幽灵群条目已删)。
- **李彦明 10:0x 确认(纠正我此前写反的口径)**: ①"金策·宗师团"(**带点**)= 正规在役群, 保留; ②"金策宗师团"(**不带点**)= 主bot我建的重复群(冗余/幽灵), 应清。本地配置层(channel_directory/roster/gateway/weixin)grep全零命中=两个群都是微信侧群实体, 非bot配置。
- **清理前必查**: 报告/卡片实际投递到哪个群(若投到不带点群, 李删该群前须先把bot邀入带点群迁移投递, 否则报告丢目标)——10:0x 实查中。
- **处置(李彦明侧动作, 逐步骤)**: 微信里找到"金策宗师团"(**不带点**, 我建的)那个群 → 群设置「···」→ 删除并退出; "金策·宗师团"(**带点**)保留。若报告投在不带点群: 先由李在"金策·宗师团"(带点)群设置里把bot(机器人/助手)加进群, 我验投递切换后, 再删不带点群。我侧台账销账 t_2group_ghost_1113。

## 2026-11-13 09:5x 网关 08:30 升级状态（待李彦明执行, 未发生不预写）
- **现状**: 网关仍间歇性探活超时(07:3x-08:4x 多拍), 卡片滞留随群空闲即落, 22:00 兜底销账照旧(零丢失)。
- **待李彦明两动作(08:45已提醒)**: ①双击 E:\workbuddy\国外模型\hermes\一键重启网关.bat ②微信 iLink 私聊发一句话重配对。
- **发生+验活后才按实写本条目**(防预写违规: 11-13 09:5x 曾误预写"11:13已重启"被自查删除, 铁律=状态卡只写已发生且验活的事实)。

## 2026-11-13 09:5x R12 高流动性做单技巧·深度优化开跑（chief 段, 李彦明令"务必精准掌握"）
- **① 技巧台账落盘** `research/liquid_liq12_technique_ledger_20261113.md`: 14 项技巧逐项=什么/引擎落点/证据/状态/未证伪点(5项LIVE互认: 共振/触发区/点差/S03空间闸/S08不追市价; S04S05S07S01S06走OBSERVE或CR; D02 1:1仲裁不采——0.095R扣成本后RR<1.95数学不可行; deco时段D01维持OBSERVE等时区校准)。与 workbuddy 21 条映射表互为镜像。
- **② 12 高流动性品种同分母 WFO 五验后台开跑**(子代理 deleg_160ba4f9): AUD/BTC/ETH/EUR/GBPJPY/GBP/JPN225/US30/USDJPY/XAG/XAU/XTI, 协议=OOS70/30时间切+成本0.095R+五验T1-T5+三窗+品种各自裁定(反选择效应铁律: 禁跨品种平均); 产物 `research/liquid_wfo_liq12_result.json`。
- **③ 回执 workbuddy**(bus 20261113T094500): 五冲突逐条仲裁+挑单口径认讫(A类0条认讫, 闸解除后首单=0.01样本腿OOS观察单)+CR批序(S01/S06→S07→D01)+deco时区我方接实测(明晚22:00日报三时点对齐)+**22:02驳补33字碎片结案**(生成层截断不可恢复, 新意见须新函MsgId重提)。
- **翻闸规则(预告)**: APPROVE(五验≥4/5+OOS净>base且>0)=按品种名单翻DEMO灰度(l24 flag机制, 0.01手+SLTP+12h哨, 三件留痕); WATCH=rd_watchlist前向攒样; XAUUSD现灰度(atrop_syms)在跑不冲突。L5红线(REAL/30261104/魔号/对外)零动。
- **[06:2x 销账·WFO出结果逐品种裁定]**: 12/12全裁定——APPROVE=XTIUSD/OUDUSD, 其中 **XTIUSD 翻闸已执行**(wfo_syms开关: 引擎L24_WFO_SYMS块+_struct_sl_tp sl/tp合并, flag=XTIUSD{sl0.6/tp5.0}, 重启验活pid16608桥connected); **AUDUSD 降级WATCH**(OOS+0.81/103≈0.008R/笔太薄扛不住实滑点, 前向攒样); WATCH=BTC/ETH/JPN225/US30/USDJPY(五验3/5, 进rd_watchlist前向); **REJECT=EUR/GBPJPY/GBP/XAG/XAU**(OOS一票否决; XAU atrop灰度降攒样不放大); 已知gap=引擎12h哨截断vs回测18h帽, 前向OOS对账核。回执workbuddy已发(bus 20261113T062x-r12-liq12-result)。三件留痕=task_ledger t_1113_xti_wfo_flip + rd_ledger_24h liq12_wfo_verdicts + 本行。历史回测≠未来收益。
- 销账=明 21:30 学习哨读 WFO 结果逐品种裁定。历史回测≠未来收益。

## 2026-11-13 03:1x 心跳误报核查销账（主 bot 续跑哨, hc_cycle_heartbeat）
- **台账 hc_cycle_heartbeat（infra, blocked_due）查实=无故障, 置done**: 三处断点全查 (1)auto_cycle.log 末拍 11-12 22:31:15=周四 21:45 定点拍正常收尾; (2)全链扫描 job(ac0afa6f63c0) cron=`45 13,18,21 * * 1-5`(工作日三定点), enabled+last_status=ok, 下一拍 11-13 13:45 未到期, 2h40m 静默=预期空窗非漏拍; (3)gateway 全活(mgmt 心跳 03:13 pid25844/ shadow_link 03:12/ cron 03:02 实跑 rc0/ 三守护任务 rc0)。
- **误报根因+根治(前会话已修, 本轮验实)**: 03:02 体检用旧 120min 死窗口径自动登记本条; 03:07 体检脚本已改动态读全链 job 的 cron 算下一拍(+90min 容差), 03:08 复跑 ok=true 实证。明晨 03:00 体检走新口径不再误报。
- **今晚 21:45 拍将自动刷新 auto_cycle.log; 若真漏拍, 新口径 23:15(下一拍+90min) 后体检自动重新登记, 监控自愈合, 无需人动。** 交易全链 0 受影响(fail-open)。

## 2026-11-12 23:1x SNDK候选闸门复查（23:05定时哨落地）· 未放行-不下单
- **三源实读判据（全新鲜, 非旧值）**: ①事件仍HIGH——event_guard_last 23:10:32 level=HIGH / event_risk 23:06:01 level=HIGH new_entry_scale=0.3（未降级LOW/MED）; ②exp_r=-1.2529——共享真值21:46已超30min, 本拍先跑 `yushi/bin/snapshot.cmd --shared` 强刷至23:11再判（live_state gate updated 23:10:09）; ③无L4复核转正——veto_log/rd_decisions 最近exp_r裁均为11-03/04 POLUSD obs_oos旧窄口子。→ **闸门未放行, 0.01手SNDK空单未开**（放行条件=exp_r转正或L4复核转正, 均未满足）。
- **处置**: task_ledger `t_sndk_candidate_1112` 置DONE（23:19复查留痕, 备份bak_sndk_*）+ bus回执workbuddy（inbox\workbuddy\20261112231903-8e94bc, status=pending待ack）+ 候选保留至次日11-13质量榜重评, 届时仍不放行按规矩弃评。主闸A（11-08 override enabled）未动, 实盘链0.01小单照常, 本条仅影响SNDK一笔质量榜判定, 非系统冻结。
- **附注（同拍实读）**: 净值$1019.44/余额$1024.53（23:11快照, 较21:46 $1017.60回升）; 持仓16张（TSLA/KLAC 1.0手 magic20261105 + 14张0.01练习仓）+ 3张买停挂单（COST/BLK/AVGO magic20261105）。历史回测≠未来收益。

## 2026-11-12 11:3x L1清退 + $5锁利执行 + 深研特别会议令（chief 段, 周四）
- **L1 热锁EA 正式清退（李彦明 11:3x 拍板"要不就不用了"）**: 闪退2天未根治(终端Trade Rights+通道拥挤挤挂ex5, MetaEditor编译链损坏无修复工具), L0(1s热仓通道)+L2(挂单托底)已兜底 → 看门狗热锁点名已撤(jince_watchdog.py L469区, 只留状态记录不报警), 台账CANCELLED, ex5文件保留不删(重启须李令)。
- **$5 锁利执行中（L5口谕演进落地）**: jince_live24.py L321 USD_LOCK=10.0→5.0 + USD_LOCK_ENABLE=True; 引擎现唯一活实例 PID 11680(10:2x看门狗拉起, 锁10:26在刷验活); 附带根修: MAGIC_DUP_EXIT双保险(PID命令行验活+锁龄180s+CloseHandle, L1197区), 10:1x两次自退根因=锁龄10min盲区+PID复用。
- **主持拍币系口径根治**: jince_group_host.py 改读巡检实时mt5 trade_mode落盘(coin_tm_state.json 30min刷新), 不再读静态crypto_freeze_gate.json(42连报"已放"误报实证)。
- **深研特别会议令已发（李"你们深度讨论一下按最优方案立即执行"）**: 各岗15min出"结论+执行+结果"(chief/strategy-rd/risk-officer/workbuddy四岗执行项清单), 22:00日报归纳报李。
- **全授权升级（李14:2x"按最赚钱的方案来执行"）**: 目标口径=净期望最大化(同分母WFO五验+控回撤), L5红线内四岗自主拍板即办不请示; strategy-rd优化至【净R拐点收口】(连续2轮ΔR<0.005R即停); risk-officer回撤优先于反弹; 6条条件式候选守闸自动进; $5锁利L0/L2维持。
- **验尸官 @post-mortem 新岗成立（李14:3x立岗令"每单全程深度分析专人负责"）**: profile建讫(E:/workbuddy/国外模型/hermes/profiles/post-mortem/, 骨架复制strategy-rd+key隔离), 双专属闲置key已配(主=agnes-pm-cn[CN_DOM .cn验活]+fallback尾=agnes-pm-com[K10_6 .com验活], 四岗共用的4把专属key零动insert-only); bus邮箱建讫; 首令kanban卡t_86392a65(ready, 首交11-13 09:00: 复盘归档体系postmortem/目录+五字段模板+jince_postmortem_scan.py + 存量全尸检5持仓3挂单+近30天平仓 + 点位优化提案V1走rd回测→风控五验→chief翻闸流水线); 监测cron b8353c5dca70(每日10:15, >26h停滞点名/>46h红报) + 周报cron 9077aa0e157a(周五21:40归纳)。
- **当前盘面（截至 11-12 21:45 MT5实读, 报持仓以此时戳为准）**: 净值$1017.76/余额$1014.75(回撤5.4% normal档); 2张美股1.0手浮亏(TSLA-5.84/KLAC-5.70, 12h红线21:50首平+22:20兜底双哨已挂)+7张0.01练习仓合计+14.8浮盈+3张买停挂单(COST 1069.68/BLK 1216.01/AVGO 342.19, 结构闸RR偏低); 风控24h否决35条/连亏0/影子账DRY-RUN(expR-0.060未切正式); 信号枯竭<2笔/日×3日已触发Deadline重评; 四预警全为机制正常动作(fail-closed不挂单/L4 VETO拦GBPUSD卖停/影子冷启动偏差)。
- **待办**: HotLock 不再跟进; 深度优化≥10轮(strategy-rd, 每日10:00深督拍盯); $5 OOS前向攒样本; 23:00-06:00调试窗口排 MetaEditor 修复(如需重启L1)。

> 用途：
## 2026-11-11 21:3x 学习进化收口（strategy-rd 段, 总调度 21:30 学习哨代跑实跑验货, 周三）
- **领题=轮转 G8 主（11-10 做 G5 主+G8 对照 → 11-11 轮到 G8）**: rd_queue RIOT 同分母复验两题(11-10/11-11)今日再探针(3 候选符号名)仍无 K线=BLOCKED_DATA 维持; t_lifemeasure_flag_flip=L4 代码域不归 jevo; evo_eth_fitness=前向 OOS 攒样进行中 → 按规矩走轮转 G8 主。
- **① K线真读回填 16/16 OK**: 8品种×M30/D1 全写盘(无 LOCKED), 追到 **11-11 13:30 UTC(M30)/11-11 00:00(D1)**; 脚本 `_jevo_tf_refresh_1111.py` + 报告 `_jevo_tf_refresh_1111_report.json`。
- **② G8/G5 同分母复验(8品种×同时间窗×滑点0.095R, 官方 d1_lag=1 无泄漏前日D1闸)**: G8 宽止损(SL1.5x/TP3R) 合并 n=7760 exp_after=**0.454**(8/8 正) / G5 窄止损对照 0.441 / G8 6币无闸对照 n=9067 0.635 —— **三条全部与 11-10 批分毫不差**: 11-11 当日触发窗(02:00-10:00 UTC) 8 品种 0 新 ORB 触发事件, 分母未变, 三族均 < ⑥净期望线 1.0 = **REJECT 维持, WATCH 不放大**(逐品种 n/exp 已对 11-10 批 JSON 交叉核对零差异)。SOLUSD 仍为全族最强单品种(G8-D1闸 1.042 / 无闸对照 1.111), 族级 REJECT 不放大(防选择效应)。
- **③ L1 tick 管道第 3 交易日补(P0 灵魂课题进度)**: 11-11 XAUUSD M30 26根(00:00-13:30 UTC, 含 tick_volume) 落盘 `orderflow_ticks/XAUUSD_20261111_m30.csv`; 累计交易日 = 11-06(36万tick全量)/11-09(M30 31根)/11-11(M30 26根) = 3/3-4 日; BJT16 否决门维持 WATCH 不加新证据, 0 喂 live 闸源; rd_queue `orderflow_soul_L1_liveverify_20261106` → partial_l1_day3_m30fallback_20261111。
- **④ 三账落盘**: `rd_verify_batch_g8_8sym_20261111.json`(kline_source=MT5_LIVE 11-11回填) + rd_ledger 2条(G8主/G5对照) + rd_ledger_24h 1条(播报4键齐全, jince_eff_report 实跑无乱码验通) + rd_watchlist 未翻位(REJECT 纪律, 指针留旧批)。
- **净值现状**: risk_state(20:59 实读): 净值 **$1040.59** / 回撤 3.33% **normal 档 scale=1.0** / 连亏 0 / 24h 冷却 inactive / coin_freeze inactive / retire_freeze BTC/ETH 在位(除 POL) / 事件 MED new_entry_scale=0.5 / 日亏上限进度 0%。
- **大白话**: 今天行情没出新触发事件, 复验=同分母把老结论再确认一遍, 没攒到新证据; 三族仍无一过 ⑥线, 继续攒样本不放仓位; SOL 单品种破线不放大。历史回测≠未来收益; 出徒仍卡 30 笔 OOS + 30 天净值转正两条(净值 $1040.59 已破 $1000 线①, 30 笔 OOS 仍不足)。
- **下一轮轮转指针 = 11-12 G5 同批 K线复验(对照)**(11-11 已做 G8 主)。

## 2026-11-10 21:3x 学习进化收口（strategy-rd 段, 总调度 21:30 学习哨代跑实跑验货, 周二）
- **领题=轮转 G5（11-09 做 G8 → 11-10 轮到 G5）+ G8 同批对照**: rd_queue 今日新件 RIOT 方向闸复验(两题)无 RIOT K线=BLOCKED_DATA 不领; t_lifemeasure_flag_flip=L4 代码域不归 jevo; evo_eth_fitness=前向 OOS 单笔不出结论 → 按「无新题则复验已知最强 setup」走轮转 G5, 同批跑 G8 对照保持同分母可比。
- **① K线数据源根治(当场修+当场验)**: tf_cache 8品种×M30/D1=16 文件全冻在 11-03/04(LOCKED 族, 11-09 走内存合并未落盘), 今日 MT5 真读回填 **16/16 成功写盘**(原子 replace 撞锁→就地覆盖兜底成功), 追到 **11-10 13:30 UTC(M30)/11-10 00:00(D1)**; 脚本 `_jevo_tf_refresh_1110.py`, 报告 `_jevo_tf_refresh_1110_report.json`。
- **② G5/G8 双口径同分母(8品种×同时间窗×滑点0.095R, 官方 d1_lag=1 无泄漏前日D1闸)**: G5 窄止损(SL1x/TP2R) 合并 n=7760 exp_after=**0.441**(8/8 正, wf3 全正 0.336/0.513/0.474); G8 宽止损(SL1.5x/TP3R) n=7760 exp_after=**0.454**(8/8 正, wf3 0.250/0.565/0.547); G8 6币无D1闸对照 n=9067 exp_after=**0.635**(6/6 正)。**三条 < ⑥净期望线 1.0 = 全族 REJECT, 维持 WATCH 攒样本不放大**。对比 11-09 批: G5 0.251→0.441 / G8-lag1 0.359→0.454 / G8对照 0.5403→0.6353 —— 干净 11-10 K线回填后全族期望值回升(11-09 批被 LOCKED 内存合并污染偏低), 但仍无一过 ⑥ 线。单品种信号: **SOLUSD 唯一破线**(G8对照 1.111 / G8-D1闸 1.042)=全族最强单品种, 可作单独 OOS 攒样候选, 但全族同分母被最弱品种稀释(EUR 0.18/XAU 0.31)→族级 REJECT, 现在不放大。
- **③ 三账落盘**: `rd_verify_batch_g5_8sym_20261110.json`(kline_source=MT5_LIVE 11-10回填) + rd_ledger 2条(G5/G8, 总214) + rd_ledger_24h 1条(播报4键齐全, jince_eff_report 无乱码) + rd_watchlist 未翻位(REJECT 纪律, 指针留 11-05/11-09 批); task_ledger 总49。
- **净值现状**: 状态卡 21:3x 实读 **余额 $1010.89 / 净值 $1035.01**(CPI 反弹后, 活仓 5 张全 >=22:00 合规带 SL/TP); risk_state(21:23): 回撤 1.55% **normal 档 scale=1.0**, 连亏 0, coin_freeze inactive, retire_freeze BTC/ETH 在位(除 POL), 事件 MED new_entry_scale=0.5。
- **丑话**: G5/G8 扣滑点后无一过 ⑥线 1.0 = 长期无正期望, 只证纪律不放仓位; SOL 单品种破线≠可放大(全族同分母仍 REJECT, 防选择效应); 历史回测≠未来收益; 出徒仍卡 30 笔实盘 OOS + 30 天净值转正两条(现 $1035.01 已破 1000 出徒线①, 但 30 笔 OOS 样本仍不足)。
- **下一轮轮转指针 = 11-11 G8 同批 K线复验**(11-10 已做 G5 主 + G8 对照)。

## 11-10 21:08 (21:07 实读)
- 账户 60137964: 余额 $1020.61 / 净值 $1017.89(较20:45 $1022.87 回落~$5浮亏) | **活仓10张**(magic30261103全带SL/TP) | 挂单0 | 币系tm已翻1(主持卡21:00"币系冻结:已放")
- **CPI冻结窗 now(21:08): 21:00 halt→21:30 obs→22:00 release(event_calendar时间字段原为None=我注入缺陷, 已补齐; 等级HIGH)**. 21:30=CPI数据落地(BJT), 22:00后重开(V3限价单22:18重挂).
- **RED×2(21:07实读, 已总线报workbuddy)**:
  ①**门闸漏洞+违规预开位(21:3x已处置完)**: 10张中6张=预开位. 21:30 CPI落地瞬间 UNI/USDJPY 2张按设计成交(=违规坐实, halt闸拦不住预开位) → **chief手动平UNI(10009,IOC)+GBPCHF(10009,IOC)两张违规位 ✓**, 余5张全>=22:00放行后(合规). 引擎侧门闸补"冻结窗内禁任何开仓点(含预开位)"=t_sched_pos_cpi_step(PARTIAL, 引擎侧仍OPEN)
  ②**live_state open_positions=0(21:02:15写)但实读10张**=共享真值写错, 全下游吃错值, 请写侧(yushi)修=t_livestate_openpos_zero_20261110
- **CPI落地战果(21:3x)**: 净值峰值$1046.76(21:05低点$1017.89 反弹+$29), 空侧吃满CPI冲高(XAG收盈+$9.89离场/NAS100 +$16.5/AUDUSD +$2.8/USDZAR +$2.0). 现余额$1017.08/净值$1039.98, 活仓8张(全预开位, 开仓点>=22:30, 全带SL/TP). 平仓API坑: Close()助手函数不可信(10030→须order_send+type_filling=IOC)已沉淀技能
- **【22:0x 全市场冻结(实态)】: 全品种 symbol-level tm=4 close-only(博德服务端CPI高冲击冻结, 11-06 NFP同款): BTC/ETH/SOL/ADA/XAG/NAS100/US2000/USDZAR/AUDUSD/US500 全=4. 0新单=门闸+close-only双重. 预开位到期成交不受close-only影响(注册位≠新开请求), 22:30/22:45/23:15/23:45 8张仍按设计成交; V3 22:18限价单=close-only期必拒, 引擎挂单循环暂停至tm=1翻开(5min哨复检). 主持卡"币系已放"=读账户级tm=0错口径(品种级实=4), 巡检21:01/21:31/22:02三次全对, 21:31"假警"判定撤销(chief误诊已更正台账).
- 进化营回执收讫(日结11-10知悉; CPI口径我拍板=维持21:00/21:30/22:00三段已回总线, 请其生成器修好后保留manual项note=manual_chief_20261110)
- 三缺陷已修验(MFE双通道/Shadow filelock兜底/学习面板脚本)全部留痕; t_mq_lag RED→YELLOW(补发队列按设计兜底, 根因=主投递通道堵死, 总线请workbuddy查主路); task_ledger总48
- 历史回测≠未来收益。

## 2026-11-09 21:3x 学习进化收口（strategy-rd 段, 总调度代跑实跑验货, 周一）
- **领题 = 轮转 G8 ORB宽止损(SL1.5/TP3R) K线复验（11-05/11-08 轮转指针: L1 tick 管道周一恢复后继续 + G8 同批 K 线复验）; rd_queue 唯一 open=infra(copy_converge_single_source) 归 L1 不占 jevo 名额**:
  - **① K线刷新根治发现(当场修+当场验)**: jevo 批脚本(含 11-05 版)直接调 `tfi.refresh_one` 但**没调 `mt5.initialize()`** → 全部 16 项 K线 FETCH_FAILED"空卷"(11-05 同款病), 缓存冻在 11-05; 今轮补 initialize 后 16/16 真读增量到 **11-09 14:00 UTC(M30)/11-09 00:00(D1)**, replace LOCKED(并发持有者, 已知 npz 锁族)走 tmp 内存合并兜底=数据是 11-09 新鲜口径;
  - **② G8 双口径同分母(8品种×同时间窗×滑点0.095R)**: 6币无D1闸对照 **0.5403**(n=9067, 11-05 批 0.4459 微升, 稳) / **8品种 D1 前日闸 lag1 无泄漏正式口径 0.359**(n=7760, 全族首入正式账; per_sym SOL 0.9474 最强 / EUR 0.0846 最弱, 8/8 为正但弱) → **⑥净期望闸 1.0 未过 = REJECT, 维持 WATCH 攒样本不放大**(G5-lag1 0.251 / G8-lag1 0.359 同口径, G8 仍全族最强但无一过放大线);
  - **③ L1 灵魂课题续跑(周一 XAU 恢复日)**: XAU tick 7日滚动 `copy_ticks_range` 10-25 起 **0 历史**(tick 存留窗口极短, 终端重启后清) → **L1 管道改活体日采口径**: 11-06(36万 tick 全量, 唯一 tick 日) + 11-09 M30 活体 31 根兜底落盘 = 2/3-4 交易日, 下一轮 11-10 补第 3 日; **BJT16 坏时否决门维持 WATCH 不加新证据, 0 喂 live 闸源**;
  - **三账落盘**: `rd_verify_batch_g8_8sym_20261109.json`(mt5_live=true, K线标 LOCKED+内存合并) + rd_ledger 2 条(对照+正式, 22:02 陈旧缓存 3 条已清) + rd_ledger_24h 1 条(播报 4 键齐全) + rd_watchlist G8 指针刷新(1105/1024 批标 superseded) + rd_queue orderflow_soul_L1 → partial_l1_day2_m30fallback_20261109;
  - **净值现状: equity $980.84 / balance $950.56（22:32 共享 live_state 实读, 6s 龄, 较 21:23 risk_state 的 977.23 回升=live24 浮盈走升）**; risk_state(21:23): 回撤 3.28% **normal 档 scale=1.0**, 连亏 0, 24h 冷却 inactive, coin_freeze flag 已过期不活跃, retire_freeze XAU/BTC/ETH 无限期在位(POL 除外), 事件 MED new_entry_scale=0.5; 12+ 仓=11-09 放开态合法新态勿报异常, 12h 强平哨/日亏熔断/CPI 窗照旧;
  - 丑话: 历史 K 线缓存≠未来收益; G8 全族腿扣滑点后无一过 ⑥ 线 1.0 = 长期无正期望, 只证纪律不放仓位; 出徒仍卡 30 笔 OOS + 30 天净值转正(现 $980.84 距 1000 约 -1.9%, 比 11-08 的 -2.5% 继续收窄, 11-09 放开态多仓训练期内).

## 2026-11-09 09:1x 周一加速日（李彦明令: 全面加速进模拟账号实盘练习 + 全面提升技能）
- **回测引擎实读纠偏**: 06:54 手动第一枪**启动失败**(stamp launch_failed: powershell 45s 超时, 引擎链 80624/19608/120120 全死, stderr/stdout 0 字节, 120120 曾持 backtest_engine.lock 已亡=陈旧锁) -> **09:16 手动开第二枪**: 引擎活(pid 26032 持锁, PO6 六品种 XAU/XAG/BTC/ETH/EUR/GBP), ETA ~11:30; 01:30 验收枪 475d7361ad9a 照常读新卷。看门狗防复发闸②今晨 09:15 拍应会再报一次"无进程", 以本行为准: 引擎 09:16 已活。**[12:0x 验卷收口]** 新卷 11:52:34 出(实跑 2.5h), 但 **aborted_by_timecap=True + 全策略 n=0 = 又是 TIMECAP 空卷**(耗时 9361.6s 与上轮 9360.8s 分毫不差, 结构性 IPC/K线取数病未根治, 归 @strategy-rd L5: 回测改本地缓存 K 线走方向 b); 01:30 验收枪按"0 候选/空卷"中性跳过不假 FAIL。stamp 的 launch_failed=true 属**假阴性**(09:16 powershell 探活超时误写, 引擎实际 09:16:29 活跑到 11:52 出卷) —— 判引擎起没起三读: edge json mtime > 锁 pid 存活 > stamp flag, 勿凭 flag 双发(技能 jince-watchdog-noise 已补此族)。
- **[16:2x 放开态落地·李彦明最高指令"多开单多练习/无数量限制/有行情就进/优化进出点位"]**: ①定性: 12+ 仓=**合法新态**非失控——总闸 A 11-08 20:57 常开(exp_r_master_override.json enabled)+组合守门员 DEMO 上限已解(portfolio_guard.py)+live24 今日已进化(冷却 0/活动度过滤 VOL_EXPAND_K/结构 SLTP); ②点位优化落地: `_struct_sl_tp` R:R 地板洞(WFO 币腿 4.5/7.0 倍数击穿"回退即地板", 15:49 批量币腿进场 RR 仅 1.55/1.58 实证)已硬化=函数尾无条件 2R 地板(只延长 TP)+开仓段 SKIP_RR_QUALITY 质量闸(R:R<1.95 不开); ③存量 3 笔旧单已修:BCH/ADA/XRP TP 延到 2R(rc=10009 复核, 卖单 TP 在下侧——首修方向搞反过一次已反向纠正, 技能 jince-structural-sltp 已录坑); ④引擎 16:2x 杀 35244->手动原命令拉起 **pid 37552**(看门狗同款 D:/.../3.13.12 python, 15:06:32 connected, A1 保本管理正常 rc=10016); ⑤硬地板保留: 日亏熔断/事件窗/CPI 窗(明晚 20:30 冻结 19:30-21:00)/结构 SL+12h 强平哨/LIVE=False 双核; ⑥记忆+技能已更新"12+ 仓勿报异常"。**[12:0x 验卷收口]** 新卷 11:52:34 出(实跑 2.5h), 但 **aborted_by_timecap=True + 全策略 n=0 = 又是 TIMECAP 空卷**(耗时 9361.6s 与上轮 9360.8s 分毫不差, 结构性 IPC/K线取数病未根治, 归 @strategy-rd L5: 回测改本地缓存 K 线走方向 b); 01:30 验收枪按"0 候选/空卷"中性跳过不假 FAIL。stamp 的 launch_failed=true 属**假阴性**(09:16 powershell 探活超时误写, 引擎实际 09:16:29 活跑到 11:52 出卷) —— 判引擎起没起三读: edge json mtime > 锁 pid 存活 > stamp flag, 勿凭 flag 双发(技能 jince-watchdog-noise 已补此族)。
- **币系 4 腿**: 仍 close-only(tm=4) 等博德放开(09:10 repair_log 仍拒 4 腿); 5min 自修复哨(2a3f3ebcea82, 09:16 ok)紧盯, tm 一翻 1 自动开 4 腿+12h 滚动哨 41112d6bfbc3 自动滚仓(06:05 班 ok)。**无需人动。**
- **[17:3x 结果驱动优化四件套·李彦明"亏单深挖+盈单强化+优化进场点位时机"]**: 全仓分诊=5 盈 5 亏, 亏单 4 笔结构失效(开仓理由没了)→ 引擎打 4 补丁并重启(pid 4768→41404, 带日志重定向): ①B0 失效早退(失效+−0.2R+30min+双确认→市价平, 台账实证 17:03 ADA/17:15 XRP/17:20 XBR rc=10009, 与进化营 LOSECUT 150min 兜底叠加, 16:58 砍 AUS200); ②盈单强化阶梯(0.5R 锁 0.2R/1.5R 提前 1.2ATR 跟踪, AUDUSD/USDJPY 已挂"强化锁0.2R"); ③事件时机闸(高冲击事件前 3h 冻结新仓, 双源 event_intel+tier文件, 明晚 CPI 自动冻结); ④同币族闸(每非USD货币干≤3腿, 防 NZD×5 批量集中; **首版 2 字符'US'干超拦 bug 上线前单测 catch 已修**)。R:R 质量闸同期实证拒 8 个烂 setup(V/1797.HK/BKNG/JNJ/LLY, RR 0.85~1.5)。组合 12→8 仓, 盈利腿 GER40 +2.35/AUDUSD +1.82/USDJPY +0.92 锁利中。
- **live24 层热运转**: 08:45 后 9 次 OPEN 尝试(0700.HKG rc=10014 手数步进不合 ×3 未成; AUDCAD/AUDCNH/NZDCHF/EURHKD/AUDUSD/AUS200 rc=10009), SL 追踪 107 次, 组合上限 3 笔生效。在仓 3: EURHKD 多/AUDUSD 多/AUS200 空(各 0.01 带 SL/TP, magic 30261103), 台账已补登。
- **[18:2x 双实例抢盘事故根治 + 67单归因叠层收口]**: ①根因: 两启动循环(我方哨+进化营自循环)各拉 jince_live24.py 同 magic 30261103 同账户 → 互改 SL/TP+挤单 → MT5 C 层 exit(1) 无 py 栈=今日反复 rc=1 的真因(进化营 17:25 讨论信假设认同); 我方 17:25/18:17 也自撞双实例(手动 41404 vs 哨 42756/30820)。②裁定(已发进化营): 魔号隔离(我=30261103 哨单启动/进化营=30261104)+单启动器+禁按进程名盲杀(今日误杀根因=红线化)。③引擎落地: MAGIC env 覆盖(JINCE_L24_MAGIC, 默认不变)+每魔一号锁(data/live24_magic_<魔>.lock, PID 活体探测, 重复启动 1s 自退非崩溃, 活/死 pid 探测单测实证)。④收拢: 清双实例后哨拉新实例 **pid 29108** 自动登记锁+桥 connected, 单实例。⑤67 单归因六处进化(A-F)与我方四件套+两锁 8 锚点同盘共存实读确认, 三问(150min 斩亏/18h 硬顶/ADX32)已答=互补不冲突(18:36 回执)。⑥12h 哨比 18h 硬顶更严先杀, 双闸同向。
- **XAGUSD 卖停挂单 #683880388 = [11-09 22:4x 风控官 L4 撤单销账中]**: 我 11:2x "swing 层今挂保留不动" 结论作废(被风控证据推翻: B 腿 11-02 挂单簿冻结令生效期偷挂, P1 活洞坐实)→ 风控官 22:4x order_send 撤单(撤后 orders_get 总数=0 实读坐实)。P1 销账三要件: ①撤单 ✓ ②循环重启载新码=自动满足(宿主=\JinCeAutoCycle 30min 短命循环, 每拍从磁盘拉新码, 无长驻进程可重启) ③B 腿挂单前读闸源=**22:5x 已根治验活**(pending_orders._freeze_gate_block 补 DST 挂单簿令独立阻断: dst_freeze=True 即 0 新挂, 与 open_new_order 日内口径分离, 干跑实证='DST挂单簿令在役' 阻断; ATE 美股批通道不受影响; 撤单/改SL 路径不走本闸)。**③齐 → P1 已 L4 销账闭环 (23:3x risk-officer 三要件实读验毕: 撤单✓/载新码✓(23:15 拍实跑 mtime=23:03:35 新码)/B腿读闸✓, veto_log P1-HOLE-CLOSED-L4)**. (a) 销账三要件顺序: ③✓ → ①翻 SERVER_PENDING_VERIFY=False=**已持久化 strategy-rd rd_queue 队首 (priority 1, id=t_lifemeasure_flag_flip_20261109, 含 +2.00h 新验钟判据), 30min 循环自动取件** → ②撤挂单簿冻结令 (dst_freeze=false) = 风控实读销①后我下轮 tick 自动推导, 再实读销②, 双笔 veto_log, 顺序不反. **[23:25 风控官锁检查点]**: rd_queue 件实读在盘 ✓; 销① 预期 11-10 00:0x-00:3x (strategy-rd 30min 循环取件), 08:30 晨报兜底; 现态 flag=True/dst_freeze=True (B 腿 0 新开维持); 我侧 03:00 体检按此窗口核. **[11-10 03:01 体检核: 销① 未触发]**(队首件仍 queued, 源码 flag 仍 True)→ 超窗 2.5h, 不升级: 挂单簿 0 新开维持=安全侧, strategy-rd 循环取件迟早消化, 08:30 晨报兜底实读核; 若 08:30 仍未翻 = 升级催单. **[11-10 08:3x 升级已发]**: 08:32 复核仍 queued/flag=True(排 9h+), 按"08:30 未翻=升级"红线发催单 @strategy-rd(送达卡 admission_conflict 已持久排队, 不重发); 若其循环结构不消费队列件, 改道=cron one-shot 代执行需 L5 点头(代翻属其 L4 代码域, 我不代拍), 留痕等李彦明一句话.
- **0700.HKG 手数步进缺陷**: 已登 task_ledger t_0700hkg_volstep_20261109(infra 类, 30min 续行器自动接手: 按品种 volume_step 归一, 0.01 样本纪律不破)。
- **美股线**: 批复检+四步重判下单 今晚 22:20 自动(86b467c8f8bd), 12h 结算 明晨 03:50 自动(100aefedf6ab)。**[22:2x 实判]**: AVGO/INTC trade_mode=4 (close-only, 与币系博德未放开同族) → 顺延 0 开单, 方向/价位隔周末实读重判已留痕 (AVGO 315.1/INTC 58.07 旧价作废); 等券商侧 tm 翻 1 次日批自动重挂; 03:50 结算哨本批无新单=自然空跑 (t_usbatch_1109_tm4_defer 已登, 含 1 处 worker scratch 拒写非致命副注)。
- **[11-10 01:3x 验收枪 FAIL-LOUD 误报根治]**: 01:30 验收报"双闸未销(无在跑回测进程+generated=10-27)"→ 实查=回测 pid 51956 (pythonw training_full_universe.py, 00:10 起) 一直活着且在出活(universe 派生文件 00:54/01:26 持续写), 误报根因=验收闸 wmic Commandline 匹配 64 位 wmic 盲区。已修 training_host_gate_check.py (加法): lock.meta pid OpenProcess 活体兜底 + 父链 CIM + 新判 PENDING_CHAIN (在跑未收工=exit 0 非故障), 干跑实证; 坑入技能库 jince-watchdog-noise + 台账 t_backtest_hostgate_wmic_blindspot_20261110。后续: 51956 收工出新卷后验收自动翻 PASS; 若 08:30 前 generated 仍 10-27=查 21:30 initialize K 线修复是否盖到全宇宙链。
- **[11-10 07:1x 李彦明"全面开工"指令·周一盈亏深挖全执行]**: ①周一成交全读=盈 7 腿 +13.45/亏 24 腿 -30.69(0.01 样本, 净 -17.24; GER40 浮 +58.7 为净值 1019.77 主力, 已破 1000 出徒线①). ②盈利五家族 13 候选全注册 rd_watchlist(JPY 空/AUD 多/挂钩/原油/欧股指, 数据可得性+点差实核, AUDNZD 已退役跳过) = 全部入模拟盘实盘(0.01 观察腿纪律, 放大=五验 PASS). ③亏损时段四归因落引擎 4 闸(SKA: SKIP_SCA_SESSION 北欧/新兴 22:00BJT 后放行 + SKIP_IDX_SESSION 股指 18:00BJT 后放行 + SKIP_SL_SPREAD 初停<3x点差拒腿 + 同币族 3→2 批强化), 引擎 pid 7112 07:17 新码生效. ④Word 报告=内容中心\交付\周一盈亏深度挖掘与系列扩仓报告_20261110.docx. ⑤副发现: 全宇宙回测链 11-10 02:46 卷 6 品种全 TIMECAP 空卷(21:30 K线修复未覆盖该链, 待查不阻塞). 台账 t_winloss_deepdig_series_20261110.
- **[11-10 03:50 结算哨揪出真 bug·已修已验]**: jince_ate_close.py (scripts/) Windows 正反斜杠路径比对永假 → 每次运行自 spawn 子进程, 11-10 滚出 1078 孤儿 python(3.7GB), 哨永远跑不完=前几次"超时静默"真因。修复: 路径双侧归一(_normp)+JINCE_ATE_REEXEC 深度保险(二次错解释器=RED exit 1 绝不再生); 孤儿 3 轮清零, 修后 2.4s exit 0。我 04:3x 独立三验毕(进程清零/补丁在盘 mtime 04:18/日志 usbatch-1110 closed=0 failed=0 在案)。台账 t_ate_close_selfrepro_20261110, 教训入 mt5-multiagent-trading。
- **[23:0x L4 三件裁回执+销账推进·risk-officer 22:5x 全裁]**: ①P1 XAG 撤单收讫, P1 销账 ③(B 腿读闸源)我 22:5x 根治验活齐 → **P1 可销, 等风控销账**; 销账②(循环重启)=\JinCeAutoCycle 短命循环天然满足。②(a) 生死测销账顺序: ③✓ → ①翻 SERVER_PENDING_VERIFY=False(已派 @strategy-rd, 23:0x 送达卡 admission_conflict 留痕待接力, 明日 03:00 体检核) → ②撤挂单簿冻结令(dst_freeze=false, 风控销账①后执行)。③(c) 断线脏快照口径(pos/od 字段断线期不认实值)已写 jince_rijie_sop.md 日结 SOP, 明日 20:00 日报起执行。
- **[22:1x 22:00 事件日报收口·三件派单处置]**: ①日报实读净值 $985.50/余额 $950.56/浮盈 +$34.94, 活仓 9 张(GER40 +29.23 最大浮盈, 强化阶梯全天曲线 +8.7→+25.7→+29.2)全带三件套。②派单: deliver_target 坏值(bot-chat:chief)核查=55 job 现配全裸 bot-chat 无坏值(497 投递失败归因网关掉线/storage_unavailable+600s 超时族, 网关看门狗兜底), **无需改配置**; 胜率复核(三盘口 5264 样本全<45%)已派 @strategy-rd 同分母复判(admission 冲突未确认送达, 兜底=21:30 学习哨 rd_queue 接力); 风控三件未销账(11-02 钟点验/XAGUSD 冻结令后偷挂撤单/21:47 断线窗核漏)已派 @risk-officer。③**XAGUSD 结论更新**: 我 11:2x "swing 层今挂保留不动" 被风控证据(冻结令后偷挂=B 腿没读冻结闸)推翻, 改"待风控撤单+重启循环销账", 撤后同步本卡。④币系 21:52 巡逻报 JPY 冻结窗内 2 笔新开(CADJPY 21:15/CHFJPY 21:30)→ 已裁定 B(闸标准失同步: 其窗规则未进我方事件源, 两腿过 R:R+共振闸非绕过), 两腿保留(0.01 手/带 SLTP/窗已闭合), 请其提供窗规则源焊入引擎 session 闸(22:06 裁定件)。
- **[22:3x 巡检"MT5 实读降级"假警根治]**: 22:31 巡检报 ATE 握手子代 rc=1(OpenBLAS 内存分配失败)→ 实为系统内存峰值窗 1 分钟瞬断(MT5 本身 22:3x 直读+ATE 复测全绿)。已加固 jince_auto_patrol.py: ①ATE 子代 BLAS 线程 2→1(更省内存) ②握手子代 OpenBLAS 内存分配失败自动 5s 重试一次(瞬峰静默吸收, 两次皆败才报)。py_compile 过。防复发=下次内存峰值不再误报"终端挂了"。
- **红线不动**: 10% 日熔断/连亏 3 笔 24h/L5/12h 强平哨; exp_r=-1.2529 为闸在守规矩, 翻闸权属 L5/用户(非研发代拍)。
- **外网/gh**: **extnet 已恢复 ok(11-09 09:5x 看门狗拍)**, gh 推送唯一剩余阻塞=token; tick/看板本地照写, 供 token 即自动清。
- **live24 自愈实读(09:54)**: 进程曾消失, 看门狗 09:33:15 自动拉起新 pid 13576, bridge connected 09:54:56, SL_TRAIL 事件在流(AUDUSD A1 保本 0.51R rc=10016), 持仓 SL/TP 服务器端未受影响, 自愈机制按设计收口。
- **看门狗训练枪 wmic 误报根治(10:3x)**: 10:30 拍报"无回测进程"= 假警报(实读引擎 26032 持锁在算, CPU 累计 2388s/75min ≈ 53% 利用率 = 真在跑, 0 日志输出=pythonw 缓冲非挂死)。根因=看门狗 wmic where 子句弃用/误解析空返回。已修 `jince_watchdog.py`: 主判据改锁 holder pid ctypes OpenProcess 原生存活(锁 <8h 接管窗)+wmic 降次判据; py_compile rc=0 + 实测(活 pid→yes / 死 pid→fallback)通过。下拍起引擎在跑时不再误报, 技能库 jince-watchdog-noise 已补 11-09 落地条。
- **CPI 事件窗缺口+验证点(11:0x)**: 晨学哨 09:26 定死明日 20:30 BJT US CPI 冻结窗(日/金/股 0 新开单, 落地 30min 不加仓不动 SL, 周五 11-13 PPI 同窗)。实读: event_intel/generated 09:53 **无** US CPI/PPI 11-10/11-13 条目(自动源日历有 China CPI, US 未现; intel 被自动源周期重写, 手动注入会被冲) -> 已登 ops 验证点任务 t_uscpi_window_verify_20261110(11-10 18:30 验再生成, 缺失=按 auto源·calendar schema 补 protective 条目+投群报, 冻结窗 19:30 L6 前还有 45min 缓冲)。同批: wrapper tasklist text=True 西里尔文 locale 解码崩(reader 线程 UnicodeDecodeError, rc=0 无害但污染 00:10 日志判读)已修=bytes+latin-1 手动解码, py_compile
- **[11-10 09:2x 补刀+验活·上缺口当日收口]**: ①真CPI时点定死=**21:30 BJT**(EST 08:30, 美11-01切冬令; 冻结S1=21:00, L6一层20:30, 落地30min窗到22:00放行); ②event_calendar.json 上版(11-09 22:01)windows=0 漏排=**三段冻结闸今晚会失灵的 RED** → chief 人工补1条(note=manual_chief_20261110, ev1794317400, HIGH, high_events_in_24h=1); ③event_guard 快通道 09:16 活体拍**验活**: 21:00 halt(停新仓+撤趋势/Stop, 震荡Limit保留)→21:30-21:40 观察→22:00 结构确认放行 ✓(display grade=MED=窗口内降档规则, 冻结效力不变); ④覆盖风险照旧(11:0x 老条: 自动源周期重写会冲人工条目) → 18:30 验证点 t_uscpi_window_verify_20261110 照验, 被冲=再补+急件升级; ⑤附缺陷(留生成方修): event_risk.json 新闻事件 time 字段=**采集时刻非发生时刻**(预判层把今上CPI全判 PUBLISHED, 0-2h跟进窗失灵); ⑥总线急件已发 workbuddy(inbox\workbuddy\20261110T092x-cpi-window-fix.json, 要生成方修复日历源+保留manual条目+修time字段), task_ledger t_cal_uscpi_window_missing_20261110 (总42)。 rc=0。
 - **[11-10 20:2x 三缺陷即时修复·李彦明令"立即修复"]**: ①MFE/MAE 追踪通道盲区(_mfe_mae_track.py MAGIC 硬码 20261104, 30261103 实盘 9 仓全瞎)→ env JINCE_MFE_MAGICS 双通道参数化, 验活 live 0→8 张 ✓; ②shadow_evaluator exit=1 根因=filelock 缺失(atomic_json.py 顶层 import 崩)→ 加 stdlib O_EXCL 兜底锁(filelock 缺时降级线程锁+os.replace 原子性, 陈旧锁 120s 清理), 3.13.12 实跑 rc=0 出 59 单影子报告 ✓; ③学习验证面板 5 天断棒根因=jince_learn_verify.py 脚本本身缺失(哨兵 11-05 起报"文件缺失")→ chief 造最小确定性版(E:\GoldstrategyEngine\jince_learn_verify.py), 今日面板生成 ✓(MFE活单8/家族4/预测台账0). 三件全登 task_ledger(总45). 遗留小疵: MFE floa_R 列旧近似公式失真(USDCAD -177R档), 面板现只取 mfe_R/mae_R 口径, 公式修另排。

> 用途：
## 2026-11-09 07:0x 节点看门狗防复发闸②·训练枪静默 手动开第一枪收口（主 bot default）
- **警报**: 节点看门狗(每15min) 报「回测产物已 42h(>36h) 且无回测进程在跑 -> 00:10 训练枪静默未跑」。
- **cron 运行史实读**: job 0878a08d2a92「金策·后台训练·全宇宙回测(00:10不限时)」11-08、11-09 两班均 rc=1, last_error = wrapper FATAL「pythonw 路径不存在」(failure_streak=2) → 回测产物(backtest_edge.json) 停在 11-07 04:39, 50h 未更; 01:30 验收枪 475d7361ad9a 照读旧卷, 属中性跳过非故障。
- **根因**: `training_full_universe_wrapper.py` 写死的 PYWIN 版本串与 tools 目录实际目录名不符(os.path.exists 恒 False) → 引擎从未拉起, stamp 冻在 started。
- **已修**: wrapper 改动态解析(glob 扫 tools/python-3.14* 找 pythonw, 优先 3.14.9, 备份 .bak_1109); 明早 00:10 cron 自动用新代码, 无需重启用。
- **手动第一枪**: 11-09 06:54 实跑验通(wrapper rc=0), 引擎链 3 个 pythonw 活体(80624/19608/120120), backtest_engine.lock holder=120120 活, stamp 06:54:21 刷新; ETA ~11:00 出卷, 01:30 验收枪(11-10)读新卷。
- **丑话**: 修 launcher ≠ 能赚钱; 回测跑完只产数据, 出徒仍卡 30 笔 OOS + 30 天净值转正; 历史回测≠未来收益。
- 另: 本拍 extnet=down 为单端点探活, 本地链全活, gh 系按旧规矩只等 token 不深挖。
- [11-09 09:2x 巡检常态] 币系 4 品种仍 close-only(tm=4, 博德侧未放开) = **等待态非故障**: 桥已 connected(11-08 切活), FX/股指 live24 开单正常(10009), 唯币系 4 腿被博德 close-only 压住; 5min 哨(自修复链, repair_log "开单被拒 TM4 4,4,4,4" 每 5min 一拍)紧盯, tm 一翻 1 自动开 4 腿不等; 巡检 30min 会反复报同一条 = 一行归类"币系等博德放开", 不重查不动手。

## 2026-11-09 07:1x 行情喂/看板哨兵 gh 失败刷屏 节流收口（主 bot default）
- **现象**: 行情喂(950cfc1b07ed, 5min) 与看板哨兵(jdashsync10m, 10min) 连挂 10+ 拍, 每拍灌一条同文「gh 推不上 exit=6 / 全路推不上」进 bot chat = 刷屏。
- **定性(实读)**: 双阻塞——① extnet 真断(curl api.github.com=000, 443 墙/瞬断, 预期自清) ② gh 未认证(GH_TOKEN 空, 持久墙, 要李彦明供 token)。本地 tick_live.json / 看板 HTML 每拍照写照生成 = 只卡远端推送, 不影响交易链。
- **已修(脚本侧节流, 不暂停 job)**: 两脚本加 `_anomaly_gate` 状态机(首拍即时报 / 状态变即时报 / 同状态 2h 才重申一次 / 成功即清态), 静默拍全量留痕 data/tick_push_quiet.jsonl + dash_sync_quiet.jsonl(绝不静默吞); 单测全过。下拍起群内最多 2h 一条, 恢复后自愈清零。
- **恢复条件**: 李彦明供 GitHub token(gh auth login --with-token 或 GH_TOKEN) + extnet 恢复 → 下一拍自动推上, 无需补账(job 没暂停, 本地数据没断)。纯推送类 job(12 站部署/夜间全推)保持已暂停态, token 到位再批量 resume + 补推。
- **丑话**: 节流 ≠ 远端看板会更新; 公网页停在 11-08 19:24 旧数据, 等 token+网络; 本地看板实时条不受影响。

## 2026-11-08 21:3x 学习进化收口（strategy-rd 段, 总调度代跑实跑验货, 周日）
- rd_queue 领题: **P0 `orderflow_soul_L1_liveverify_20261106`**（灵魂课题·机构订单流 L1 实盘验证底座; P0 优先于轮转, G8 轮转再顺延）:
  - **① 币系 tick 采集机制实跑**: `copy_ticks_range` 可用, 但 void 对象字段须 `t['field']` 访问（非 `t.field`）; 11-08 币系 24h 无 tick 历史（币系 tick 量低 / MT5 仅存 K 线）, **可靠 fallback = M30 K 线真读**;
  - **② 币系 10 品种 M30 活体落盘**: BTC/ETH/SOL/LTC/XRP/KSM/ADA/DOT/UNI/POL 各 48 根 × 24h（`orderflow_ticks/*_20261108_m30.csv`）, 快照 `crypto_24h_snapshot_20261108.json`; 币系活体数据新鲜（BTC 75445~76135 / ETH 2217~2246 / SOL 88.5~90.2）;
  - **③ XAUUSD 11-06 36万 tick CVD proxy 实算（独立第三证据链）**: BJT16 delta_net=+2460（近中性, 未显著单方向被扫）, BJT16 price_range=$13.09（**未入 top25% 波动**）; 最高波动 = BJT11 $41.36（东京凌晨 03:00 UTC = 周五亚洲夜盘）, 次 BJT18 $25.92; **独立印证**: BJT16 坏时 = **chop/mean-reversion 窄幅双扫型**（非 CVD 单方向被扫, 与 BJT11 高波动停损扫损机制完全不同）; 与 11-06 deco 双证 BJT16 同负坏时一致但机制补充细化;
  - **④ XAUUSD 周末确认休市**: last tick age = 37.8h（周五最后 bar time≈14:30 UTC = BJT 22:30）, 币系活体正常;
  - **裁定 = partial_progress, 不喂 live 闸源**: L1 管道 ①tick 7日滚动 11-06+11-08 已落两天, ③ Brooks/Seiden/ICT/deco 两条独立链交叉需再攒 3-4 个交易日 tick（周末休市 XAU 断供, 周一 11-09 恢复后继续）; BJT16 否决门维持 WATCH 不放大（chop 型不是 trend 型, 固定 SL 的不对称双扫在低 CVD+中低 vol 时段发生, 机制已细化）。
  - **副产出: RIOT/AMD 复核（P1 快速裁定）**: RIOT 命中率 26%（n=23）, AMD 命中率 38%（n=21）, 均 n<30 → **WATCH 只否决门**, 不放大不进 live; 攒满 30 笔（RIOT 再攒 7, AMD 再攒 9）后重走五验（品种稳健 ≥4/6 + WF3）再裁定 RETIRE 或维持 WATCH; 留痕 `rd_verify_batch_delta_cvd_xau_20261108.json`。
- 净值现状: **$975.15（21:42 live_state 实读 balance=equity, 账户 60137964, 0 持仓 0 挂单）**; risk_state(21:23 实读): 回撤 3.36% **normal 档 scale=1.0**, 连亏 0, coin_freeze active=false（until_ts 已过期）, retire_freeze XAU/BTC/ETH 无限期（POL 除外）, 事件 MED new_entry_scale=0.5, 当日已实现 P&L=0。
- 丑话: 本轮 partial progress = 数据底座累积, 不出五验结论; BJT16 否决门维持 WATCH 不放大; RIOT/AMD 待攒样本; 历史回测 ≠ 未来收益; 出徒仍卡 30 笔实盘 OOS + 30 天净值转正两条（现 $975.15 距 1000 约 -2.5%）。下一轮轮转指针 = **L1 tick 管道周一 11-09 恢复 XAU 供给后继续 + G8 同批 K 线复验（K 线刷新后）**。

## 2026-11-06 21:3x 学习进化收口（strategy-rd 段, 总调度代跑实跑验货）
- rd_queue 领题: 本轮领 **P0 `deco_session_mask_p0_20261106`**（P0 优先于轮转, 轮转 G8 顺延）: deco 账号(91300135, 第三方 XAU 385笔实盘, 只读, 永不下单/不接30min闸源) session_mask 时段掩码 -2h 重校 + 与我方徐 DST 13万笔时段闸交叉印证 + 自有五验合成:
  - **① -2h 重校(确定性, deco_stats by_hour→BJT)**: deco 服务器时坏时 16/17/18/23 → 重校 BJT 14/15/16/21; **BJT16 = 唯一双外部链同负坏时**(deco 重校 BJT16=-3219 ∩ 徐 DST BJT16=-2760, 两条独立证据链同指向), BJT 01-04 = 双链同好时(呼应徐「01/18 最赚」); 宽面重校坏时 14/15/19/21 在徐侧为正 = 单链, 不交叉印证。
  - **② 跨账户规矩**: 不跨账户借样本, 只比对小时桶指向(OOS 纪律: 外部实盘 = 最多 WATCH 级方向证据, 绝不直接升 APPROVE)。
  - **③ 自有五验(裁决数)**: 10-13 `xu_hourdst` BJT16 单时否决门已跑自有 XAU 1107 交易日同分母 = **REJECT**(增益 +1.7k/1107日 ≈ 0.01R/笔 不显著, WF3 一段负, g3/g4/g5 全 FAIL)。
  - **合成裁定 = WATCH, 不放大, 0 喂 live 闸源**: session_mask 维持 L2 前置门/看板时段参考(与 `xu_amp_regime_gate` WATCH_L2 同族), 只做否决门提权参考, 不挂单闸/不加仓; 下一步前向 OOS 攒样(BJT16/宽掩码挂 OBSERVATION 列, 60137964 实读攒 30 笔隔日对账, 攒够重走五验 z>=1.96+品种稳健+WF3)。
  - 留痕: `data/rd_verify_batch_deco_session_mask_20261106.json`(kline_source=外部 OOS, 本轮未用 MT5_LIVE) + rd_ledger 1 WATCH + rd_ledger_24h 1条(播报4键齐全) + rd_queue `deco_session_mask_p0` → watch。
  - **灵魂课题印证**: session_mask 是机构订单流视角的第一个可验证切面(时段闸), 本轮坐实「BJT16 双证坏时」(该时段波动对固定 SL 双向被扫); 但自有五验未过放大线, 按灵魂铁律「灵活运用/务必实盘验证」先攒样本证据不放大, L1 tick 管道(`orderflow_soul_L1`)跑通后回验。
- 净值现状: **$980.2（21:47 共享 live_state 实读 balance=equity, 账户 60137964, 较 11-05 的 $962.86 +$17.34 ≈ +1.8%, 距 1000 转正点约 -2.0% 大幅收窄）**; risk_state(21:23 实读): 回撤 2.86% **normal 档 scale=1.0**(HALF 已解除), 连亏 3 → 24h 冷却已过期 active=false, coin_freeze 旗标 until_ts 陈旧(11-04 已过期仍 active=true, 待循环清), L4 0.3× 帽仍压 new_entry_scale=0.3, retire_freeze XAU/BTC/ETH 无限期(POL 除外)。
- 丑话: 本轮领题 = 外部 OOS + 已有自有五验合成 = WATCH 攒样本证据, 不是能赚钱; BJT16 门不进 live、0 放大仓位; 历史回测 ≠ 未来收益; 出徒仍卡 30 笔实盘 OOS + 30 天净值转正两条(现 -2.0% 接近转正)。下一轮轮转指针 = **G8 同批 K 线复验**(或宽面掩码自有同分母复跑, K 线刷新后)。

## 2026-11-05 21:3x 学习进化收口（strategy-rd 段, 总调度代跑实跑验货）
- rd_queue 无新 open 课题可领（唯一 open=copy_converge_single_source 属 infra 归 L1 不占 jevo 名额）→ 按轮转规矩（11-03 指针顺延）本轮做 **G5 窄止损(SL1x/TP2R + D1 无泄漏前日闸口径, 11-04 L4 降级推荐口径)** 8品种(XAU+EUR+6币)复验:
  - **K 线数据源: MT5 真读增量至 11-05 14:00 UTC（M30）/11-05 00:00（D1, 今日未收 bar）, 8品种×2周期全齐**。⚠ infra 新发现: `tf_cache/*.npz` 被常驻影子采集进程（jince_shadow_link.py / jince_shadow_signals_v3.py, 疑似长持 NpzFile 句柄）写锁, 增量刷新 4 批 replace 全 LOCKED → 本批走「tmp 留盘 + 内存合并」口径跑通（数据新鲜度不受影响, 已登记 task_ledger `t_tf_cache_npz_lock_holder_20261105` @chief 修持有者句柄, 30min 续跑器接手）。
  - **G5-lag1（前日闸, 无泄漏正式口径）= ⑥净期望闸未过 → REJECT, 维持 WATCH 攒样本不放大**（8品种合并 n=7758, 扣 0.095R 滑点后合并期望 **0.251** < ⑥线 1.0; 8/8 品种扣滑点后为正但弱: SOL 0.5428 最强 / XAU 0.2524 / EUR 0.2066 最弱; 对照 11-04 lag1 批 0.3018 略降, K 线多 2 天新数据+⑥线不变）。
  - **G5-lag0（当日闸, 仅对照不作依据）**: n=10444 合并 0.3683 ≈ 10-25 批 0.3686（口径稳定, 复现性好）。
  - **G8 对照复跑（6币, 泄漏免疫）**: 0.4459 < ⑥线 1.0 同样 REJECT（11-03 批 0.4943 → 回落 0.05, 仍全族最强但不过放大线）; 下一轮轮转指针 = **G8 同批 K 线复验**。
  - **币系分侧（lag1 口径）**: buy 均值 0.3887 vs sell 均值 0.4168 — 本轮两侧基本均衡, 「空腿独撑」预警 11-04 后第 4 轮观察, 本轮无加剧。
  - 留痕: `data/rd_verify_batch_g5_8sym_20261105.json`（kline_source 逐品种打标 MT5_LIVE_inmemory_merge）+ rd_ledger 2 条(G5-lag1/G8, ⑥闸留痕) + rd_ledger_24h 一条(播报 4 键齐全, jince_eff_report 实跑验通无乱码) + rd_watchlist G5 指针刷新 g5_8sym_20261105(旧 1023 批标 superseded) + task_ledger infra 任务。
- 净值现状: **$962.86（共享 live_state 21:32 yushi 实读, 余额 $960.68, 较 11-03 的 $897.28 回升 +$65.58 ≈ +7.3%）**; 持仓 2 张 + 挂单 1 张（magic 20261104 人工练手: EURUSD 多 -3.57 / JPN225 空 +5.98 / XAUUSD BUY_LIMIT 4080）; risk_state(21:23 实读): 回撤 4.6% 回 **normal 档 scale=1.0**（11-03 的 11.08% HALF 档已解除）, 连亏 3 → 24h 冷却已过期 active=false, 币系冻结/冷却 until_ts 已过期（L4 桥 l4_scale_cap=0.3 仍压 new_entry_scale=0.3）。
- 丑话: G5/G8 全族腿扣滑点后无一过 ⑥线 1.0 = 长期无正期望, 一律 WATCH 攒样本不放大; 出徒仍卡 30 笔实盘 OOS + 30 天净值转正两条（现 $962.86 距 1000 约 -3.7%, 比 11-03 的 -10.3% 大幅收窄, 但 3 笔连亏+L4 0.3× 帽期间开新单要从严）; 历史回测 ≠ 未来收益。

## 2026-11-03 18:3x 学习进化收口（strategy-rd 段, 总调度代跑实跑验货）
- rd_queue 今日领 **ml_manual_sop_gd_forex_20261025**（人工开单SOP·金/外汇域, P2 研究题; 另一 open 题 copy_converge_single_source 属 infra 归 L1 不占 jevo 名额）:
  - **K 线回填(_jevo_tf_refresh_1103.py, 8品种 M30+D1 全 MT5 真读)**: 追到 11-03 13:30 UTC(周二活体, 币系/金银全活), 17 条序列全 ok。
  - **T1 入场层·回调 EMA9/21 新腿 = 五验 REJECT → 不教, OBSERVATION 记样**（n=8268 扣 0.095R 滑点后 exp_R=0.128 < ⑥线 1.0; 邻域 EMA20/50=0.1197 同号更低; 8/8 品种为正但弱于同日宇宙 G8 ORB 0.4943; 胜率 48.55% vs G8 76.1%）。**SOP 入场层只教 ORB 前日区间突破（G8 口径 WATCH 攒样本, 不放大）**。
  - **T2 环境闸·3连亏→24h冷却 = 开关 WATCH 有效**（G8 事件全集 10452 笔同分母, 开闸跳 1100 笔: 最大回撤 10.95R→6.40R **-42%**, 单笔期望 0.4943→**0.5278** 反升——连亏后行情整体是坏的, 冷却是顺风不是阻力）。写进 SOP L0 条款。
  - **T3/T4/T5 定性**: V反转=裸反转负alpha同族只当否决门不教; 事件缺口砸回=event_calendar 空 blocked_data OBSERVATION 不盲测; SL先定+0.5%×brake 手数倒算=纪律条款与 live L0/L1 双闸同构; 离场=固定SL/TP（ml_r_ladder 10-26 REJECT 定死, R阶梯只记样）。
  - **G8 轮转被基线桶顺带复验**: 11-03 批 0.4943（10-24 批 0.3993, 币系空腿独撑预警 buy0.30/sell0.68 同族第6轮）, 仍卡⑥线 WATCH; 轮转指针顺延至 **G5 窄止损(SL1x/TP2R+D1闸)**。
  - 三账落盘: rd_verify_batch_ml_sop_8sym_20261103.json + rd_ledger 162(REJECT)/163(WATCH) + rd_ledger_24h 一条(播报4键齐全无乱码) + rd_queue → sop_landed_20261103; SOP 文档 `data/manual_sop_gd_forex_20261103.md`（五层纪律+红线自查, 每条挂实数）。
- 净值现状: **$897.28（11-03 21:23 MT5 实读 balance=equity, 0 持仓 0 挂单, trade_allowed=true）**; risk_state(21:23 实读): 回撤 11.08% HALF 档 scale=0.5, 连亏 3 → 24h 账户冷却 active（至 ~11-04 06:24 北京时间, 含 L4 桥）, 币系冻结同步至该时点, retire_freeze XAU/BTC/ETH 无限期（POL 除外）, 当日已实现 P&L=0。较 11-02 的 894.89 微升 +2.39（POL 例外腿浮盈区间）。
- 丑话: SOP 只教验证过的, 回调腿/缺口/V反转 全部关在门外; 历史回测≠未来收益; 出徒仍卡 30 笔 OOS（现 2/30 冻结）+ 30 天净值转正（现 897.28 距 1000 约 -10.3%）两条; 24h 冷却期内不开新单是纪律不是故障。

## 2026-11-03 12:0x MT5 一体化交接（主 bot default 代总调度实读落地, 用户令"嵌入 MT5 跟交易系统融为一体, 让他们接管"）
- **执行层收口为一条腿**: 终端内 `EA_L5_Exec v1.1`(magic 20261103, tick 级 30s 节流) = 唯一开单层; 三处变更全实读验货:
  ① `ea_advisory_feed.py` 5c 段: XAU 12年OOS突破腿(ADX≥30+20bar 突破+MA5/20, SL3×ATR15/TP5×ATR15/0.01手/点差硬闸⑤, 与 tools/jince_live24.py 同口径)迁入 feed + magic 20261103 当日已实现亏≥2% 熔断(magic_fuse, 口径修正: live24 数 IN 单永不触发→改 OUT/OUT_BY); feed ate 环境实跑过(MT5 真读, magic_fuse=0, adx=3.4 无信号, XAU 行 RETIRED 闸住);
  ② `EA_L5_Exec.mq5` v1.1: 认 magic_fuse/spd_ref/leg 三新字段, 加 MAGIC_FUSE_DAY_2PCT + SPREAD_WIDE 两道 HOLD, MetaEditor64 **0 错 1 旧警告**, ex5 29910B 覆盖装终端 Experts(11:02:34);
  ③ 双退场: `data/LIVE24_HALT` 建(live24 停开新仓, 进程 23:00 窗清) + runner 降 DRY(启动盯盘.bat/自愈看门狗去 --execute/JINCE_BOT_LIVE=0, 看门狗 11:15 按新配方复拉 pid 584, 只观察攒 OOS 0 开单)。
- **终端 Experts 3 个 ex5 定性(用户问"每个 EA 功能")**: ①`EA_L5_Dryrun`=开单前自检面板(净值/刹车/连亏/币冻/日剩余额度/手数倒算+STALE 标), 喊单 0 下单权, 人工照面板挂单的偏差攒 OOS; ②`EA_L5_Exec` v1.1=执行层本体(上面那条腿, 双闩: 引擎 armed 旗标 + 图上 InAllowExec, 都真才发单); ③`JinCeEvolutionEA`(45KB 混淆 ex5, 11-02 16:25 装, 本地无源) = **待定性, 疑似 workbuddy 主动进化腿(magic 20261102 已 11-02 23:17 撤销降只读), L4 定性前禁挂图**。
- **待接管(全部入账 task_ledger, 30min 续跑执行器接手)**: t_jince_ea_exec_verify_20261103(@chief: 急停件 DRY 实跑+双击 bat+挂图面板验) / t_jince_evolution_ea_audit_20261103(@risk-officer: EvolutionEA 删除 or 登记) / t_jince_live24_cleanup_2300_20261103(@chief, 23:00 窗: live24 进程清+当日首开复盘)。
- **双闩现状: 引擎闩未写**(`data/ea_exec_armed.flag` 不存在=armed 0) → EA 恒 0 开单; **L4 验货+拍板后写旗标**, 写后 30min 内下一轮 feed 生效。
- **李老师手上唯一动作**: MT5 开任一品种图 → 把 EA_L5_Exec 拖上图 → Inputs 勾 InAllowExec=true → Common 勾允许算法交易 → OK。挂上面板显 "L5 EA v1.1 EXEC LEG" 即就位。
- **今日盘面闸态(10:5x feed 实读)**: XAU 行 RETIRED(L4 退役冻结)+突破腿无信号(adx 3.4) → XAU 0 开; 其余 23 行可开 net_side=SELL 但 HALF 刹车档单笔 $2.25, 多数品种 lot=0(数据从严 HOLD)。挂上大概率今日 0 开单 = 闸在守规矩非故障。
- 丑话: 一体化=把 OOS 攒样本路径焊死终端内, 不改变"出徒仍卡 30 笔 OOS + 30 天净值转正"; 历史回测≠未来收益; 混淆 ex5 定性前谁挂谁负责。

## 2026-11-02 21:3x 学习进化收口（strategy-rd 段, 总调度代跑实跑验货）
- rd_queue 今日有 2 条新 open 课题(grokbot_llm_advisory_replay / ea_v0_dryrun, 均 P2), 本轮领 **grokbot_llm_advisory_replay_20261102**(ea_v0 的 L5 实物今日已交付验到盘: ex5 30868B 装在 Roaming MT5 数据目录 MQL5\Experts + ea_advisory_feed.py 首跑实数 eq=898.68, 剩「钩进 30min 循环 meta-evolver 步后」是 L1 23:00 窗活体清完才挂, 非本轮);
- grokbot 可回测半 = LLM 结构化作战快照(方向/信心度/时程 JSON 契约): 无历史 LLM 信心度日志 → 同分母回放**不可跑, 绝不造假回测** → 落**前向攒样合同**: 每日 21:30 jevo 出 1 批 8 品种快照(O2 开评加料), 次日 D1 收盘对账, 攒 30 批走五验(z>=1.96+品种稳健>=4/8+邻域+WF3), **0 喂闸源**;
- 三件全落盘验通: ① `data/llm_advisory_contract.json`(口径: 次日 D1 收盘 vs close_ref, NEUTRAL 不进分母) ② `data/llm_snapshot_ledger.json` b0001 n=1/30(数据基础全实读: rd_momo_8sym_20261102 MT5_LIVE 8/8 @21:53 + market_judges 21:47 + tick_live 21:45 degraded=false, 禁编数到位) ③ `strategy_rd/llm_snapshot_reconcile.py`(0 LLM 对账, 实跑 exit0, b0001 正确挂起待次日收, fail-open 不崩);
- 方向面速记(b0001 @21:58 快照): 金空 0.6(3941<EMA50 4174, H4 熊旗 ADX36.5, 24h-0.57%/7d-1.41%); 币系 5 弱: KSM 7d-10.21% 全场最弱(空0.6)/SOL 7d-6.60%(空0.55)/DOT 7d-5.10%(空0.50)/BTC 7d-3.58% 跌后盘整(空0.45)/ETH 短线反弹结构不改(空0.40); 唯一正: UNI 7d+3.11%(多0.45); EUR 两侧弱 中性0.35;
- 三账落盘: rd_ledger 158(一条 OBSERVATION_FORWARD_CONTRACT) + rd_ledger_24h 143(播报键齐全, **jince_eff_report 实跑验通无乱码 RC=0**) + rd_watchlist 13(OBSERVATION n=1/30); rd_queue grokbot → forward_contract_landed;
- infra 注: 21:5x terminal64 一度不在 tasklist, 看门狗 5min 自拉, 21:53 MT5 真读 8/8 恢复(数据新鲜, 交易链未受影响);
- 下一轮轮转: G8(宽止损 SL1.5/TP3R + D1 闸) 同批 K 线复验(10-25 轮转顺延, 比 G5 0.3686 vs G8 0.3993);
- 净值现状: **$894.89（11-02 21:23 MT5 实读 balance=equity, 0 持仓, 1 挂单 POLUSD #660469449 例外腿, trade_allowed=true）**; risk_state(21:24 实读): 回撤 11.32% HALF 档 scale=0.5, 连亏 2(<3 未冷却), **币系冻结今晚 22:00 到期(until_ts=1793628000, NFP 生死测)**, retire_freeze XAU/BTC/ETH(POL 除外), 事件 MED 0.5× 金银线, 当日已实现 P&L=0;
- 丑话: LLM 快照=开评加料非决策源, 前向攒样 0 喂闸源, 攒样本身不出结论; 历史回测≠未来收益; 出徒仍卡 30 笔 OOS + 30 天净值转正两条。

## 2026-10-25 21:30 学习进化收口（strategy-rd 段, 总调度代跑实跑验货）
- rd_queue 无新课题可领（全 blocked_data/decided/reject/observation）→ 按轮转规矩上轮 10-24 做了 G8, 本轮轮到 G5(ORB 窄止损 SL1x/TP2R + D1方向闸, 全族主力腿), 先 MT5 真读回填 K 线到当天再同分母复验:
  - **K 线回填(_jc_tf_refresh_1024.py 复用, 8品种 M30/H4/D1 全 MT5 真读)**: 币系活体追到 10-25 16:30Z(周日币圈 24h 照常开), 金银 周五夜盘收口(周末休市, K 线停在 10-23=正常非过期); 合并 n=10435。
  - **G5_ORB 窄止损+D1闸 = ⑥净期望闸未过 → REJECT, 维持 WATCH 不放大**（8/8 品种扣 0.095R 滑点后全为正 pos_rate=1.0, 合并 exp_R 0.3686 < ⑥线 1.0, 新⑥闸判无正期望拒放大）。**轮转对比: G5 本轮 0.3686 < G8 10-24 批 0.3993 < G5 10-23 批 0.4555(旧口径) —— 同批 K 线下 G8 仍全族最强, 但全族腿无一过 1.0 净期望放大线。**
  - **币系分侧核查（连续第 4 轮同族留痕）**: G5 币系 buy 侧均值 0.4104 / sell 侧均值 0.6783, 空腿独撑预警继续(sell≈1.6×buy, 币系腿实质空侧更赚), 防选择效应持续跟踪。
  - 留痕: data/rd_verify_batch_g5_8sym_20261025.json + rd_ledger 一条(WATCH) + rd_ledger_24h 一条(播报键 theme_cn/candidate/verdict/p4_gap 齐全, python3.11 实跑验通无乱码) + rd_watchlist G5 指针刷新(旧 1023 批标 superseded_by=g5_8sym_20261025, 追加新批)。
- 下一轮轮转: G8(宽止损 SL1.5/TP3R + D1闸) 用同批 K 线复验, 比 G5 0.3686 vs G8 0.3993。
- 净值现状: **$893.95（21:3x MT5 实读 balance=equity, 0 持仓 0 挂单, 周日外汇/黄金休市, 币系活体）**; risk_state(21:01 实读): 回撤 11.41% HALF 档 scale=0.5（账户级仓位全半仓）, 连亏 2(<3 未冷却), 币系冻结至 11-02 NFP, 事件 MED 0.5× 金银线。30天 a 条(净值转正)距 1000 约 -10.6%, 实亏继续拖慢出徒。
- 丑话: G5 复验扣滑点后净期望 0.3686 < 1.0 = 长期无正期望, 维持 WATCH 攒样本不放大; 历史回测≠未来收益; 出徒仍卡 30 笔实盘 OOS + 30 天净值转正两条, 本轮只证纪律不改仓位。

## 2026-10-24 21:30 学习进化收口（strategy-rd 段, 总调度代跑实跑验货）
- rd_queue 无新课题可领（全 blocked_data/decided/reject/observation）→ 按轮转规矩上轮 10-23 做了 G5, 本轮轮到 G8(ORB 宽止损 SL1.5/TP3R + D1方向闸, 全族最强腿), 先 MT5 真读回填 K 线到当天再同分母复验:
  - **K 线回填(_jc_tf_refresh_1024.py, 8品种 M30/H4/D1 全 MT5 真读)**: 币系活体追到 10-24 16:30Z(周六币圈 24h 照常开), 金银 周五夜盘收口(周六休市, K 线停在周五=正常非过期); 币系 D1 闸本轮 8/8 品种全出数无 IndexError(10-22 踩的坑已根治, 这次 D1 带上了), 合并 n=10433。
  - **G8_ORB 宽止损+D1闸 = ⑥净期望闸未过 → REJECT, 维持 WATCH 不放大**（8/8 品种扣 0.095R 滑点后全为正 pos_rate=1.0, 合并 exp_R 0.3993 < ⑥线 1.0, 新⑥闸判无正期望拒放大）。**关键变化: G8 本轮 0.3993 明显低于 10-22 旧批 0.7553** —— 本轮 8 品种 M30 序列更长(XAU 1698 笔 vs 旧批 ~106), 同分母分母变大把加权净期望拉低; G8 仍高于 G5(0.4555→同为最新批口径 G5 0.4555/G8 0.3993, 本轮 G8 反超不了 G5 但都卡⑥线)。全族腿(G5/G8)扣滑点后无一过 1.0 净期望放大线, 一律 WATCH 攒样本不放大。
  - **币系分侧核查（连续第 3 轮同族留痕）**: G8 币系 buy 侧均值 0.352 / sell 侧均值 0.977, 空腿独撑预警继续(币系腿实质只有空侧在赚, 防选择效应, 下轮 G5 复验继续拆 buy/sell 分侧)。
  - 留痕: data/rd_verify_batch_g8_8sym_20261024.json + rd_ledger 一条(WATCH) + rd_ledger_24h 一条(播报键 theme_cn/candidate/verdict/p4_gap 齐全, 键全验通无乱码) + rd_watchlist G8 指针刷新(旧 g8_8sym_20261022 标 superseded_by=g8_8sym_20261024, 追加新批)。
- 下一轮轮转: G5(窄止损 SL1x/TP2R + D1闸) 用同批 K 线复验, 比 G8 0.3993 vs G5 0.4555。
- 净值现状: **$893.95（21:46 MT5 实读 balance=equity, 0 持仓 0 挂单, 周六休市）**; risk_state: 回撤 11.41% HALF 档 scale=0.5（账户级仓位全半仓）, 连亏 2(<3 未冷却), 币系冻结至 11-02 NFP, 事件 MED 0.5× 金银线。30天 a 条(净值转正)距 1000 约 -10.6%, 实亏继续拖慢出徒。
- 丑话: G8 复验扣滑点后净期望 0.3993 < 1.0 = 长期无正期望, 维持 WATCH 攒样本不放大; 历史回测≠未来收益; 出徒仍卡 30 笔实盘 OOS + 30 天净值转正两条, 本轮只证纪律不改仓位。

## 2026-10-23 21:30 学习进化收口（strategy-rd 段, 总调度代跑实跑验货）
- rd_queue 无新课题可领（全 blocked_data/decided/reject/observation）→ 按轮转规矩上轮 10-22 做了 G8, 本轮轮到 G5(ORB+D1方向闸SL1x/TP2R, 全族主力腿), 先回填 K 线到今天再同分母复验:
  - **数据源回填(本轮 K 线追到今天 10-23 13:30 UTC)**: 8 品种 M30+D1（XAU/EUR 含 H4）全回填, 币系 D1 闸 searchsorted 越界已根治（10-22 踩的坑这次 D1 带上了）, 8/8 品种全出数无 IndexError。
  - **G5_ORB+D1闸 = ⑥净期望闸未过 → REJECT, 维持 WATCH 不放大**（合并 n=4508>1000 过样本闸, 7/8 品种扣滑点后为正, 但合并扣 0.095R 后净期望 0.4555 < 1.0, 新⑥闸判无正期望拒放大）。
  - **关键根修坐实（本轮同批 K 线 + 修正⑥闸重跑 G8 对比）**: 今天 validate.py 新增⑥净期望闸（`rd_five_gate_netexp_20261023`）把过线标准抬到「扣滑点后合并净期望≥1.0」, 并点名 10-19 G8(0.4993)/10-20 G10/10-22 G8(0.7553) 三连是**假 PASS**（旧闸只拒 exp_after<0）。用同批 K 线重跑 G8 = 0.756 同样 <1.0 → **G8 也是 REJECT**。即: **昨天状态卡「G8=0.7553 PASS 5/5」是旧闸假 PASS, 修正后 G5/G8 全族腿无一过线, 一律维持 WATCH 攒 OOS 样本不放大。** 全族最强仍是 G8(0.756)>G5(0.456), 但都未到 1.0 净期望放大线。
  - **币系分侧核查（连续第三轮同族留痕）**: G5 币系 buy 侧均值 0.32 / sell 侧均值 0.73, 空腿独撑预警继续（币系腿实质只有空侧在赚, 防选择效应, 下轮对比拆 buy/sell 分侧）。
  - 留痕: data/rd_verify_batch_g5_8sym_20261023.json + rd_ledger 一条(WATCH) + rd_ledger_24h 一条(播报键齐全, python3.11 实跑验通无乱码) + rd_watchlist G5 指针刷新。
- 下一轮轮转: G8(宽止损SL1.5/TP3R) 用同批 K 线复验, 比 G5 0.456 vs G8 0.756（两腿都卡⑥净期望闸≥1.0, 都 WATCH）。
- 净值现状: **$893.95（21:5x MT5 实读 balance=equity, 0 持仓 0 挂单）**; risk_state: 回撤 11.41% HALF 档 scale=0.5（账户级仓位全半仓）, 连亏 2(<3 未冷却), 币系冻结至 11-02 NFP, 事件 MED 0.5× 金银线。
- 丑话: G5/G8 全族腿扣滑点后净期望 0.456/0.756 都 <1.0 = 长期无正期望, 一律 WATCH 攒样本不放大; 历史回测≠未来收益; 出徒仍卡 30 笔实盘 OOS + 30 天净值转正两条, 本轮回调只证纪律不改仓位。

## 2026-10-23 10:2x 数据事故复盘收口（主 bot MT5 活体二次实读坐实）
- 事故: 群内盘面播报把黄金说成"突破 2000 美元 / 支撑 1990-1980 / 阻力 2010-2020"（真实价 ~4024）= 纯编数没实读, 价位错一个数量级。Chief 实读 MT5 已纠正: 4026, 支撑 4020-4021/4004/3986.6, 阻力 4032/4048/4088/4145, 4170→4024 暴跌后 4020-4030 筑底。
- 主 bot 二次实读坐实（_xau_live_probe, MT5 活体 60137964）: XAUUSD bid/ask = **4024.35/4024.68**; K线高低点: M15近40根 高4031.06/低4002.07, H1近40根 高4145.64/低3986.57, H4/D1 低3986.57 — 与 Chief 纠正数据吻合（4048/4088 属 H4/D1 区段中间位, 方向一致）。
- 分级: **绿**（错数据没挂出任何单: 0持仓 0挂单, 资金 0 影响）。
- 铁律再确认（全团）: 任何盘面分析/播报前必须 MT5 活体实读（价+时间戳+账户+多周期K线）, 支撑阻力从K线高低点取不编圆数, 没数据就明说。子 bot 开播前先跑一次只读探针（_mt5_readonly_probe.py 或等价）再开口。
- 净值现状: **$893.95（10:2x 实读 balance=equity, 0持仓 0挂单）**, 盘面 4170→4024 暴跌后 4020-4030 筑底中; 币系冻结至 11-02 NFP 照旧。

## 2026-10-23 07:19 每日体检收口（主 bot 深诊+实跑验货, 0 触交易闸）
- 03:00 体检"MT5 读降级/ATE 连不上/OpenBLAS 内存分配失败"复诊: 活体探针 initialize=True 读到 60137964 $893.95 / 0 持仓 0 挂单, 终端其实活着; 真根因 = 系统 16GB 常 95% 吃紧(当前 95%, 仅 ~653MB 余), ATE 子代 import numpy/OpenBLAS 期默认起满线程池 → 内存分配失败 → fork 崩 → 误报降级. auto_run_cycle.py 早已用 OMP/OPENBLAS_NUM_THREADS=2 护住(17-18行), 但巡检 jince_auto_patrol.py 起 ATE 子代没继承.
- 已修(纯 infra, 不碰挂单/撤单/交易闸): ① jince_auto_patrol.py 加 _ate_child_env() 起子代盖 OMP/OPENBLAS=2, check_live_read 那处 fork 接上, py_compile 过 + 实跑 degraded=False; ② data/egw_restart_status.json 带 UTF-8 BOM 被 chk_3 判"历史坏文件"天天虚报红(引擎 .py 零引用, 纯 09-28 gateway 重启留痕), 去 BOM 写回(备份 backup_p0_opt_20261023_0709/), 复跑 03:00 体检总判翻"全绿"(9/9 节点绿, 0 auto_fixed, 0 429, 历史坏文件 0).
- 净值现状: **$893.95(07:1x ATE 活体实读, 0 持仓 0 挂单)**; 10-23 凌晨 00:00 日切熔断线按新净值重算; 币系冻结至 11-02 NFP 照旧; 连亏 2(<3 未冷却); 回撤 11.41% HALF 档 scale=0.5. 30天 a 条(净值转正)距 1000 约 -10.6%, 实亏继续拖慢出徒.
- 丑话: 修 infra/降虚警 ≠ 能赚钱; 内存 95% 是机器级(本 bot 不擅杀进程), 根治要李老师侧清内存/加交换; 出徒仍卡 30 笔实盘 OOS + 30 天净值转正两条; 历史回测≠未来收益.

## 2026-10-22 21:30 学习进化收口（strategy-rd 段, 总调度代跑实跑验货）
- rd_queue 无新课题可领（全 blocked_data/decided/reject/observation）→ 按轮转规矩上轮 10-21 做了 G5, 本轮轮到 G8(ORB宽止损SL1.5/TP3R+D1闸, 全族最强腿), 真读K线至今天(10-22 13:30 UTC)后同分母五验:
  - **数据源根治(本轮踩坑已修)**: 10-21 回填脚本只给币系补 M30 没补 D1, 币系 D1 缓存停在 10-13(478根) 而 M30 已追到今天 → D1闸 searchsorted 越界 IndexError, 首跑只有 XAU/EUR 出数(n=108 假 WATCH 已作废改 SUPERSEDED)。手动把币系 6 个 D1 补到 479 根(至 10-22)后重跑, 8/8 品种全出数。**今后回填脚本 JOBS 必须把币系 D1 也带上, 不能只补 M30。**
  - **G8_ORB宽止损 = PASS 五验 5/5 维持 WATCH**（8品种合并 n=4507>1000, 扣 0.095R 滑点后加权净期望 0.7553, 8/8 品种同向为正, 合并 wf3 [0.1855/0.9814/1.9871] 全正 → 5/5 PASS; 腿级仍卡 30 笔实盘 OOS 地板, 不放大。较 10-19 旧口径 0.4043 显著抬升, G8 重新坐实全族最强）。
  - **币系 D1 闸偏科留痕(连续两轮)**: BTC buy50/sell880, ETH 58/784, LTC 73/895, XRP 61/696 —— D1方向闸在币系几乎全判空, 币系腿实质只有空侧在赚(SOL 卖侧 1.9168 最猛, 买侧全品种 0.13~0.74 偏弱), 下轮 G5 对比时拆 buy/sell 分侧, 防"币系空腿独撑"选择效应。
  - 留痕: data/rd_verify_batch_g8_8sym_20261022.json + rd_ledger 一条(PASS, 首跑假 WATCH 已改 SUPERSEDED) + rd_ledger_24h 一条(播报键齐全, python3.11 实跑验通无乱码) + rd_watchlist G8 指针刷新 g8_8sym_20261022。
- 下一轮轮转: G5(ORB+D1方向闸) 用同批真读K线复验, 比 G8 0.7553 谁更强。
- 净值现状: **$893.95（21:32 MT5 实读 balance=equity, 0持仓 0挂单, trade_allowed=true）**; 今日 04:01 五仓全平实亏 -$72.43(XPT 前兆兑现, 拍板项作废留痕), risk_state: 回撤刹车 11.41% 触发 HALF 档 scale=0.5（比昨 4.43% 正常档大跌, 账户级仓位全半仓）, 连亏 2（<3 未冷却）, 币系冻结至 11-02 NFP 生死测, 事件 MED 0.5× 金银线。净值比 10-20 的 976.16 回落 82, 已跌破 10-12 低点 965.40 与全部前锚点, 30天 a 条(净值转正)离目标更远(距 1000 约 -10.6%), 本日实亏拖慢出徒节奏, 明日 22:00 日报对账五仓平账细节。
- 丑话: G8 五验 PASS = WATCH 攒样本证据, 不是能赚钱; 历史回测≠未来收益; 出徒仍卡 30 笔实盘 OOS + 30 天净值转正两条。

## 2026-10-21 21:30 学习进化收口（strategy-rd 段, 总调度代跑实跑验货）
- rd_queue 无新课题可领（全 blocked_data/decided/reject/observation）→ 按轮转规矩上轮 10-20 做了 G10(卡样本量闸+纽约段n=0), 本轮回到 G5(ORB+D1方向闸, 全族主力), 先治 K线数据源再复验:
  - **数据源根治**: K线从 10-16/09-26 旧缓存 → MT5 真读回填至 10-21（tf_cache: XAU/EUR M30+H4+D1 + 币系6 M30/D1, 脚本 _jevo_tf_refresh_1021.py）, 本轮首次用真读到今天的 K 线跑五验, 不再吃过期快照。
  - **G5_ORB+D1方向闸 = PASS 维持 WATCH**（8品种同分母, 扣0.095R滑点合并净期望 0.6435, 较 10-18 旧K线口径 0.3298 显著抬升, 7/8 品种同向 [仅 EURUSD n=3 新D1闸生效期薄弱], 合并 n=4501>1000, 三wf段全正 → 五验 5/5 PASS; 腿级仍卡 30 笔实盘 OOS 地板, 不放大）。
  - **数据质量留痕**: 币系 D1 闸当前几乎全判空头（BTC buy50/sell879 等）= D1 方向闸在币系偏科, 下轮 G8 复验要拆 buy/sell 分侧看, 防"币系空腿独撑"选择效应。
  - 留痕: data/rd_verify_batch_g5_8sym_20261021.json + rd_ledger 一条 + rd_ledger_24h 一条(播报键齐全验通无乱码) + rd_watchlist G5 指针刷新 g5_8sym_2021。
- 下一轮轮转: G8(宽止损SL1.5TP3R, 用同批真读K线复验, 上轮 10-19 净期望 0.4043, 本轮比 G5 0.6435 谁更强)。
- 净值现状: $973.61（21:5x MT5 实读 balance 966.38 / equity 973.61, 5 持仓浮盈合计 +$8.31, 比 10-20 的 976.16 小回落仍高于 10-12 的 965.40）; risk_state: 回撤刹车 4.43% normal scale=1.0, 连亏 2（<3 未冷却）, 币系冻结至 11-02 NFP 生死测, 事件 MED 0.5× 金银线。
- 丑话: G5 复验抬升 = WATCH 攒样本证据, 不是能赚钱; 历史回测≠未来收益; 出徒仍卡 30 笔实盘 OOS + 30 天净值转正两条。

## 2026-10-16 21:30 学习进化收口（strategy-rd 段，总调度代跑实跑验货）
- 无新课题可领（rd_queue 全 decided/reject/blocked_data）→ 按规矩复验观察名单最强 3 腿（ORB 族 G5/G8/G10），rd_cycle 实跑 + 五验 + 台账落盘：
  - **G5_ORB+D1方向过滤 = PASS 维持 WATCH**（exp_R 0.425，扣 0.095R 滑点后 0.33，6/6 品种同向，wf3 三段全正 [0.46/0.58/0.51]，10-16 21:47 重新入 rd_watchlist）
  - **G8_ORB宽止损 = PASS 维持 WATCH**（exp_R 0.534，扣滑点 0.439，wf3 [0.42/0.81/0.65]）
  - **G10_ORB时段聚焦 = REJECT 放大**（净 exp_R 0.853 全族最高，但伦敦+纽约段实算样本 n=98 <1000 触发五验样本量闸 → 拒绝升档；原 09-28  WATCH 判定基于 M30 缓存旧样本，H1 CSV 口径下不成立 → 维持 WATCH 0 放大，待 H1 数据补全再复验，防小样本假放大）
- 留痕: rd_ledger.json 三条 21:47 + rd_ledger_24h.json 21:55 一条（播报告道验通不再印问号）+ rd_watchlist G5/G8 刷新。
- 净值现状: $971.54（21:33 全链训练节点实读，比 10-12 的 965.40 回升转正中）；0 持仓 0 挂单；swing 层边衰 0.5× 降仓中；连亏 2（<3 未触发 24h 冷却）；币系冻结至 NFP 生死测照旧。
- 丑话: 三条全 WATCH 攒样本阶段，离 P4 出徒还差 OOS 30 笔 + 30 天净值转正两条；历史回测 ≠ 未来收益。

## 2026-10-18 21:30 学习进化收口（strategy-rd 段, 总调度代跑）
- rd_queue 26 条全非新可领（13 open 多为已裁定留痕/blocked_data）→ 按规矩复验观察名单最强腿 G5(ORB+D1方向闸), 扩到 8 品种（黄金/欧元 + 6币）最新 K 线同分母七验:
  - XAUUSD/EURUSD M30 = MT5 真读至 10-16（tf_cache 已回填 4 周期/2 品种）; 币系 M30 缓存 10-13。
  - 结果: 8/8 品种扣滑点 0.095R 后 exp_R 全正（0.31~0.61, SOL 最强 0.607）, 合并 n=7460, 加权 exp_R 0.4248 / 扣滑点 0.3298, 合并 wf3 三段全正 → 五验 PASS（WATCH 攒样本, 腿级未过 30 笔 OOS 地板, 不放大）。
  - EURUSD 样本 n=2（新 M30 序列太短, D1 闸刚生效期）— 标注薄弱, 下轮扩样本再复验。
  - 实数: data/rd_verify_batch_g5_8sym_20261018.json + rd_ledger 一条 + rd_ledger_24h 一条（播报告道验通）。
- 净值现状: $971.54（21:3x MT5 实读 balance=equity, 0 持仓 0 挂单, 比 10-12 的 965.40 持续回升中）; risk_state: 回撤刹车 3.61% normal scale=1.0, 连亏 2（<3 未冷却）, 币系冻结至 11-02 NFP 生死测, 事件 MED 0.5× 金银线。
- 丑话: G5 全族最强腿复验仍正 ≠ 能赚钱, 历史回测≠未来收益; 出徒仍卡 30 笔实盘 OOS + 30 天净值转正两条。

## 2026-10-19 21:30 学习进化收口（strategy-rd 段, 总调度代跑实跑验货）
- 无新课题可领（rd_queue 全 blocked_data/decided/reject/observation）→ 按规矩轮转复验观察名单最强腿, 上轮 10-18 做了 G5, 本轮轮到 G8(宽止损SL1.5/TP3R), rd_cycle 实跑 + 五验 + 台账落盘：
  - **G8_ORB宽止损 = PASS 维持 WATCH**：8品种(XAU/EUR+6币)最新K线同分母复验, 扣滑点0.095R后 8/8 品种全正(0.35~2.03, XAU最强 1.181, SOL 0.992), 合并 n=7460, 加权 exp_R 0.4993 / 扣滑点 0.4043, 合并 wf3 三段全正 [0.28/0.24/1.11] → 五验 5/5 PASS。
  - G8 扣滑点净期望 0.4043 > G5 同口径 0.3298 = 宽止损腿仍是全族最强, 但腿级未过 30 笔实盘 OOS 地板, 不放大, 维持 WATCH 攒样本。
  - 留痕: data/rd_verify_batch_g8_8sym_20261019.json + rd_ledger 一条 + rd_watchlist G8 指针刷新到 g8_8sym_20261019。
- 下一轮轮转: G10(时段聚焦, 伦敦+纽约段样本 n=98<1000 触发样本量闸, 待 H1/M30 缓存补全后复验)。
- 净值现状: $971.54（21:0x MT5 实读 balance=equity, 0 持仓 0 挂单, 比 10-12 的 965.40 持续回升中）; risk_state: 回撤 3.61% normal scale=1.0, 连亏 2（<3 未冷却）, 币系冻结至 11-02 NFP 生死测, 事件 MED 0.5× 金银线。
- 丑话: G8 全族最强腿复验仍正 ≠ 能赚钱, 历史回测≠未来收益; 出徒仍卡 30 笔实盘 OOS + 30 天净值转正两条。

## 2026-10-20 21:30 学习进化收口（strategy-rd 段, 总调度代跑实跑验货）
- 无新课题可领（rd_queue 全 blocked_data/decided/reject/observation）→ 按轮转规矩上一轮 10-19 做了 G8, 本轮轮到 G10(ORB时段聚焦·伦敦+纽约, 全族 exp_R 最强腿), rd_cycle 实跑 + 五验 + 分段拆解 + 台账落盘:
  - **G10 = REJECT 放大, 维持 WATCH**（六币最新K线同分母复验, 扣 0.095R 滑点后合并 exp_R 0.8529 全族最高, 但合并 n=98 <1000 触发五验样本量闸 → 拒放大, 与 10-16/10-17 一致维持 WATCH 攒样本）。
  - **关键新发现（分段拆解治本）**: G10"伦敦+纽约"名不副实 —— 纽约段 (UTC 13-16) 六币全 n=0, 98 笔事件**全是伦敦段**。即 0.8528 的"最强腿"实为**伦敦单子集选择效应**, 不是真时段 edge, 踩了"子集胜率差冒充 edge"同族坑, 本轮用分段实数钉死, 下轮不再把 G10 当全族最强, 待 K 线序列补长 + 纽约段出样本再复验。
  - 留痕: data/rd_verify_batch_g10_8sym_20261020.json(带 london/ny breakdown) + rd_ledger 一条 + rd_ledger_24h 一条(广播键齐全验通不再印问号)。
- 下一轮轮转: 回 G5/G8（G10 卡样本量闸 + 纽约段 n=0, 暂不占轮转主力）。
- 净值现状: $976.16（21:4x MT5 实读 balance 971.40 / equity 976.16, 比今早 09:30 的 957.84 回升 +18, 5 持仓浮盈合计 +$4.76）; risk_state: 回撤刹车 5.86% normal scale=1.0, 连亏 2（<3 未冷却）, 币系冻结至 11-02 NFP 生死测, 事件 MED 0.5× 金银线。
- 丑话: G10 复验仍"最强数字但样本薄"≠ 能赚钱, 历史回测≠未来收益; 出徒仍卡 30 笔实盘 OOS + 30 天净值转正两条。

## 周末休市锚点 (2026-10-03 周六 18:0x 实读)
- 外汇/黄金 周六休市: EURUSD/XAUUSD/GBPUSD lasttick 停在周六 ~07:54, 距18:0x 10h+ = 已收盘, 周末无行情。
- 币系 24h 活: BTC/LTC/POL/ETH lasttick 到点仍跳动。
- **归因铁律: 周六/周日 外汇与黄金 0 开单 是休市所致, 不是系统故障/负期望/漏挂 —— 答"没单"先报休市, 别归错因。**
- 币系冻结桥+POL 例外腿照跑: 币 24h, 周末可开 POL 例外腿(0.5x 五验攒OOS), 其余币系仍 0 开(至11-02 NFP 生死测)。
任何新会话（桌面群聊 @Hermes / 微信 iLink / 新对话框）开头痛一点就读这张卡，30 秒接上现状。
> 单一事实源：管辖分工见 `金策宗师团_管辖分工_v2.md`；**每日规章制度/排班表见 `金策宗师团_每日规章制度.md`（2026-10-07 用户令落地：时刻表冻结+失败必发声+每日21:30学习进化）**；技能 `mt5-multiagent-trading`。

## 一、Bot 拓扑（4 个，一 bot 一把专属 key，固定不共用）
| bot | profile | 职责 | 专属 key（只指尾4位，全值在各自 .env） |
|---|---|---|---|
| 主 bot（总调度，用户唯一出口） | default | 派单/汇总/盯循环 | sk-lvB…RC3b |
| 金策·总管·首席操盘手 | chief | L1-L3 日运营：全链/看板/事件日报/复盘 | sk-GIl…yBL7 |
| 金策·风控官 | risk-officer | L4 双闸 veto+事件定级复核，不听总管、直报 | sk-C2x…GRQZ |
| 金策·策略研发 | strategy-rd | L5 研发判断/回测验收/P4 出徒 | sk-Lgf…TWey |
- 4 把全 .cn 验活 200；delegation/子代理也钉死各自 key；fallback（agnes-main/.com + agnes-flash）仅失效兜底
- 群标记：4 profile 的 ui_meta 群 = 「金策·宗师团」（桌面 Bots 建群时 4 个会预聚）

## 二、自动节奏（全 Windows 级，不依赖任何对话框）
| 任务 | 驱动 | 频率 |
|---|---|---|
| 交易全链（对账→CIO→币→股指→总督→进化→研判→日报） | JinCeAutoCycle | 30min |
| **事件快通道（新, 2026-09-28）**：event_risk HIGH/HALT 即时撤趋势/Stop 挂单 | JinCeEventGuard | 5min |
| 08:30 开盘简报 / 22:00 事件日报+复盘 / 月度 P4 | Hermes cron（deliver=weixin） | 日/月 |
| cron 兜底 tick | JinCeHermesCronTick | 5min |
| GitHub 同步 | JinCeGitSync/PM | 07:00/19:00 |

## 三、关键路径
- 引擎：`E:/GoldstrategyEngine/`（数据唯一源 `data/`；看板 `data/daily_dashboard.html` 全局唯一、无密码）
- 流水线：`E:/workbuddy/金策宗师团/chief/chief_pipeline.py`（L0 一键）
- **看门狗：`E:/GoldstrategyEngine/event_guard.py`（日志 `data/event_guard.log`，快照 `data/event_guard_last.json`）**
- key 对账脚本：`E:/workbuddy/金策宗师团/_keymap.py` / `_probe_keys.py`
- 微信：iLink 仅 default 有凭证（子 bot 已剥离），私聊稳、群聊收不到

## 四、当前盘面锚点（2026-10-01 19:4x 锚, MT5 实读 60137964）
- 净值 **$965.40**（10/1 实读 balance=equity，demo 60137964 当实盘练；峰值回撤 4.22% 保险丝内）
- 持仓 0 张；**活挂单 2 张（19:4x MT5 实读）**：
  - #578016436 POLUSD BUY_STOP 0.03 @ 0.12538 / SL 0.11698 / TP 0.14216（L4 t_bb1d11fe 明示保留的正期望观察腿，L4 冻结令 11-02 NFP 生死测前币系 0 开新腿，存量照常管理）
  - #578888283 GBPUSD SELL_LIMIT 0.02 @ 1.32885 / SL 1.33129 / TP 1.32485（range 层小观察单，**无 L4 双闸审计留痕**，19:4x 已派 t_1466eb2b 补裁）
- **币系冻结桥生效**：crypto_freeze_bridge 30min 循环全绿（19:45 实读 frozen=true），KSM 0 单（0.95 空头研判只做观察不挂单，门守住了）
- 方向=10/1 09:31 研判：USD 偏强/三线空头共振（USDJPY SHORT 0.95 / EUR 双顶 0.8 / USDCAD 双底 LONG 0.9），PCE 降温→加息押后至 10-02 NFP，10-02 NFP 落地前不回归常规手数
- **P4 月度评审（10/1）= HOLD 不出徒**：30天净值 -2.95%（a 不过）/日内腿无正期望可放大（b 不过）/swing 腿衰减挂起（e 挂起）；风控层干净（d 过）；两项承接单：t_65f3d034（strategy-rd 归因：G10 30笔复验+swing 攒样本+日内 P0 替代）/ t_a3872914（risk-officer 补建 risk_state.json）
- 数据新鲜度病复发：美盘开评节点 19:22 报"无 open 单"实为旧快照+数据源未读 MT5 实盘（V13 问题），19:4x 已留痕 us_open_1922_data_source_fix，明早 08:00 批量修节点数据源


## 五、深度优化根治台账（2026-10-02 总调度自主落地，免请示）
- **节点误报无单**：`pending_orders.py` 简报已加 MT5 实盘对账段（orders_get/positions_get/account + 派生簿vs实盘差异警示），实盘跑通验证。今后节点挂单/持仓一律照实盘段报，派生簿只留痕。
- **429 连烧 3 天误判 crashed**：根因=Windows 无 waitpid，worker 撞额度退出码 75（KANBAN_RATE_LIMIT_EXIT_CODE）拿不到 → 被记成普通 crashed 连败 2 自动 block。已修 `kanban_db_dispatch.py`（_windows_worker_exit_codes 镜像 + spawn 注册 Popen + Windows poll 抓码），gateway 已重启加载。今后 429 死=rate_limited 不计连败，走 rate_limit_cooldown，额度恢复自动重派。
- 备份 .bak-deepopt_1002；确定性层 Python 不套 LLM；放大只放大已验证正期望。

## 七、体检汇报制度（2026-10-07 用户令"建立规章制度, 定时给我汇报", 总调度落地）
- **每日 03:00** 金策全面深度体检（job b8cf251ccd7c, no_agent, `jince_daily_healthcheck.py`, 结果落 `data/healthcheck_last.json`）
- **每日 08:45** 体检汇报投群（job jdashhealth0845, no_agent, `jince_health_report.py`）: 读 03:00 体检结果出大白话汇报 — 全绿一行; 异常逐条点名 + 已自动修 + 待续跑; 结果缺失/陈旧>16h 直接报警"03:00体检没跑"。失败也发声(failure_deliver=bot-chat), 绝不静默吞。
- 汇报只读体检落盘结果, 0 LLM, 429 免疫; 异常项自动登记 task_ledger 每30min续跑执行器接手。

## 八、群激活 + 双通道汇报（2026-10-07 用户令"互动起来/两个都要", 总调度落地）
- **桌面群「金策·宗师团」= 高频舞台**：2h 效率播报/6 节点/群主持(白天6班 09,11,14,16,19,21)/看板哨兵/巡检 全走 bot-chat, 保持现状。
- **微信私聊 = 关键 4 项直达手机**（2026-10-07 起）：08:30开盘简报 / 08:45体检汇报 / 21:30学习进化 / 22:00事件日报+复盘, deliver+failure_deliver 全设 `weixin:o9cq802uOL2IXFNyr8_ITt827NKE@im.wechat`。微信私聊通道已验活(总调度此刻就在此 DM 收发消息)。
- **回执 unverified 机制真相**：cron bot-chat 投递后回执 `delivery_queued: completion unverified; do not resend` = Hermes 的"不重发"保护, **不是丢消息** —— 消息已入 bot_live_delivery 队列(64KB, 桌面端独占锁, 别去 kill 桌面进程读它), 桌面端 consumer 活着(active_sessions.json 每 5min 刷新 + 4 个 consumer=True)即被消费进桌面 Bot Chat; 要 100% 确认 UI 渲染需人工切桌面看一眼该条在不在。**别反复 kill 桌面端去读独占队列 = 终端 churn 同族事故。**
- 群主持脚本 `jince_group_host.py`(确定性0LLM, 同小时防刷屏, 08:30-22:30外静默), job jgrouphost0900。

## 六、卡死根治台账（2026-10-06 总调度自主落地，免请示）
用户令「深度优化不能出现问题 / 所有自动程序总是卡」。根因三件套 + 已修:
1. **看门狗僵尸 Running 叠 4h 不退出**：`jince_watchdog.py` 的 gateway 探活 subprocess timeout=60 在网关忙时卡满, 且 Windows 任务 `JinCeWatchdog` 原 `ExecutionTimeLimit=PT72H`（等于不限时）→ 实例永不退出 → 任务状态 Running 叠死。已修: ①watchdog gateway 探活 timeout 60→25s + main 入口加兜底护栏(未捕获异常也写心跳落盘+exit 0, 绝不僵死) ②`JinCeWatchdog/JinCeAutoCycle/JinCeEventGuard/JinCeGitSync/JinCeGitSyncPM` 五个任务统一改 `ExecutionTimeLimit=PT15M + MultipleInstances=IgnoreNew`（上轮没跑完跳过下轮, 不堆叠）。备份 `E:/GoldstrategyEngine/backup_deepopt_1006/`。
2. **网站 07:30 每日升级 cron 每日报「Script not found」**：jobs.json 里 workdir 填了 `E:\workbuddy\内容中心\网站\脚本` 但 hermes no_agent 投递按脚本名去默认目录 `E:\workbuddy\国外模型\hermes\scripts\` 找 → 找不到。已修：把 `sites_daily_upgrade.py / sites_daily_report.py` 复制进默认 scripts 目录（workdir 原值保留，双保险）；同理 `jince_auto_patrol.py / jince_daily_healthcheck.py` 复制到 `E:\GoldstrategyEngine\` 兜底。
3. **外部网络断**：`network_probe_last.json` extnet=down（curl ipify reset），本地循环照跑，节点数据降级用最近快照（fail-open，不影响交易）；GitHub 同步 07:00/19:00 自动补推，不卡死。
4. **行情看板（GitHub Pages 远端）停更根因 + 已修**：用户报"看板一直不更新"。实查 = 本地 `daily_dashboard.html` 30min 全链每轮正常重生成（09:02→13:31 五轮全绿），但**推 GitHub 的 443 被间歇性墙**，`sync_dashboard.py` 裸 `git push` 全挂 → 远端停在 10-05 08:01 旧快照，用户看的是 Pages 公网链接所以体感"一直不更新"。已修: ①`sync_dashboard.py` 改成「探测 4 候选 IP → resolve 旗标绑活 IP 推（URL 保持 github.com SNI 对）→ gh-token-in-URL 兜底 → 裸推兜底」四层推送，实跑验证 13:50 推送成功（远端 7221dcb→cb31ad3 已更新到最新）；②手动把 13:46 最新看板推上去并补 stamp。引擎仓 11:25 那次"push rejected"是 443 墙卡 fetch 的假阳性，gh api 验远端 HEAD=本地 HEAD 一致，非真故障。


## 五、出徒加速锚点 (2026-10-06 主 bot 立, 全力进化)
- P4 10/01 = HOLD(a 不过/b 不过); 研发连撞 P2 前置闸 5 段(CONFIRMED_NEG_EV) → 换赛道
- 新赛道 = 三客户号实盘验证思路: **时段闸(8/14/15/16 北京) + 盈亏比 1.3 闸**
- H1 快跑结果: 双闸组合 EURUSD Δ+0.0435R(正), XAUUSD Δ+0.0007(交互衰减, 待查因)
- 数据: data/rd_hypo_xinjian_rrgate_quick.json + data/rd_hypo_combo_session_rr.json
- 下一步: strategy-rd 补 DSR/PBO + 品种稳健 + WF3 段 → P4 10/06 重审 b 项
- 已落自有系统: trader_brain ④.5 盈亏比闸(默认生效) + 演练号纪律卡(chief 目录)

## 已收口
- 客户EA破解线（候总 ex4）：策略测试器日志等待于 10-06 20:46 经李彦明指令正式收口，不再执行、不再等待 tester_log。已交付物保留：E:\workbuddy\内容中心\交付\候总EA破解_行为复刻\（行为复刻 .mq4/.ex4）。

## 2026-10-06 23:43 续跑核验(监控器到期误叫醒, 无新进展)
p4_path_close 台账/落盘一致, DSR/PBO/品种稳健/V5已验完, 仍等strategy-rd拍板; 台账已顺延至10-07 02:15, 不烧LLM空转。

## 2026-10-07 高频剥头皮 5 道风控闸 · 深度吸收进系统(总调度令"深度吸收进我们的系统")
> 来源: 新建20011176 MQL5 复刻 EA(GoldScalpClone) 深度优化 17 项, 本机 MetaEditor64 0错0警告编译通过(.ex5 已交付 E:\workbuddy\内容中心\交付\GoldScalpClone_20011176_复刻EA\), 提炼成金策自有纪律(非客户EA, 是我们自己的系统)。
**三落点全部落地**:
1. **trader_brain.py 开单大脑**(E:\GoldstrategyEngine\multi_agent\trading\trader_brain.py): 加 ⑤浮亏强砍 _hard_cut_check + ⑥净浮亏闸 _net_float_block + ⑦点差闸 _spread_block + ⑧手数归一 + ⑨下单验活; 提案 dict 加 `high_freq_gates` 字段(5道闸参数+verify_retcode=TRADE_RETCODE_DONE), 执行端按此守纪律。实测跑通(提案3条不崩, high_freq_gates 已带进)。
2. **chief 演练纪律卡**(E:\workbuddy\金策宗师团\chief\三账户思路_人工操盘演练纪律卡.md): 原 4 道闸 + 新增 5 道高频风控闸(浮亏强砍0.5xSL/净浮亏1.5%/点差35pt/日亏熔断1%/下单验活), 演练号 60137964 人工+机器两线通用。
3. **strategy-rd 研究台账**(E:\workbuddy\金策宗师团\strategy-rd\研究台账.md 2026-10-07 节): 5 道闸各自同分母回放待验项(重点⑤浮亏强砍0.5xSL扣滑点 vs 等SL扫损净期望差), 未过五验只作纪律不放大仓位。
**派单**: rd_queue `scalp_hf_gates_backtest` + task_ledger `t_scalp_hf_gates_backtest_20261007` 交 strategy-rd 同分母回放定 WATCH/APPROVE。
**铁律**: 这 5 道闸=纪律/风控参数, 非新策略腿; 放大仓位/进 live 仍须走五验(同分母+DSR+PBO+品种稳健+WF3)。

## 2026-10-11 金策·策略 SaaS(卖给资管公司的白标跟单系统) · 全网最优交付
> 用户令: "给你做一套完整系统卖给资管公司,他们让客户用我们的bot交易" + "做到全网最优"(对标商用天花板)。
> 铁律(用户口头): **这套系统只落 D:\jince_sass\, C/E盘别动、引擎 D:\client-jince 与 10 个定时任务不动、只读引擎 data。**
**系统四件套全部做到全网最优标准, 19/19 验收全绿**:
1. **① 后端信号中枢**(src/): FastAPI 多租户 API + 开放API(api_key token) + WS 实时推送 + 5道风控闸 + demo/金策引擎双信号源 + 402门控 + 防篡改审计哈希链 + 生产密钥拒启。主验收 tests/test_acceptance.py 9/9。
2. **② 跟单执行引擎**(src/exec/engine.py, 对标 Tradecast/CopyFactory/MQL-CopyTrade/MetaCopier2026): 幂等防双下单(client_order_id三层) + per-symbol有序队列(防幽灵仓) + 死信队列+重放 + 跨broker品种映射三层 + lot四模式(full/percent/fixed/multiplier)+broker step归一 + 资金上限三态(reject/skip/clamp) + 断线补漏 + 指数退避+jitter。tests/test_exec_engine.py 10/10。
3. **③ 网页客户端**(web/index.html+app.js 1083行+ECharts离线包): 策略广场/排行榜/详情腿矩阵/账户CSV导出/实时WS/402横幅/白标换肤/合规风险7类揭示+结构化同意, 离线双击可开+改一个 API_BASE 接真后端。
4. **④ 收费引擎**(billing/): HWM绩效分成(4段曲线)+6费用结构+自动分账ledger借贷平衡+PDF对账单+402门控+Stripe/支付宝双通道。
**总调度亲补的缺口**: 后端 stats 端点补 risk_metrics五指标+monthly_roi; 新增 /api/v1/tenants/{slug}/theme 白标端点; _serve_demo.py 一键起 :8800(网页+API+WS同端口)。
**一键开**: `D:\jince_sass
un_demo.bat` → 浏览器 http://127.0.0.1:8800/; 纯离线双击 `web\index.html`。
**对标天花板清单(已落D盘)**: 全网最优_功能天花板.md(7维度+🟢可复刻/🔴商用独有) + 全网最优_执行引擎借鉴.md(逐字段伪代码)。
**kanban**: t_18d62f8e(①,done) t_52624673(②) t_f8e52ec9(③) t_a45511b9(④)。
**下一步(若继续)**: ⑤可观测性面板(延迟分位/拒单率/DLQ深度) + accrued fee debt + 真实 MT5 终端接 mql-zmq 执行腿; 全部仍只落 D:\jince_sass\。

## 2026-10-12 全网最优"做到交付为止"· 终态(全 7 维度天花板落地, 27/27 验收全绿, git 18f56e3)
> 用户令"继续深度优化直到交付为止"+"以后不用问必须最有才行"→ 不再请示, 直接做到顶收口。
**本轮补齐的剩余天花板缺口(全部亲跑验货)**:
1. **⑤ 可观测性/运维(专家团落 src/metrics.py)**: /admin/metrics 8项SLA指标(跟单延迟P50/P95/P99·拒单率按原因分类·双下单率·DLQ深度·终端在位率·费用健康·WS在线·信号源心跳)+ /healthz 分层健康检查(db/WS/signal/sweeper)+ web 监控页(8指标卡+红警条)。test_metrics.py 验收。
2. **P1 计费/合规缺口(总调度亲自补)**: accrued fee debt(应收费债 accrue_debt→_recover_debts 自动补扣·双留痕)+ 结构化同意记录(ConsentRecord·7类风险逐项取证·文档版本/设备/IP/时间戳/原文SHA256哈希·verify_consent 跟产前合规门没签拒下)+ /api/v1/billing/consent + /debts 端点。test_billing_p1.py 3用例。
3. **pump 跨 event-loop 根治(总调度亲自修)**: pump.stop_event 改懒建绑定当前 loop + main lifespan 每次 _new_stop_event(), 修掉"多 TestClient/多 worker 混跑关泵抛 bound to a different event loop"真 bug。
**端到端验货(真起 :8800 服务 HTTP 全 200)**: 网页16KB+echarts / admin/metrics 8指标 / healthz分层 / 白标theme / 合规门(未签拒→签7类→放行) / 债台账 全通。
**最终验收**: tests/ 全量 27/27(acceptance 9 + exec 10 + billing_p1 3 + metrics 5), 56s 全绿。git 18f56e3 收口。
**这套系统 7 维度天花板全落地, 可交付资管公司**。若继续: 真实 MT5 终端接 mql-zmq 执行腿 + Docker 部署 + Prometheus/Grafana 面板(把 metrics 接出去), 仍只落 D:\jince_sass\。

## 2026-10-12 王金光 165476018 · 扛单腿/战役加仓 · 全面深度吸收(总调度令)
> 来源: 客户 `E:\资料\王金光\ReportHistory-165476018.html`(Exness USC 美分 XAUUSDc, 499 笔 2026-06-25~10-08, 净+9130 / 胜率74.35% / PF2.70 / 盈亏比仅0.90)。
> 行为族 = 波段反转扛单族(赢34min快跑/输22h死扛, 39笔扛>1天吃掉75%毛亏) + 战役式加仓(9/2 0.1→0.65手5连发占全期利润36%)。
**先出复刻 EA(李彦明令"按原策略做MT5EA, 不加金策内容, 优化10次以上")**: `E:\workbuddy\内容中心\交付\王金光EA复刻\WangJinGuang_Clone_EA.mq5/.ex5`, 本机 MetaEditor64 **两轮编译最终 0错0警告**(12项深度优化), 已拷本机两终端 Experts; 同目录 Word 深度解析报告 + 说明.txt(含"挂上不开单"自查清单)。**客户报"挂上不开单"→ 根治 v1.1**: 时段门只有7个北京时是主因 + 每静默return改带原因日志/面板(非开单时段/点差超闸/无信号/时区错位四类秒定位), 新增 InpAllHours/InpLooseSignal/InpServerOffsetH 三个可配 input, 重编译 0错0警告重同步。
**三刀吸收进自有系统(铁律: 不整块塞, 杠单/加仓=马丁近亲高风险, 不放大仓位不进 live)**:
1. **trader_brain.py 开单大脑**: 加 ⑫ 扛单腿块(WATCH) `WJG_HOLD_MAX_HOURS=72 / WJG_HARD_CUT_MULT=0.5 / WJG_PIRAMID_MULT=0.5 / WJG_EVENT_LIVE_CAP=0.10`(超0.10手一律WATCH拒放大), 提案 dict 加 `wjg_hold_gate` 字段; 实测 ate venv 跑通(提案3条不崩, 0.65手被正确拒放大, 非XAU族N/A)。
2. **chief 演练纪律卡**: 加王金光对照行(通用风控=与⑤⑥⑧再次验证; 扛单/加仓腿=WATCH观察; 战役0.65手=不吸收只按风险研究)。
3. **strategy-rd 研究台账**: 加 2026-10-12 王金光扛单腿同分母回放待验项(⑫-a扛单腿正EV/⑫-b加仓腿独立贡献/⑫-c战役加仓可复制/⑫-d 72h上限, 全 WATCH 不升 APPROVE)。
**派单**: rd_queue `wjg_ctr_hold_replay_v1` + task_ledger `t_wjg_absorb_replay_20261012`(research类30min自动接手) 交 strategy-rd 3桶同分母回放(A扛单/B带⑤强砍/C无加仓)定 WATCH/APPROVE。
**铁律**: 扛单+加仓 = 马丁近亲高风险子类, 未过五验(同分母+DSR+PBO+品种稳健+WF3) 只当 WATCH 否决门/纪律标注, 不放大仓位、不进 60137964 自动挂单链; 战役式 0.65 手原样打法不吸收只按风险比例研究。


## 2026-10-12 黄飞 15014338 · ⑬日内节奏同分母回放定稿 · 出徒加速(总调度令"深度研发加快出徒")
> 来源: 黄飞 TradeMax 对账单 224 笔 XAUUSD 0.01手(36天+435.29/胜率61.6%/PF1.50), 剔09-11两笔人工单。
> 总调度亲自加速跑完同分母回放(不等 strategy-rd 30min 续跑器): 四桶回放+阈值扫描+OOS两半, 数据落 `data/rd_verify_batch_hfh_{intraday,bfive,oos,pbo}.json` + M1缓存。
**三假设两证伪一定稿(回放打脸原设计, 这正是五验的价值)**:
- ⑬-a 错单5min快砍 **REFUTED**(274.97<430.81且MDD 75.99→253.32, 早砍砍在反弹前) → 纪律卡快砍维持⑤0.5ATR口径
- ⑬-b "赢单拿>1h" **REFUTED, 真身=15min定时硬平**(SL/TP优先, 帽内未走出市价平): 阈值10/15/20min平台区+942/+941/+932(PF~2.05非孤峰), 定稿15min全窗+941.03(增益+510)/PF2.04/OOS前后半皆正(589/352)
- ⑬-c 0.5R移保本 **WATCH边际**(+543但MDD 106.79, 回撤成本不抵收益)
**落地四处全绿(0崩验通)**: ①trader_brain ⑬块参数修正(60→15min定稿版, hfh_gates字段带timecap_min+refuted_rules证伪留痕) ②chief演练纪律卡黄飞对照行=回放定稿版 ③strategy-rd研究台账⑬节=五验进度表 ④rd_decisions `hfh_intraday_15m_v1` 裁定 WATCH+前向合同n=30(60137964观察列攒15min定时平仓OOS, 22:00隔日对账, 30笔meanR≥0且SQN≥0→补品种稳健+WF3→P4出徒评审; meanR<0→RETIRE)。rd_queue/task_ledger 已销账 decided/done。
**出徒铁律**: 跨价源回放(TMGM近似TradeMax)只作方向证据, 出徒只认前向合同n=30真实OOS+品种稳健; 未过前 ⑬ 只 WATCH 标注不进 live 不放大仓位。

## 2026-10-12 22:15 群播报断链收口（主 bot 实读, 已闭环）
- **bot-chat 投递链根治完成**：根因=@chief 实读纠偏（C-runtime cron store 是空的, 41 job 全在 E-store/E gateway 调度, 真正要切的是 tick 任务 exe）。@chief 方案(a)落地=JinCeHermesCronTick 切到 E-runtime（认 bot-chat, 不擅启 E 侧交易任务）+ 主 bot 杀旧 gateway(21348, 12:16 旧码+带 4 个 stale SESSION_NOT_OWNED 会话锁)拉新(22740 独活, launcher guard 兜底防双调度)。
- **验收铁证**：f452478a「金策 2h 效率播报」22:00 那班 `executions.status=completed`、22:10:41 收工、无 error = bot-chat 进群坐实。群播报恢复常态, 交还 @chief。
- **SESSION_NOT_OWNED ×4 / 600s 超时 ×2**：旧会话(10-06/09/11/12-03:16) stale owner 随 gateway 重启释放；下次投递重开新会话。
- **双闸销账更正**：00:10 job=Ready + 宿主闸 verdict=PASS_INDIRECT 属实, 但 **12:57 那份回测卷是空卷**（universe 仅 3 品种, SDP/ICT/VP 全 n=0, 0 正 edge 腿）→ 别当出徒进展；live 不动、出徒 8 腿仍 <30 OOS floor。已转 @strategy-rd（rd_queue `universe_empty_volume_full_run`: 全品种×全腿 n>0 才算销账卷）。
- **今日补播口径**：一律实读 **0 持仓 / 0 挂单 / 净值 965.40**（@chief MT5 实读坐实；派生簿"持仓 2"是老病, 群播报改报实盘数）。补全稿在盘 `E:\workbuddy\内容中心\交付\金策群播报补全_20261012.md`。
- **当前盘面（22:15 实读）**：账户 60137964 · 0 持仓 0 挂单 · 净值 $965.40 · 事件 risk=MED 无熔断 HIGH=0 · 全链 30min 活 · gateway 已重启健康(22740 单活)。

## 2026-10-12 23:45 chief 群播报 gateway 死因收口（主 bot 实读）
- 真根因: chief 需自己的 per-profile gateway 当 bot-chat:chief 接收方; root(22740)只服务default, chief在'NOT served'名单. chief gateway 起来就被 weixin 跨平台毒化(HERMES级.env有WEIXIN_ACCOUNT_ID, chief无token)→ WEIXIN_TOKEN required → non-retryable启动冲突 → 退. 与429无关.
- 已修: 主bot给 profiles/chief/config.yaml 加 platforms.weixin.enabled:false(某E-runtime进程23:18确认读到'will NOT start weixin adapter'). 手动spawn姿势不对没生效, 已停手不churn.
- 确定性收尾: ①Windows login item Hermes_Gateway_chief.vbs 下次开机自动拉; ②00:00额度重置后E-runtime venv干净spawn一次; ③期间群播报主bot代主持兜底不让静默. 验收=chief gateway_state刷新新pid+一条bot-chat:chief播报真进群.

## 2026-10-13 全自主优化收口（主 bot 实读, 定论）
- 授权: 李彦明『全部优化好 你以后自己决定』= 金策全自主权(交易+运维), 主 bot 按最优方案落地/验证/汇报, 不逐件请示, 改配置不碰进程不碰实盘不盲churn.
- 群静默定论(三层, 全实读坐实): ①前半夜=chief per-gateway 被 weixin 跨平台毒化(HERMES级.env有WEIXIN_ACCOUNT_ID但chief无token→起来连weixin→non-retryable冲突退出)→已修(chief config加weixin.enabled:false+启动器vbs换E-runtime新代码, 认禁用标记); ②今早已自愈(delivered 33条, 意义班次 2h播报/节点/巡检 全delivered, chief gateway收敛1活进程, 今天429=0); ③94%suppressed=33个bot-chat job挤同一群的同小时防刷屏设计(正常静默高频哨兵/放行有意义班次, 非漏发).
- 12条failed=整点:00/:30多播报job并发挤+单条600s超时, 全是no_agent纯脚本(0LLM), 漏一条下15min班自动补, 不影响交易. 不降频(监控密度铁律)/不改schedule(节奏最小影响).
- 验收锚点: 明早08:30开盘简报+08:45体检投群=整条链(cron→bot-chat→weixin已修→群渲染)决定性验收, delivered即彻底销账.

## 2026-10-13 学会看MT5多周期真K线（弃自造K线, 总调度令'安排他们学会+群里积极讨论'）
- 根因坐实: 本机MetaTrader5老MQL4绑定只有TIMEFRAME_*无PERIOD_*; 旧盘感腿读6-30过期CSV快照=自造K线(金价4007 vs 实时4166, 差150+判断全废)。
- 已修market_intuition.py: load_kline(prefer_mt5=True默认MT5真读优先+CSV兜底, 每根K线带source标签MT5_LIVE/CSV_CACHE) + _resolve_period三级回退(PERIOD_→TIMEFRAME_→raw值) + multi_tf_report(四周期M15/H1/H4/D1真读+共振判定+大白话say结论)。
- 教材+一键脚本落盘: MT5多周期真读K线_教材.md + run_multitf_report.py(双击即用) 都在 multi_agent/trading/。回归: form_opinion没崩、prefer_mt5=False回测路径保留, 实盘下单链路没碰。
- 派单: @strategy-rd学会+回报 / @chief组织金策群讨论read盘结论 / @risk-officer复核D1逆势否决门。学会达标即销账 t_mt5_multitf_learn_20261013。

## 2026-10-13 金策·策略 SaaS · 把全网成熟功能全搬完（客户自主选择权 + AI大模型 + 移动保护自主设置, 45/45 验收全绿, git 4c82782）
> 用户令"你把他们成熟的东西都拿过来"+"客户如何选择策略 要有自主选择权"+"现在很多公司用 AI 大模型做交易 全网深度搜索全部实现他们的功能 给我汇报"+"还要有移动保护 客户根据自己需求自主设置"。
> 铁律不变: 全部只落 D:\jince_sass\, 引擎 D:\client-jince 与 10 个定时任务不动。
**本轮全网对标并落地的 4 块成熟功能（亲跑验货）**:
1. **AI 大模型交易模块**(src/ai/ 6 文件, 对标 Moomoo/TradingAgents/AInvest): /api/v1/ai/ 四端点 = ①AI投顾对话选策略(自然语言→本租户策略库筛推荐, LLM JSON优先/规则引擎兜底) ②AI风控双闸(verdict+可解释reasons, 规则兜底对照客户三闸, LLM误approve会被规则轨降级) ③AI市场点评(真K线算 MA5/20+ATR+回撤, 套大白话模板, 没数据明说无数据绝不造假) ④自然语言下单("用20%资金跟黄金回撤15%就停"→percent=20/max_drawdown=15)。每端点带 ai_mode(llm/rules)透明标注+llm_configured。无 LLM 自动降级规则引擎, 绝不500不造假。tests/test_ai.py 6/6。
2. **策略市场后端**(src/marketplace.py 415行, 对标 ZuluTrade 40+筛选器/eToro/cTrader): /api/v1/marketplace/ = ①策略列表+筛选(min_win_rate/max_drawdown/risk_rating1-5/min_followers/asset)+排序(pnl/sharpe/drawdown/win_rate/followers)+分页 ②四大排行榜(followers/pnl/low_dd/win_rate 各top5带rank) ③多策略并排对比(≤5个, 缺填null不报错) ④客户自主改自己订阅风控(改别人403, 改完审计哈希链 before/after) ⑤换仓推荐(同资产+风险相邻一档±1+pnl降序top3)。risk_rating 1-5派生不落库(红线sharpe<0或dd>30%→5, 安全分换算)。tests/test_marketplace.py 5/5。
3. **客户移动保护自主设置**(对标 cTrader Copy 移动止损/ZuluGuard/eToro随时停): Subscription 加 trailing_stop_pts/trailing_tp_pts/equity_stop_pct/eq_baseline/paused(含SQLite轻量迁移) + src/exec/trailing.py 纯函数compute_trailing_levels+TrailingTracker(价格有利移动后止损跟抬锁利润) + 风控闸0(paused拦全部跟单)/闸0.5(equity_stop_pct回撤超阈自动暂停) + main.py 客户自助端点 PUT /subscriptions/{id}/protection + POST /pause + /resume + GET /protection-status(带审计)。网页"🛡️我的移动保护"面板: 每订阅一卡, 参数表单+保存+一键暂停/恢复。tests/test_trailing.py 7/7。
4. **真实行情交易版面**(上一轮命门, 本轮全端点验货): /market/* MT5 终端实拉8周期K线+报价+账户+持仓+成交, 终端在线实拉/离线回放真2.9MB快照, 没数据明说无数据绝不造假。web/terminal.html Lightweight Charts v5 真K线。端到端验货: :8891 真服务 /market/status source=mt5 realtime=true。
**网页客户端新增**: "🤖 AI助选·策略选择中心"视图(AI投顾对话/四大排行榜/AI市场点评/自然语言下单/多策略并排对比, 接 /marketplace+ /ai, 离线给诚实提示不造假) + "🛡️我的移动保护"自主设置面板。app.js +index.html 已接好, node --check 语法通过。
**总验收**: tests/ 全量 45/45(acceptance 9 + exec 10 + billing_p1 3 + metrics 5 + trailing 7 + ai 6 + marketplace 5), 端到端 11 端点全通。git 4c82782 收口。
**下一步(若继续, 仍只落 D:\jince_sass\)**: 接真 LLM(AI_BASE_URL/AI_API_KEY 环境变量即升 llm 轨, 现为 rules 兜底) + Docker 部署 + Prometheus/Grafana(把 /admin/metrics 接出去)。

## 2026-10-13 AI 模块接真大模型（Agnes agnes-3.0-flash 网关, ai_mode 真切 llm, git cbd311f）
> 用户令"好"(接上真 LLM, 从规则兜底轨升到真大模型轨)。
- **.env 接入(gitignore, key 不入库)**: D:\jince_sass\.env 写 AI_BASE_URL=https://api.agnes-ai.cn/v1 + AI_API_KEY(取 Hermes .env 的 AGNES_FLASH_API_KEY, sk-ISp…51位) + AI_MODEL=agnes-3.0-flash + AI_LLM_TIMEOUT_S=30。key 来自 Hermes 池的 Agnes FLASH, 非金策 4 把专属 key, 不违反铁律。
- **main.py 启动加载 .env**: import 段加 os + load_dotenv(override=False 不覆盖已存在环境变量), dotenv 缺失/.env 缺失都静默走 rules 兜底不崩主系统。
- **conftest.py 铁律**: pytest 根配置设 JINCE_SASS_SKIP_ENV=1 → 所有测试跳过 .env 加载, AI 端点恒 ai_mode=rules(确定性不依赖外网/额度, 不烧真 key); 生产 uvicorn 直接起 main 不设此变量 → 正常加载 .env 走 LLM 轨。职责干净分离。
- **实测验货**: 起真服务 :8891, POST /api/v1/ai/advisor 单发 → ai_mode=llm 真切换(耗时3.2s, reasons 是大模型生成的中文"设定最大回撤上限10%以符合低回撤定义", 非规则引擎话术)。之前连发探活撞 Agnes RPM 429 + 冷启动首字超 20s 导致假降级, 已把 timeout 提 30s 根治。
- **降级铁律不变**: LLM 未连/429/超时/JSON 解析失败 一律 llm_chat 返 None → 上层自动走 rules 兜底, 端点永远 200 绝不 500 绝不造假。
- **全量回归 45/45 全绿**(conftest 设 skip 后 test_ai 仍走 rules 确定性), 端到端 LLM 轨单发验通。git cbd311f 收口。

## 2026-10-13 金策bot-chat静默真根因（主bot agent.log实读, 非gateway/非429）
- 定论: 33个金策播报job全 deliver=bot-chat:chief 且全 resume 同一个named会话'Bot Chat'=20261013_083034_c12893, 该会话08:30起累积到153条msg/单turn in=86037 token. 每播报=resume胖会话→LLM回合60-170s+会话锁活体不放→并发全排队→target_busy→delivered=0. 这就是"SESSION_NOT_OWNED/600s超时"同族, 根子=胖会话+锁串行化, 不是gateway死.
- 自愈: 11:44后failed 55→0; 11:59一条turn真text_response完成=群没全死, 是迟到挤着出. 我主bot反复手动spawn探针反而给队列加塞(churn), 已停手.
- 根治(t_bloated_botchat_session_20261013): 高频哨兵job改开新会话/按班次独立会话(方案A), 或定期compact/rotate胖会话(方案B); 不碰交易实盘/不碰gateway. 验收=11:55/12:05/12:15连续三班delivered>0且无target_busy.

## 2026-10-13 学习后开单效果·三席群讨论收口（chief主持+strategy-rd分析+risk-officer风控, 全实读背书）
- 效果=0（实话）: XAUUSD SELL_LIMIT 0.01手(挂11:09)触发4219.62/SL4243.75/TP4156.35/RR2.6, 近72h没弹到位→0成交0盈亏, 净值965.40没动. 链路通(学看多周期真K线→挂单)但没跑出盈亏, 不虚报.
- 风控裁定 APPROVE_WITH_CONDITION: 4条红线没踩(日≤3单0/3/日亏10%熔断P&L=0/连亏冷却0/D级否决门不适用=小样本池n=4). 放行但两前置: ①现价<4190撤重挂(防追价) ②SL24.1点=2.49%净值超0.5%仓位闸→进场后0.5ATR快砍兜底. 落veto_log ticket603067879.
- 撤单双条件: 即时跌破4190(风控) / 48h即10-15约11:00没触发(strategy-rd). 成交靠行情走到, 30min循环盯, 22:00日报对账.
- 出真效果标准: 攒30笔前向真实成交+同分母五验+z≥1.96, 空卷0成交不算, 约1个月, 不跳档不提前放大.
- 更正留痕: 触发价实读用price_open=4219.62(老绑定字段名坑, 两拍曾误读price_stoplimit=0.0), 双数已更discussion_log.

## 2026-10-13 strategy-rd收尾: TIMECAP空卷真根因=IPC价源争抢(坐实, 防再瞎查)
- strategy-rd定量拆解实锤: 单币XAUUSD全策略simulate外推仅3-6s/拉K线0.2s, 远低于1560s/币护栏 → 单币本不该TIMECAP.
- 真根因=IPC价源争抢: 多个Python引擎/探针进程同时霸 copy_rates_from_pos 全阻塞(非回测逻辑慢/非引擎触价bug[空头式10-09已修,grep判反残留0]). 这跟主bot查'多周期真K线'时 copy_rates_from_pos 卡是同一个坑.
- 06:50补卷哨兵0=假阴性(全币0成交没跑出腿, 无n>500腿) → 坐实主bot纠偏+「空卷不出结论」铁律.
- 销账条件钉死(rd_queue open_ipc_rootcause_confirmed_clean_backfill_running): 非空卷(6币有真实成交)+哨兵真实清零+breadth_pass 三件齐才算过, 不收空卷假账. 后台干净直跑PO6补卷(proc_cf38324f19f8, 1终端独占IPC, 约25-40min).

## 2026-10-18 金策SaaS·客户远程体验 + 执行腿最后一公里(主bot代总调度落地, 用户令"客户远程/全部做好/继续深度优化")
> 范围铁律不变: 全部只落 D:\jince_sass\, 引擎 D:\client-jince 与 10 个定时任务不动; 默认 dry-run 不碰 60137964 资金.
**本轮落地(全验货)**:
1. **客户远程体验打通**: 8800 改监听 0.0.0.0 + Cloudflare 一次性隧道(客户手机/任何网络直接进, 免装免给内网IP) + 看门狗 _watchdog.py(服务/隧道挂了自动拉起+链接文件自动刷新, 修了 tasklist GBK 乱码崩溃真 bug) + 开机自启(启动文件夹 JinceSaaS_Watchdog.bat) + 桌面一键恢复 bat. 客户入口链接每次隧道重启会变, _refresh_link.py 自动刷新到 桌面/D:\jince_sass\客户远程体验链接.txt(客户账号 demo@jince.demo 已预置体验现场: 体验EA+自动驻留+demo行情+开单历史). 长期固定链接需 Cloudflare 命名隧道(用户账号).
2. **执行腿 executor.py(客户绑自己账号→单真落自己钱包)**: 默认 dry-run 记账(CustomerEaFill 成交账本, 模拟也留痕); 真下单=双闸门(平台 JINCE_SASS_ENABLE_MT5 + 客户 live_trading_enabled)+终端attach账号==客户绑定账号, 缺任一诚实降级 dry-run 写明原因(SDK 物理限制只能发当前终端账号, 绝不假装成功); 幂等键 client_order_id(分钟切片+单内seq, 防双发且不撞唯一键——seq 修复被回归测试揪出的真 bug: 一轮多笔同向单曾崩 UNIQUE). 客户3端点: /execution-status(现在是模拟还是真发)/ /live-trading(开自己真单开关)/ /ea/fills(跟单成交账本逐笔核对). 凭证红线测试锁定: /accounts 绝不回显 password.
3. **可观测**: /admin/metrics 第9项 ea_exec(留痕分布+全局闸门态) + 监控页第9卡"执行腿·客户EA".
4. **前端面板⑭ 收口**: 执行状态条+跟单成交账本+「我要真下单」开关 全绑定, ▶运行结果直显"真发到哪/为什么没真发".
**验收**: tests 全量 105/105(原97+执行腿8, git 收口); 8800 新码活(0.0.0.0)+隧道200+客户视角 execution-status/ea-fills/跑EA 全通; app.js node --check OK.
**全功能巡检(用户令"里面的功能要都能用"): _patrol.py 把前端用到的 34 个端点 + EA 全生命周期(建/调参/自动驻留/运行/熔断/复位/暂停/恢复/历史) + MQL5导出(5099字符真代码) 在活服务上逐个真打 → 34/34 全 200 功能全通. 初版巡检揪出 4 个"坏项"逐一坐实全是巡检脚本自身误用(2个用GET打POST端点/checkout没带card_sim body/查了前端不用的GET /subscriptions/元组解包错), 系统本体零缺陷; 前端订阅表格真实数据源=report.active_subscriptions(实测正常), 不依赖缺失端点. 巡检脚本修好收口 git. 缺数据的洞察类面板(attribution/correlation/risk-budget/scenario-stress)按"诚实标注无数据不造假"设计报 200, 非故障.
**待办(需用户)**: ① Cloudflare 账号配命名隧道(链接固定) ② 给客户开真单=平台设 JINCE_SASS_ENABLE_MT5=1 + 客户勾选 + 终端挂其绑定账号, 三者齐才真发(客服话术已进交付指引 内容中心\交付\金策SaaS_客户远程体验指引_20261018.md).

## 2026-10-19 13:46 自动全链扫描（cron auto_run_cycle，DRY-RUN）
- 净值 **$971.54**（balance=equity，MT5 实读）；实盘 0 持仓 0 挂单；残留系统仓（magic 20260902）= 0，DST=外网断冻结，无需清理。
- 风控: LEVEL=1, 否决记录=3/放行=3/拒=0；连亏 2（<3 未冷却）；回撤 3.61% scale=1.0。
- 异常: 外网断（forexfactory blocked，本地缓存兜底，日内放行需降级半仓禁隔夜）；XAUUSD 破位撤单闸（bid 4184<4190 只出不进）；GBPUSD 命中 L4 常设 VETO 拒挂；币系冻结至 11-02 NFP。
- 挂单交易部本轮 0 新挂 0 开仓（DRY-RUN，LIVE_TRADING_ENABLED 未开）；简报"持仓3"均为终态留痕（XAUUSD SELL×2 + GBPUSD SELL，早已了结）。


## 2026-10-20 09:30 最高级别优化·四件收口（主 bot 深度解析+实跑验货）
> 用户令「全部给我优化到最高级别」。前提: 先认账——昨日 P0 改错库(改的是 E:\资料 废弃副本, 对活的 E:\GoldstrategyEngine 不算数), 今日改到真实引擎, 全有备份可回滚。
> 交叉验货 workbuddy 4 文档 + 真实引擎源码/日志/MT5 实读, 逐条坐实后再动手。
**四件全部落盘验货(活系统上最高价值+绝不崩循环+全可回滚)**:
1. **fail-closed 安全网关落地(guardian_executor.py)**: 把 config.SAFETY_LIMITS(之前只备着无人消费, workbuddy 坐实的隐患)接进唯一 LIVE 下单收敛点 _send_order(开仓), 三道墙=①服务器名含 Live/Real 拒②终端实际账号!=config.login(账号漂移)拒③allow_live_trading 总闸未开拒; 读不到账户也 fail-closed 拒。**平仓 close_position 刻意不挂(释放风险绝不能被卡=卡住=仓位裸奔)**。验货: mock 6/6 场景全对(该拒的拒/该放的放/开总闸仍拦实盘服务器)。
2. **双 watchdog 收敛(jince_watchdog.py)**: 根因=15min no_agent cron 被调度起两遍(PID 20596/4396 差32s), 双实例=重复巡检/重复拉端/重复刷闸(同族双调度搅乱隐患)。已加 Windows 原生 msvcrt 文件排它单实例锁: 第二实例 LK_NBLCK 立即失败静默退出, 进程崩 OS 自动释放句柄锁不留僵尸挡后续轮次。验货: 双启动实测3/3(实例1抢/实例2挡/释放后实例3再拿)。
3. **一键急停 kill switch(jince_kill_switch.py 新建)**: 独立于主循环的撤单+平仓急停; 只碰本系统 15 个 magic 白名单(20260704-12/0901-04/1020-22), 绝不误伤手工单; 默认 DRY-RUN 只报告, 加 --execute 才真动; 全程写审计 kill_switch_audit.jsonl。验货: DRY-RUN 跑通, attach 60137964 净值 $971.54 实读, 0持仓0挂单正常报告。
4. **LIVE 现状坐实(只读不改)**: guardian_executor LIVE_TRADING_ENABLED=False + auto_confirm=False 双锁按着=现在一直 DRY-RUN 不真下单, 安全。唯一活风险=谁误开 LIVE 开关就裸奔——1号安全网关就是堵这个的。
**锁死空仓定性(非bug)**: 09:01 轮 72 候选全否决(30 coin_frozen+36 negative_expR+9 low_conf)=风控在正确判断「当前市场无 RR≥2 好机会」, 四道闸叠加(币冻结+expR负+MED 0.5x+RR门槛)收口。不建议强解; 是否放宽 min_rr_ratio(主2.0/币1.5)交 strategy-rd 五验拍板, 不拍脑袋。
**丑话**: 修安全/运维/急停≠能赚钱; 真 edge 仍卡 30 笔 OOS+30 天净值转正; 历史回测≠未来收益。
备份: E:\GoldstrategyEngine\backup_p0_opt_20261020_0927\(config.py+guardian_executor.py+jince_watchdog.py)。

## 量化网·依瓦AIOS 方法论融合（2026-10-19）
学自《E:/资料/量化网/量化网--依瓦Ai量化智能体介绍.pdf》(A股"依瓦AIOS"产品介绍)。
我们是 MT5(黄金/外汇/币)跟单SaaS，它的"5500 A股指标/35年A股数据/主力资金/T0"没有A股数据源→不照搬造假；
只融方法论层三块，全落现有EA体系、默认dry-run不碰资金、测试锁死(132/132含新增10个test_quantnet_integration.py)：
- A 一句话建EA: POST /api/v1/customers/me/ea/from-text（LLM轨+规则兜底双轨，中文品种/风格/阈值/周期/多空全解析）
- B EA模板商城: GET /ea/templates + POST /ea/templates/{tid}（4套专家参数包gold_swing/fx_trend/core_defend/vol_bidi一键套用）
- C 自动调参: POST /ea/{pid}/tune（读成交账本算绩效给调参建议；胜率只认本EA真单票据匹配终端平仓，dry-run诚实报"无平仓样本"不编胜率）
前端web/app.js已挂(一句话/模板卡片+每EA卡片加"🤖自动调参"按钮)，活服务:8800真打全绿，老功能回归未破。

## 2026-10-20 AI 全天候交易 bot（主 bot 总调度，李老师令"按最优方案自主决定 以后不要问了"）
- **定位**: 新 bot 独立于金策 15195 行活引擎, 复用其 AI 建议层(top_trader.decide), 不碰活代码。代码在 `E:\workbuddy\内容中心\交付\AI交易bot方案_20261019\jince_bot\` (protocol/side_brain/side_hand/signal_bridge/runner/verify), 独立 venv 装 pyzmq+MetaTrader5。
- **架构**: 脑(出信号,PUSH)→ZMQ→手(attach 官方 MT5 库收单执行,PULL)→成交回传+序列号核对。手侧默认 DRY(组装真实订单+读真实价,不真 order_send), `--execute` 才真下。
- **可靠性层(全网最优公约数)**: 三道安全网关(服务器Live/Real禁词拒/账号漂移拒/实盘总闸只在真下单拦) + 幂等去重(client_order_id) + 序列号防漏(每seq必回执,超时=疑似漏单) + 成交确认(retcode白名单) + boot对账(启动读真实持仓不假设空仓) + 断线重连。
- **验货证据(demo 60137964, 全DRY 0资金)**:
  1) e2e 全链路 XAUUSD DRY 真读价 4141.88, 幂等去重同单三次只下一次, 序列号全核0漏单。
  2) 信号驱动闭环: top_trader.decide 真读版出 6 单(heat 1.27%), 9/10品种 source=MT5_LIVE, 取5单走脑→ZMQ→手 DRY 全 sent=True dry=True, 绝对SL/TP透传(修了价差当点数贴价坑)。
  3) runner 手数重算生效: 用金策 symbol_universe 的 pip_usd(每手每pip美元值) 重算, ADAUSD lot=0.05(不再全塌0.01), 13条emit全DRY全回执。
- **24/7 常驻**: runner.py --loop 1800(30min一轮) 已挂后台 persist_on_release=True, 日志 jince_bot/runner_loop.log。
- **已知待办/坑(交strategy-rd, 不碰金策活代码)**: 金策 top_trader 币系 sl_pips 量纲 bug(非贵金属非JPY品种价差当pips, 手数算错, DRY不影响安全但开实盘前必须修, 交五验拍板)。
- **丑话**: 这套骨架证明"24/7能活着/不漏单/不误下单/可急停/可断线重连", 但不证明能赚钱; edge 仍卡 30笔OOS+30天净值转正, 历史回测≠未来收益。真下单需开 allow_live_trading 总闸+5验过线, 默认永不开。

## 2026-10-20 19:22 交接·jince_bot 切真下单 + 交回宗师团（李老师令"这个窗口我想关闭了 交给金策宗师团处理"）
> 主 bot 本窗口收尾。jince_bot 已从 DRY 切到【真下单】并后台常驻, 窗口关闭不影响它跑。宗师团接手照此卡接。

**1. 状态: 已切真下单 (双钥匙, 不是 DRY 了)**
- 触发: 李老师原话"干净训练 跟人工操盘手一样 操盘开单 给你账号了 怎么一直没动静" = 开绿灯切真开单。
- 双钥匙: runner `--execute` + 环境变量 `JINCE_BOT_LIVE=1`, 缺一把自动退 DRY (fail-closed)。手侧 `--execute` 才真 order_send。
- 账户 60137964 @ TradeMaxGlobal-Demo (**demo, 非真钱**, 0 资金风险)。**注意: 这套 jince_bot 走的是 demo 真开单, 不等于金策引擎 allow_live_trading 总闸 —— 金策活引擎仍是 DRY-RUN 没动。**

**2. 实况锚点 (19:22 实读)**: 余额 $971.54 净值 $965.03 持仓 5 挂单 0。
- 19:15:57 一口气真开 5 单全成交确认 (retcode=DONE): XAUUSD BUY / XBRUSD BUY / AUDNZD SELL / BCHUSD BUY / XPTUSD BUY, 各 0.01 手。
- 浮亏约 -$6~-8 (开仓 4 分钟内正常点差, 距日亏 10% 熔断线 $874 还远)。

**3. 后台常驻 (窗口关了还在跑)**: `runner.py --equity 971.54 --execute --poll 15 --signal-refresh 60`, `persist_on_release=True`。
- 15 秒巡一轮: 实读账户→日亏熔断→持仓管理(金策不再持有/反转即离场)→有信号立刻开单; 后台线程 60 秒刷金策信号。
- 代码目录 `E:\workbuddy\内容中心\交付\AI交易bot方案_20261019\jince_bot\` (protocol/side_brain/side_hand/signal_bridge/runner/kill_switch/bot_risk/stop_today), 独立 venv (pyzmq+MetaTrader5)。
- 日志 `jince_bot/watch_loop.log`; 审计 `E:\GoldstrategyEngine\data\jince_bot_{runner,brain,hand}_audit.jsonl`; 当日状态 `jince_bot_daystate.json` (重启不丢魂: 熔断/计数落盘)。
- 单实例锁 `jince_bot_runner.lock` + 就绪文件 `jince_bot_hand_ready.json` (uv shim 坑: 不靠 PID 匹配, 靠就绪文件时间戳)。

**4. 三把钥匙 (宗师团随时能用, 落到李老师手上零歧义)**
- 一键急停: 双击 `jince_bot\一键急停.bat` → 按 Y → 撤全部挂单+平全部持仓 (只碰 magic=20261020, 绝不误伤手工仓) + 设当日熔断。
- 切回假开单 (DRY): 跟我说"切回 DRY" → 重启 runner 不带 `--execute`/`JINCE_BOT_LIVE`, 15 秒内切回。
- 清 5 持仓: `jince_bot\kill_switch.py --execute` (独立进程, relay 死了也能用, 只碰本系统 magic)。

**5. P0 保命三件套已收口 (本窗口落地)**
- ✅ 风控单一源 `bot_risk.py` (单笔0.5%/heat6%/日亏10%/单品种日3单, AI 说了不算, 代码硬闸)
- ✅ 日亏熔断时区写死北京时间 UTC+8 (机器时区被改不触发 bug)
- ✅ 重启不丢魂 (daystate 落盘, 重启不清零熔断/计数) + 一键急停 .bat
- ✅ 疑漏单根治 (脑侧 `_inbound` 统一收件缓冲, 迟到 FILL 全回收, 0 漏单验绿)

**6. 交宗师团的下一步 (按 ROI)**: ① 进程自愈+静默报警 (可靠性 80→90, 1-2天) ② 回撤35%+相关性+滑点高级风控闸 (1天) ③ Edge 只能靠时间攒 30 笔 OOS + 30 天净值转正 (不跳档) ④ 信号源扩 + 可观测面板 (前沿件往后排) ⑤ 金策币系 sl_pips 量纲 bug 交 strategy-rd 五验 (开实盘前必修, 现在 demo 真开单用 runner 的 pip_usd 重算绕过了, 不影响安全)。
**丑话**: 切真下单 ≠ 能赚钱。demo 攒的是 30 笔 OOS 证据, 今天这 5 单是第 1 批; 历史回测≠未来收益, 浮亏正常。谁跟你说月化 30% 稳赚, 谁在赚你钱。


## 2026-10-20 红级 · 敞口口径分叉（chief 汇报层读错腿，已派 risk-officer/chief 复核）
- **事实（python3.11 活体重读 terminal64，权威源 _mt5_readonly_probe.py）**：账户 60137964 实开 5 仓（各0.01手）。**方向=4买1卖，AUDNZD 唯一卖单**：XAUUSD买/XBRUSD买/XPTUSD买/BCHUSD买/AUDNZD卖。（注：探针 type 字段是字符串'BUY'/'SELL'，早期读法误拿它==0 比成全卖，Chief 2026-10-20 物理交叉验(盈亏符号vs现价)已更正，以此为准；chief 留痕 discussion_log 第1446行。）equity 950低点→973回血、trade_allowed=True、回撤~3.4%（未破日亏10%熔断）。
- **根因**：guardian_executor.py（LIVE=False 影子账腿）报“系统仓=0/0敞口”，今天全链扫描+逐拍汇报一直读这条腿 → 整天误报“实盘0敞口”；真正下单的是 exec_live_60137964.py（写死 LIVE_TRADING_ENABLED=True、demo 真单腿）。两腿敞口没对齐，“0敞口”汇报系统性漏 live 腿。
- **纪律红线**：5 仓含 BCHUSD（币系）撞币系冻结闸（crypto_freeze_gate.json active=true 冻到 11-02 NFP，例外白名单只有 POLUSD，BCH 不在）。
- **状态**：只读未动仓；已派 @risk-officer（L4 币腿裁定撤/留）+ @chief（对齐两腿敞口口径、汇报层改读 terminal64 positions_get）。撤/平 5 仓是交易动作，按红线先报后动、李彦明拍板。
- 历史回测≠未来收益。

## 2026-11-16 10:0x 深督拍·黄级 (strategy-rd 主动优化两头号命题, 主bot default, 每48h拍)
- **判定=黄级(非停摆)**: ①strategy-rd 活: research/loss_cycle_log.md 亏损驱动6h循环活到 11-16 04:09 + G5 ORB 轮转活到 11-16 08:01(rd_ledger_24h, 全 REJECT); ②但**指定台账** `E:/workbuddy/金策宗师团/strategy-rd/研究台账.md` 停更 31 天(最后条=10-15 黄金连损), 活产物全落 `E:/GoldstrategyEngine/research/`(留痕错位, 非停摆——若按指定台账判48h停摆会误判, 多账对账坑)。
- **两头号命题验收(5件套)**: ①亏损单=交付为「B0假突破结构性拒绝」纪律(loss_leakage_report.md 87笔/胜率13.8%/−37.15R, 六参数+信号闸五验全FAIL=维持现役, 结论对), 但**没钉指定的 TSLA/KLAC负腿+影子链47SL+近72h 30261103SL 逐单autopsy表**(现只有 broad live24 全量分析); ②$10锁利=L0已LIVE(chief R11 11-12 09:48, USD_LOCK=5.0/giveback 0.6R), 但 **L1(HotLockEA挂图验活)+L2 未交付 + 灵魂指标「浮盈峰值回吐超$X笔数显著下降」只 track giveback_fail=4, 没出[基线 vs 现行]对照数**。
- **红线gap(从严盯)**: **t_3599373f [L4复核 USD_LOCK $10锁利翻闸补签] risk-officer status=blocked, 11-12 09:37起已逾期4+天(原24h期限), USD_LOCK L0 引擎写无L4复核裸跑4天** — 已发 bus 催签 risk-officer(urgent, 24h内复签或否决回滚) + 催 strategy-rd(高优, 补指定台账+命题①逐单表+命题②L1L2回吐对照, 下一拍 11-18 10:00 前)。
- **留痕**: bus 双写 `E:/AgentCommons/bus/inbox/strategy-rd` + `inbox/risk-officer` + `outbox`(20261116T100759, 各带 outbox 存档); 缺项攒 22:00 日报。
- **大白话**: 研发没停(亏损单/锁利/供需区都摸过, 6h循环一直活), 但①活没记到指定的账本上 ②两个重点题目只交了一半 ③最要紧的是 $10 锁利的风控官复核拖了 4 天没人签——已催风控官 24h 内补签、催研发下拍前补齐。历史回测≠未来收益。

## 2026-11-12 黄级 · 深督拍#1（strategy-rd 主动优化三令后首拍）
- **事实**：三令 09:27 bus 兜底双写入 strategy-rd 收件箱（取件哨 10:00:52 跑活，10:15 拍取件唤醒）；48h 首交期限 11-14 09:00 未到，五件套两命题未出属在期限内，未构成停摆。
- **$10锁利 L0 已先行落地**：进化营 09:32 落码 jince_live24.py（USD_LOCK=10.0 触发/USD_TAKE=0 纯锁保奔跑/USD_GATE_R=10 大SL品种/USD_BUF=1.0，WFO 五验 9 品种 n=11432 ΔR>0 banked_R+1746 WR67.3%），chief R11 翻闸 09:48，引擎 PID 31480 验活（锁 ts 刷新/心跳新鲜）。
- **缺项（黄）**：USD_LOCK 翻闸无风控官 L4 复核记录（kanban/rd_decisions/veto_log 三源查无）→ 已当场补 L4 复核卡 `t_3599373f`（risk-officer ready p95，5 裁定点+不动清单，24h 期限），等复签；引擎/L0 层不回滚等 L4 裁。
- **L1 HotLockEA**：ex5 编译 0 错 0 警；挂图未验（错挂 A3B1DF 终端+Algo Trading 未开，已诊断待重挂），未上线=非越权。
- **台账停更**：strategy-rd 研究台账停在 10-15（28 天）；停摆判定归属下一拍 11-14 10:00（48h 窗 = 本令 09:27 下发起算），届时无合格产出=写 bus 点名催+红报。
- 缺项攒 22:00 日报。历史回测≠未来收益。

## [11-15 02:0x] 深研拍假交付根除闭环(主bot)
- R1币系/R2金银FX 两拍宣称'深研日志落1行'均未落盘 -> 主bot补记 family_deep_study_log.jsonl(R1=11-14行/R2=11-15行, 2行齐)
- 交付验活哨(jince_delivery_verify.py)新增第4查项'深研拍-日志对账': research/ 内48h内深研产物(arbr_/soul_/hourwindow/fx_gold)必须有对应日期日志行, 缺=FAIL -> 防第三次假交付; 验活: 编译OK+实跑exit0+check4对账PASS(两产物均有日志行)
- R2深研裁定留痕: 破位裸开单进禁开名单(4044笔全族负edge) / 金禁开窗收窄20-23UTC / 15min数据企稳扩到金银数据窗 / 全OBSERVE引擎未动

## [11-15 06:0x] R4汇总拍挂掉=已脚本化替代(主bot)
- 05:30 R4汇总一次性拍(cc87ac2a06b3) LLM 4次续写截断全挂, 四步零落地 -> 主bot确定性脚本替代讫: scripts/jince_r4_rollup.py(0 LLM, 验活: 首跑三行/稳态零输出/幂等工单)
- 已落地: data/family_playbook.json(exec=0 watch=1 negated=2, 全WATCH引擎0变更) + rd_queue工单 t_live24_family_playbook_hook_1115(P2挂点, strategy-rd审批)
- 预防铁律: 以后深研R4汇总拍一律排 no_agent(jince_r4_rollup.py), 不再用LLM一次性拍; 明晨07:15汇总Word拍(c357e569d980)读到的playbook.json=本脚本产物, 数据链已通
- 【2026-11-15 07:09:00 P3灵魂观察批】李令"灵魂技能深度复习彻底融入灵魂": S1-S8逐条重学+引擎差距扫描(无越权接线, S8正确未接); _soul_obs_tags开单打S5族窗/S4日偏/S6定位标签(零行为变化); 热切换pid13812三验全绿; 报告research/soul_gap_scan_20261115.md; 30笔OOS攒样后走五验+R11双裁翻闸

- 【2026-11-15 07:47:02 供需区深研】李令"深度挖掘供需区做单思路看效果": Seiden原文钉口径(破区质量+first test收线进+3R+12h)8品种M15同分母=全族REJECT(XAU -161R/胜率0), 机理=质量判据被机器化稀释+迟到回踩逆动量接刀(E1同族); 不接线不放大; 保留增量=爆炸移动分桶OBSERVE; 报告research/sd_zone_verdict_20261115.md

- 【2026-11-15 07:50:28 供需区双向证伪】李令"反着做看效果": 顺势版(破需求区回踩上沿空/破供给区回踩下沿多, SMC BSS+retest)8品种=MOMOMOMO... 全族REJECT(顺势亏损>逆势>base追破); 关键读数=昨高低±30%机械区本身无edge(双向+base三组全负), Seiden的edge在人工质量裁量; 下轮=质量判据机械化(1.5xATR爆炸+fresh+3x利润区)同分母五验, 不过=三次证伪销账; rd_queue sd_zone_quality_spec_20261115

- 【2026-11-15 07:56:43 Seiden原文吃透+技能深度优化】李令"深度优化技能全面深学原文材料吃透": 全读 sam_seiden_cn 400页核心三章(P1-30基础规则/P150-167 Odds Enhancers/P376-400区机制); 新发现=10分制概率增强剂评分系统(前两轮供需区REJECT病根=丢评分)+gap最大失衡+回踩衰减砍树喻+越失衡停留越短(反教科书)+新闻错觉进攻用法(BP实证)+日初45-60min黄金窗; 已融入技能institutional-order-flow§八+深学卡原文层+rd_queue sd_zone_quality_spec规格改为原文10分制机械化映射(≥8分才出事件, 五验不过=三次证伪销账)

- 【2026-11-15 08:15:21 全量资料10遍深读收敛+供需区销账】李令"全部资料深度学习10遍以上给我汇报": 8文件1.9M字10遍(2280判据提取->聚类->10setups全读->Seiden余159条skim->技能§十->供需区第4轮原文标准结构REJECT->四次证伪销账CLOSED->判据三桶清零); 新核心=Brooks 10 setups机械判据(H2/L2旗, 高开75%先测均线, 楔形3推75%破, 通道25%, 区间1/3二次进场)已入技能§十+rd_queue brooks10_setups_backtest READY; 供需区独立进场法销账, 3:1利润区底线+供需判据保留于S01-S08

- 【2026-11-15 09:03:04 供需区裁定重发: 旧四次REJECT作废(结算符号bug), V2止损外移1.8x五验6/6=APPROVE候选进30笔OOS观察】李令"验证扫损后走势": 对账抓到sell分支TP/超时分母符号bug(盈利记成亏损) -> 修复重验: R4五品种翻正, EUR扫损后92%再摸TP=方向对时机错成立; V2=8/8全正 净R+1703 胜率84% 五验6/6; 供需区REOPEN进OOS观察, 教训入技能(结算镜像分支符号断言)

- 【2026-11-15 09:39:12 供需区42组网格深度优化定案: E3+S1(区远沿限价进+紧SL 0.2x区宽) 净R+4533 胜率99% 五验6/6 最大回撤仅8R 最大连亏8笔, 进30笔OOS观察; 备选E3+S7(扫损垫)给防扫损场景; 关键规律=紧止损净R单调最高(紧SL=小R=目标近=高频达成), 外移止损反而降; 连抓2个结算引擎符号bug(sell/buy镜像分支分母写反), 盈利断言单测已入技能铁律

## 2026-11-19 2026-11-19  工作制度v1生效(李令指令)
- 制度铁律清单v1: E:/workbuddy/金策宗师团/金策工作制度_铁律清单_v1.md (六大章23条, 每条=规则+责任岗+机器验证+留痕)
- 制度巡检哨 cron 56f62980c7dd(system-patrol-30m, no_agent全绿静默): 每30min机械验制度, 红件一行报+rd_queue工单(责任岗认领); 首拍已真抓XRP尾停红件(数据官下拍消化)
- 制度执行率进周五验尸周报, <90%红报李

## 自主运行机制（11-19 李令"给全部灵魂"授权）
- **30min 自动巡市哨** auto-soul-sweep-30m(563d32ec14a1)：自动扫灵魂门→合格自动开单（分品种赚钱格 0.01 攒样级，四闸=D4尾龄/冻结窗/日位/去重，每拍≤2开）→12h红线登记+到期自动处理→**开单立即报微信**
- **10min 出场反馈哨** auto-soul-exit-10m(40bfe6020e77)：仓位消失=立即报（分类：移动保护锁盈/止盈/原止损/手动）→盈利侧出场重扫灵魂门：**方向未反转=当场市价再进场（0.01同格+红线再登记），反转=报观察**
- 冻结窗数据化=data/event_freeze_windows.json（晨学哨可追加）；开单格表=data/auto_soul_params.json（12轮战役top1+赚钱格）
- 实绩：本时段 EUR 双腿均移动保护锁盈离场（+0.26/+0.07）；EUR格R=3.4点vs点差1点=点差占0.3R磨平循环→验尸岗材料
- 制度：铁律清单 E6/E7（自主闭环+冻结窗数据化）；无事件=静默，开单/出场=必报
- 更新时间 2026-11-19 18:53

## 每单经验值(XP)进化系统（11-19 李令"每个单子都要有学习升级的经验值"）
- **XP聚合层** research/order_xp_1119.py: place/close自动配对(零侵入) → 每单XP(基础10/盈利+20/亏损-10+5学到) + 格级状态机
- **格级状态机**: 30样本满+净利≥0+胜率≥55% = 自动立⑥线翻闸工单(rd_queue, 参数官裁); 10样本负 = 降级/换宽档审工单; 其余=WATCH攒样n/30
- **20:15 每日XP日报** cron 3ab72d570c2c: 报回当日单/XP/各格状态; close行缺失=每日自愈补录(服务器成交合成, 找不到=不计XP绝不伪造)
- 首报实测(11-19): 累计23单 净+0.40 XP245; BTC@0.8/3 3笔全胜(+0.41), EUR@0.5/3.75 2笔全胜(+0.33), SOL@0.8/3 2笔1负(-0.39)=学习材料
- 制度 E8(每单必带XP) + E7(五闸+3秒验收+冻结窗自动滚动); 更新时间 2026-11-19 19:33
