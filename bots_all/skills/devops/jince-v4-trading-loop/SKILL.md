---
name: jince-v4-trading-loop
description: "金策v4固定交易闭环SOP: 参数官专人制+8岗零无主矩阵+赚钱格执行. 开波/挂单/审计/翻闸前加载."
---

# 金策 v4 固定交易闭环 SOP（李令 11-17 深度优化升级后固化）

GitHub 存档: `dapengzhanchi141345/jince-v4-sop`（README=9步SOP全文, docs=分工卡v5+spec v4, scripts=参数官哨+三赚钱格哨）. 分工卡现版=v5（`E:\workbuddy\金策宗师团\金策宗师团_分工卡_v5_20261119.md`, 9岗: 总调度/参数官/执行/哨体检/数据官/风控/研发/验尸/取件 + L5裁定位, 20板块零无主）.**分工卡升级规则**: 新层/新冲突/新守护出现=新板块, 必须入卡重做零无主检查; 无天然单主板块用双主配方（码=X岗, 账=Y岗, 各管一半, 交棒走 rd_queue）; 全量 cron 归岗核对（last_status 全扫）是每次升卡的前置步.

## When to Use
- 开波/挂单/审计/翻闸前（李令交易指令, 金策任何执行动作）
- 写新哨脚本、改参数、收验尸结果、跑全品种深优时
- SL/TP 裁定细节研究见 jince-structural-sltp, 本技能只管执行闭环

## 九步固定流程（每次开波照走, 跨会话不变）
1. 行情扫描: 灵魂门(扫掠+位移+D1方向), 全品种同分母 -> 总调度
2. 参数取用: 只读 spec v4 权威表(唯一参数源), 参数官=唯一写者
3. 常量核对: 哨脚本 vs spec 一致才放行(参数官30min哨自动, param_officer_state.json issues=0)
4. 挂单: 信号腿×赚钱格SL/TP, 0.01手, 12h红线, 叠单去重 -> 执行岗
5. 风控: 熔断/事件窗/冻结态照查, OBSERVE门不误杀前向样本 -> 风控岗
6. 数据保鲜: tf_cache npz 30min刷新, M30闸=2h(11-19 P0收紧, 旧8h闸"mtime全绿但K线尾停6h"实锤); 效期戳双记mtime+m30_kline_end(数据末端), 消费方以kline_end为准, 尾停>2h(币)/34h(非币)=红件; M30末端>48h=五验FAIL -> 数据官
7. 收盘验尸: 亏损单必落"为什么亏+怎么改对", 不斩除 -> 验尸岗
8. 回测复核: 五验同分母(30日M30, OOS70/30双段, 0.15R压力), REJECT前查扫损后诊断 -> 研发岗
9. 攒样翻闸: 每格30笔OOS满 -> ⑥线翻闸工单 -> chief/L5裁定

## 交棒铁律
跨岗只走 rd_queue.json 工单, 禁直接改他岗文件; 参数表唯一写者=参数官, 越权=留痕追责.
**深度记忆指令=四层固化**: 李令"深度记忆不能再忘"类指令, 同一事实必须同时落: ①跨会话记忆条目 ②对应技能章节 ③状态卡追加 ④GitHub 入仓(commit+push 验远端 HEAD)——只写一层=换会话/换机就丢, 四层齐才算"不会再忘".

## 制度巡检哨（11-19 李令"建立工作制度"立法后常备, cron 56f62980c7dd 30min no_agent）
- 《金策工作制度_铁律清单_v1》(E:/workbuddy/金策宗师团/) 六大章 23 条: 数据/执行/参数/哨群/风控/汇报, 每条=规则+责任岗+机器验证+留痕处; 巡检哨 system_patrol_1119.py 逐条机械验证, 全绿静默/红件一行报+rd_queue 工单(责任岗认领, 同规则去重).
- 制度变更=L5 动作(李令/chief 拍板, 版本封版不删旧版); 执行率进周五验尸周报, <90% 红报李. 新增同类事故必问: 哪条制度接住它? 接不住=补制度+补巡检项, 不留"下次注意"型口头承诺.

## L5 直裁执行路径（李令指令 vs 冻结态文件冲突时）
- 李令最新明示指令（如"按最赚钱参数执行"）与冻结态字段（risk_freeze_state 的 RETIRE 硬拒、coin_freeze 等）冲突、且该冲突早已红报待裁时 = **本指令即终裁，立即执行，不等不请示**；执行后往冻结态文件追加 L5 覆盖留痕字段（决策者=L5 李令，执行者=主 bot，冲突来源注明），其余品种/字段照旧保留.
- intraday_policy 在场时：新开仓必带 12h 红线不过夜 → 进场后当晚注册次日清晨红线哨（one-shot），红线脚本窗口要 window-or-env-FORCE 可跨日（wrapper 里 `JINCE_REDLINE_FORCE=1`），别把单日夜间窗口写死成跨日 one-shot. **台账里的 redline_12h 戳≠执行者在案**: 开仓后必查 one-shot 红线哨/cron 确已注册可跑, 只有戳没有执行者=红线形同虚设, 销账时两件都要验.
- 执行崩了（terminal 非零退出）≠ 开仓失败也 ≠ 开仓成功：必须独立读 positions_get 验收，缺腿用幂等脚本重跑补（见下），别凭打印的 rc 汇报.

## 参数三处同步（防参数混乱的根因律）
改参数=必同步三处: ①spec 权威 JSON (data/param_spec_v4_earn_cell_20261117.json) ②参数表 practice_params_all_symbols.json ③哨脚本常量. 只改一处=混乱根源; 参数官 30min 哨自动检漂移, 漂移走 rd_queue 执行岗修, 参数官复检闭环. 参数改版时旧值封版进 spec 的 decommissioned 清单, 不许旧值继续流通.
**参数文件覆盖合并律**: 任何共享参数 JSON（锁利表/开单格表等）更新=合并写——先 grep 全部消费方读哪些 key, 保留旧字段面+注记新值来源, 整件覆盖=别的消费方静默降级（11-19 锁利深优覆盖丢 11-15 旧字段实踩, 修=从备份文件合并回全字段）.

## 哨脚本写法坑（新哨必过, 11-17 SOL哨三连 bug 教训）
- MT5 连接探测按 returncode/输出空判据; 拿 pid 数字串做特征匹配会误判"未连接"→去拉终端, 硬编码终端路径猜错=WinError 2. 终端真路径=`C:\Program Files\TMGM MT5 Terminal\terminal64.exe`（禁写 D:/MT5 类猜路径）; 拉起前先看进程防双实例.
- 币系哨必带 go窗 13-21UTC 检查, 新增品种哨禁止漏窗检（窗外=留痕不执行, 靠 cron 双拍补）.
- 开单前必须 position + pending orders 双查去重（magic+symbol）.
- **执行层幂等纪律**: 一次性开仓脚本（放 scripts/exec_wave/ 子目录, 禁引擎根目录）必须幂等=重跑时已有本波仓的腿自动跳过、缺腿自动补 → 执行崩后的恢复动作=直接重跑, 不需手写补单; magic+wave 写进开单 comment 供去重与追溯.
- **开仓后必独立读持仓验收**: 打印 rc=10009 OK ≠ 该腿在账——内部处置进程可能数分钟内瞬平（coingate/L4 类, 同 12h 红线流程）; 腿消失=幂等重跑补开 + P1 取证工单（取证=验尸岗, 定位平单方=研发岗, 平单方若合规但漏登记=执行岗补账）. **立 P1 前先对锁利守护日志 `data/sd_profitlock_log.jsonl`**: 平仓价==守护推的 new_sl + 有对应"锁利: 峰值X R->锁Y R"行 = 锁利设计内服务器端 SL 触发（正面事件, 报实收 R 不立单）; 守护日志无对应行才走 P1 取证（本条曾开出假 P1 后销账, 对账前置可省一轮错账）. 另 MT5 history_deals_get 有同步延迟+服务器钟偏移, "没看到平仓 deal" 不等于"没被平", 以 positions_get 为持仓真值. **查成交两条可执行修正**: ①查询窗口按服务器钟构造=本地时间整体+7200s（不偏移=窗口整体偏早 2h, 近端平仓 deal 全查空, 表现为"平仓了却查不到记录"）; ②TradeDeal 无 `.position` 属性, 按票号过滤用 `d.position_id`, 直接用 d.position 抛 AttributeError.
- **仓数突增(0→N)先归因再定性**: 监控(MFE/MAE 等)报仓数突变不 panic 也不判 rogue——先 positions_get 实读归因(magic+comment+票号+开仓时间+开仓价), 再查开单登记台账判合法/违规; **白名单开单登记在 `data/task_ledger.jsonl` + `data/order_lifecycle.jsonl` 侧, 不在 task_ledger.json**(两文件并存, 查错文件=漏归因, 空结果别下"无登记"结论); 判为合法 L5 波后, 把覆盖口径回写 risk_freeze_state.json(追加 override 字段, 注明决策者/执行者/冲突来源)再收口.
- **tf_cache npz 无预算 'atr' 键**: M30 npz 只有 t/h/l/c, 现场 ATR 重锚须用最近 15 根真区间均值（tr=max(h-l,|h-pc|,|l-pc|), pc=前收拼接）; 直接读 m["atr"]=KeyError 崩脚本. ATR 会漂移（日内可宽 50%）, 开单必现场重锚 R, 不用昨日常量.
- 探测超时 30s 冷挂载会假阳性, 用 90s.
- **cron `script` 参数只认 `E:\workbuddy\国外模型\hermes\scripts\` 目录**: 引擎内脚本挂 cron=先在该目录写包装器(subprocess 委托 3.13.12 解释器 + env 带 PYTHONIOENCODING=utf-8, 常驻守护类才走 Windows 计划任务), 包装器静默守则: 无开仓/全绿=空 stdout(=什么都不发), 有动作/故障才打印(非零 rc=自动 error 告警), 防空交付哨刷屏.

## 踩坑铁律(11-17 21:00三腿未执行根因解析, 防再犯)
- **tick新鲜判据禁用绝对时差**: 经纪商时钟偏本机+2h(7200s), `abs(now-tick.time)<120` 恒False=每拍必跳; 一律改 **feed活性5s双采样**(t2.time>t1.time=活, 不依赖任何时钟)
- **执行层解释器基准=3.13.12**(`D:/workbuddy/binaries/python/versions/3.13.12/python.exe`, 含MT5实证); jince_sass/.venv(numpy断链)=只许研究层, 包装器grep到jince_sass=哨体检报警
- **MT5 Python API 纪律**: `positions_get()/orders_get()`(返回tuple, 配 `or ()` 兜底), 禁`positions_total()`(返回int不可迭代); 填充模式=`symbol_info().filling_mode`位运算(4=RETURN/2=IOC), 此版本无`filling_mode_all`
- **新哨脚本三铁律**: ①照三哨模板写 ②py_compile ③go窗外干跑一次(预期输出SKIP)才许挂cron; 写完不验=cron静默崩
- **限价通道10015长病**: GTC挂单恒rc=10015(全品种全距离), 市价降级通道正常; 挂单失败必自动落市价(哨内置)
- **数据官挑活排序键反转=主力饿死(星饥饿 bug 类)**: 主力品种优先的排序键若写反(如 `x in 主力` 升序时 True 排后=非主力优先), 节流每拍定额名额被杂件占满, 主力 K 线缓存饿到 15h+, 次日清晨破 48h 五验 FAIL 线. 修排序/优先级选择码后必实跑一拍+回归验主力 npz mtime<2h, 静态 review 不算修讫; 报红件时给"距 48h 线还有几拍"的量化余量.
- **用户报"停了一天"先扫 cron 群 last_status**: 网关更新/重启（draining）会批量中断 agent 型 job（last_error=interrupted / Gateway draining, 无 agent 脚本型照跑）; 若"故障补跑哨"这类自愈机制本身躺红, 崩掉的一次性执行会整日无人补=假停机根因. 检修=先手动补跑漏掉的 L5 动作, 瞬态红哨不杀网关、下拍自愈, 逻辑错红哨才修脚本.
- **重复哨降级=改提示词不删 job**: agent 型与脚本型哨职责重叠（如故障补跑 vs fail-scan）时, 脚本型=确定性主层保留, agent 型用 cronjob_manage 改提示词降为"红件复核层"（仅确定性层报红才介入, 全绿静默 exit, 禁重复其活）, 留 job 留痕可再升.
- **cronjob_manage 改任务=action='update'+job_id 参数**（'edit' 是 unknown action, 传 'id' 报 job_id required; list 结果超大走 spillover 文件+execute_code 解析, 别重拉）.

## 当前裁定(spec v4 赚钱格, 前向攒样中)
- BTC/ETH/SOL: SL=0.8×ATR30 紧损 + TP=3R（spec 唯一赚钱格；高流动性宇宙复验批中 SOL 格证据 4/6→3/6 降级、BTC/ETH 3/6 = OOS 测试段不保正，前向 30 笔 OOS 继续攒，⑥线+chief R11 双裁才翻闸）
- 宽损/结构极值/进化宽参=REJECT封版; 余8品种无过线格=不动
- 风险帽撤(李令11-17), 1.0 lot冻结, REAL零动
- 哨: soul_wave/slv2_eth/slv2_sol 三腿双拍(21:00/21:30型), 参数官30min watchdog哨(静默=正常)

## [11-18 jevo复核] 刷新数据后赚钱格网格复验(0LLM确定性, 数据官75/75 npz后)
- 复验命令: `D:/workbuddy/binaries/python/versions/3.13.12/python.exe research/all_symbols_deep_opt_20261117.py`(11品种×SL{0.5,0.8,1.2,2.0}×TP{1.5,2,3}同分母, 扣0.095R, OOS70/30, ⑥线1.0), 产物 data/rd_verify_batch_all_sym_deep_20261117.json(卷按generated戳认新旧, 重跑前备份prev)。
- 11-18 00:58卷裁定: **唯一过线格=SOL sl0.8/tp3.0=4/6 WATCH(OOS双正 net+78.0 delta+145.9)**; **BTC/ETH同格=3/6 REJECT(OOS测试段未双正, net+61.9/+91.9但后段不保正)→不放大继续前向攒样**; 余8品种(含KSM刷新件)无过线格全REJECT=参数表一字不动。
- 宽损4.5/7.0基线三币net全负(BTC-29.4/ETH-28.8/SOL-68.0)=再证封版裁定正确。
- 前向OOS实读口径: MT5 deals按magic(20261104/30261103/30261106)+comment(OOS30/deep_opt/sl_spec前缀)计数, 11-18 01:0x=0/30(⑥线未翻, 翻闸仍走chief R11双裁)。
- 参数表mismatch族: 表内sl4.5/tp7.0≠spec 0.8/3.0由参数官30min哨消费(param_officer_mismatch_*工单), 回测base读表值不影响网格裁定(格点扫全SL/TP), 但挂单执行必须等mismatch销账后核表=spec再开新波。**写冲突变体（翻表后被另一写侧推回旧值）**: 参数官"已修"后表仍回弹=存在竞争写者, 修法定位写侧（文件 mtime + 内容指纹 + 谁在写=进程/任务归因）先阻写再翻, P1 工单; **agent 型写侧（LLM 工具调用写文件, 静态 grep 全只读、mtime 对不进程）= 用 OS 只读属性堵: `attrib +R <表>` + 实测追加写（Permission denied=堵成立）, 合法重写路径（参数官哨）先 `attrib -R`+留痕再写, 竞争写者下次写必失败=必暴露**; 阻写落地前每次开新波前必再核一次表=spec（翻过的表≠表还在值上）. 注: 回测网格对竞争写者免疫（格点扫全 SL/TP 不读表 base 裁点）, 只有"表值=挂单执行源"这条线要护.

## 深度优化12轮战役配方（李令『深度优化10次以上』类指令直接走）
- 脚本: `research/deep_opt_campaign_1119.py`（jince venv, 确定性0LLM, 30日M30同分母口径）: R1-R6 六个连续30日窗×12格稳度矩阵 → R7 精细30格(sl0.5-1.0×tp2.0-4.0) → R8/R9 两邻域精调(±0.1/±0.25) → R10 0.15R压力+5折同向 → R11 锁利并轨对拍 → R12 终裁（稳赚格=gate≥3且OOS双正且窗稳≥4/6且压力正且5折≥4/5；否则WATCH前向攒样）+ top3格逐格6窗口补算。
- 坑: ①`_cell`返回二元组; ②格串解析用parse_cell(a[1][2:-1]剥TP前缀, 直接float("TP2.0")崩); ③精细格无窗口稳定记录→R12必须现场补算6窗, 否则稳赚格永远0; ④全量npz 30000根=633天, t是秒级epoch, 30日窗=W30=1440根, 窗切片后P['n']须重算; ⑤30日口径与全历史口径数字不可比（n差3倍）, 汇报必注口径。
- 11-19战役裁定（留痕 data/deep_opt_campaign_1119.json）: 稳赚格=0（全格窗稳≤2/6=参数随regime切换, 一套打天下不存在）; WATCH攒样格5个= XAU SL0.9/TP3.75R最强(gate4/6 净R+9.3 胜率0.57) / KSM SL0.8/TP3.0R(+8.0) / LTC SL0.5/TP2.25R(+6.8 OOS双正) / ETH SL0.6/TP2.0R(+3.0 OOS双正); BTC旧赚钱格30日口径窗稳0/6降级; US30/SOL全REJECT。= spec v4.1提案走rd_queue（P2, 参数官写表, ⑥线30笔照旧）。

## 灵魂门全市场扫描+自动开仓配方（李令『全面分析行情,有行情就开』类 L5 指令直接走）
- 脚本对: `research/soul_scan_1119.py`(确定性扫描, 全品种 M30: D1方向=近12根收盘斜率 + 近48根内20根区段扫掠(刺破前高/前低收盘拉回) + 扫掠后位移≥0.6×ATR30且方向与D1一致; 位移在近2根=market可开, 否则=limit_at_sweep挂单位) + `scripts/exec_wave/auto_wave_soul_1119.py`(过门且market=市价进赚钱格0.01, SL/TP币三=spec v4余品种=参数表, 开仓即写 order_lifecycle + _manual_prac_log + 台账, 末了 positions_get 独立验收).
- **有行情就开=条件单不是无条件开**: 0 信号过门=不动手+挂自动哨(事件反应拍: 数据落地+5min, one-shot 扫描开仓; 事件冻结窗内只开币系宇宙, JPY/金/股指排除), 绝不硬开凑数; 有单报单无单静默.
- **确定性扫描首跑必做 2-3 例物理合理性抽查再认结果**: 现价 vs 扫掠位差/ATR量级对不上=索引 bug 不是 0 信号(本配方曾两连假: ①npz 文件名剥品种名=8字符"_M30.npz"不是7, 错剥=全品种 file-not-found 假 0 信号 ②扫掠循环用窗口相对索引 i 配全量数组 hi20_prev[i]=拿数据开头的价格比近端位移=假 5 信号); np.bool_/np.float 进 json.dumps 必 int()/float()/bool() 强转否则 TypeError.
- 限价挂单位(limit_at_sweep)受 10015 通道病限制不可挂, 只执行 market 型位移.

## 自主运行闭环（李令『给全部灵魂』授权: 开单/出场零人工触发, 11-19 建立）
- **双哨架构**: ①30min 巡市哨 `research/auto_soul_sweep_1119.py`（cron 563d32ec14a1）: 自动跑 soul_scan → 五闸（D4 尾龄≤2h / 事件冻结窗外 / 日位 guard BUY<0.97·SELL>0.03 / 同 magic+品种去重 / **R≥4×现点差防磨平**）→ 过线市价自动开单（开单格表 `data/auto_soul_params.json` = 赚钱格+12 轮战役 top1 分品种, 0.01 攒样级, 每拍≤2 开, ATR 现场重锚）→ **开单后 3 秒 positions_get 验收在账** → 12h 红线登记 `data/redline_registry.jsonl` + 到期自动 FORCE 处理 → 开单 stdout 立即报微信。②10min 出场反馈哨 `research/auto_soul_exit_watch_1119.py`（cron 40bfe6020e77）: 比对 `data/auto_soul_exit_snap.json` 快照检测仓位消失 → 按 deals 分类（锁盈/止盈/原止损/手动）**立即报** → 盈利侧出场重扫灵魂门: **同向信号仍有效且非冻结=当场市价再进场**（0.01 同格+红线再登记）, 反转/无信号=报『不再进, 观察』; 亏损侧=不追, 交巡市哨。
- 冻结窗**必须数据化**: `data/event_freeze_windows.json`（晨学哨可追加, scope=all/JPY/FX/COIN）; 窗口 ISO 带 +08:00 时区, 消费前 `.replace(tzinfo=None)` 对齐本地 BJT, 否则 naive/aware 比较 TypeError. **巡市哨每日 19-20h 自动滚动追加次日美数据窗(20:30-21:30 all), 冻结窗永不断供——窗靠手动加=还会留"要提醒"的口, 任何人工依赖点都是自主闭环的破口**.
- **开扫前数据自鲜**: 巡市哨与数据官同为 30min 拍=会抢到旧数据, 开扫前查参考品种(BTCUSD)M30 尾龄, >45min 先 subprocess 跑 `jince_data_officer.py` 再扫(失败=D4 尾龄闸兜底, 不崩).
- **出场哨再进场必须与开单同闸**: 再进场路复用 D4 尾龄闸 + R≥4×现点差防磨平闸 + 每拍再进场上限 1（连环出场≠连环开单）+ 扫描全哨只跑一次共享结果 + 再进场开单同样 3 秒验收在账; 闸不对称=磨平循环换个入口复发.
- **开单后 3 秒 positions_get 验收在账**（10009≠在账, 验收失败=报"验收失败立 P1"不静默）, 验收不过不写登记.
- **坑（11-19 实踩）**: ①soul_scan JSON 字段映射: 信号方向在 `signal`（"BUY"/"SELL"）, sweeps 键是 `UP`/`DN` 不是方向名, `disp_atr` 嵌在同侧 sweep 内——用错键=位移恒 0.0（排序/选单全废但脚本不报错, 首跑必抽查打印值量级）; ②`entry_type=limit` 型信号禁自动开（限价通道 10015 长病）, 自动开单只执行 market 型; ③平仓原因码: 锁利守护推 SL 后回踩扫出=reason 4（EXCHANGE/客户端平仓, **不是** 3）, 分类以「平仓价 vs 开仓价定盈亏侧」为主、reason 码为辅; ④紧 R 格活点差磨平循环: EUR 安静日格 R=3.4 点 vs 点差 1 点=成本占 0.3R, 锁利哨每轮只磨 +0.07 打转——开单格表选格必过点差耐受（R<5 点的外汇格默认降级宽一档或禁自动开, 验尸岗周材料）。
- 共享参数文件（sd_symbol_params/auto_soul_params 等）覆盖前必 grep 全部消费方读哪些 key, **合并写保留旧字段+merge_note**, 整件覆盖=静默降级事故（11-19 实踩丢 slc/tpmul 旧字段）.
- **rd_queue.json 是平铺 dict（key=工单ID, 值={id,sev,status,by,ts,task/...}）, 混着 items/ts/queue 等 meta 键**——往 `q["tickets"]` 列表里塞工单=写错容器（键根本不消费方不读）. 写共享 JSON 状态文件前先读一个样例键确认结构, 再选容器.
- **建新自主机制前先对现有闭环跑一轮自查**（李令"你先自己找出问题自己优化"）: 逐问——哪步还在等人工触发? 开单/验收/留痕哪环缺? 新旧路径闸对称吗? 数据缺口会让哪个下游静默降级? 查出的洞当轮全修再挂 cron, 别修一半上线.

## 每单 XP 进化系统（李令『每个单子都要有学习升级的经验值』立法, 11-19 上线）
- 聚合层 `research/order_xp_1119.py`（**零侵入**: 从 order_lifecycle.jsonl place/close 行自动配对, 不加新写点; 3.13.12 可跑, 需 MT5 只在自愈时用）:
  - 每单 XP: 基础 10, 盈利侧出场 +20（"会赢"）, 亏损侧 -10 罚 +5 "学到"（亏损=学习必附因果, 不斩除, 对齐李令进化制度）, 在仓=0, close 记录缺失=0 **绝不伪造**.
  - 格级状态机（键=品种@SL/TP 倍数, 标签归一化防同逻辑格被切碎）: n≥30 且净利≥0 且胜率≥55% → 自动立 `xp6_*` ⑥线翻闸工单进 rd_queue（参数官裁, 翻闸仍走 chief/L5 双裁）; n≥10 且净利<0 → `xdn_*` 降级/换宽档审工单; 其余=WATCH 攒样 n/30.
  - **close 行自愈**: 每日跑前把"已开但缺 close 行且不在账"的单从服务器成交合成补录（窗口含 +2h 钟偏移）, 窗内找不到=pnl=None 不计 XP, 只报补录行数.
  - 日报 cron `order-xp-daily-2015`（3ab72d570c2c, 每日 20:15 no_agent 报回微信）: 当日单/XP + 各格 n/胜率/净利/状态; 常规模式仅新增格级工单时出声.
- 坑: ①XP 聚合首跑必查"累计 XP 恒 0"=close 行缺失（旧单没留痕）, 先自愈再出数, 恒 0 的日报=假数据; ②格标签归一化（regex 抠 SL/TP 倍数, 抠不出查格表该品种官方倍数）, 不归一=同格被标签差异切碎, 30 样本永远攒不满.

## 高流动性宇宙（liq13）全面深优配方（李令『全面深度优化高流动性品种』类指令直接走）
- 宇宙/补K线/批协议/结构结论/四账注册/复验漂移口径见 `references/liq-universe-deep-opt.md`。
- 流程: ①state.cmd+tf_cache 新鲜度闸 → ②缺品种按数据官配方补 M30 → ③跑 liq13 批(3.13.12 确定性 0LLM) → ④逐品种裁定(禁跨品种平均) → ⑤四账+状态卡+Word 报告(走 docx 技能, 存 内容中心\交付\) → ⑥ 0翻闸0放大只报结论(翻闸=chief R11)。
- **用户同一指令连发多遍 = 催办不是重发**: 不重起计划不重铺说明, 一行『执行中·第几步』回稳, 一口气收到尾（长任务分段汇报时尤忌每段重新铺陈）。
- **复验漂移规则**: 每批深优必拿同格 gate 计数与上一批对账（如 SOL 4/6→3/6 = OOS 测试段转负），升降级注记进对应 rd_queue 件的 note，不推翻 spec（裁定权属 chief R11 双裁）；全宇宙 ⑥ 线 0 达标时『0翻闸0放大』是纪律正确不是失败，报告按此口径写。
