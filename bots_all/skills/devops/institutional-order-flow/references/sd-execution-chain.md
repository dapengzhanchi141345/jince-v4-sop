# 金策 SD 批（供需区+锁利+分级强平）执行链 · 三方审查后状态

> 11-15 WorkBuddy 进化营/独立复验/御史三方审查：3 P0 全实锤（强平死代码/SELL 锁利反向/dry 不 dry）+ 回测口径三处系统性高估（前视选样/幽灵成交价/SELL 棘轮符号）→ 原 22751R/98.9%WR 与分品种参数表 v1 **全部暂停采信**，v2 重算中。本件=审查后唯一权威口径，旧会话记忆里的 v1 数字/参数作废。

## 策略（v2 口径，待 v2 参数表落盘后定案）
- 区 = Seiden 供需区 + 3:1 利润区闸 + Odds Enhancers 评分（sd_zone_oe_20261115.py 引擎，v2 重算引擎 sd_symopt_v2_20261115.py）
- 进场 = 近沿限价（sell@区上沿/buy@区下沿=挂单可挂侧；远沿不可挂，回测按远沿结算=幽灵成交价=高估主因）
- **v2 结算五口径**（御史裁定）：① 3:1 准入只用 前一日 H/L + 事件前当日 H/L（无未来）② 近沿限价挂价即成交价 ③ SELL 锁盈=SL 下移/BUY=上移（sgn 符号）④ 每单扣 COST=0.095R（点差+费）⑤ 12h 红线（未锁单 8 根 M15 强平）
- 锁利 = 峰值口径棘轮：peak≥trig 后锁位=peak-giveback（地板 0R），只紧不松，方向随 sgn；10s 一拍
- 强平 = 分级：锁利单（SL 已在开仓价另一侧）豁免 12h、24h 二道闸；未锁单 12h 照砍

## 执行链文件（E:/GoldstrategyEngine/research/ + E:/workbuddy/国外模型/hermes/scripts/）
| 文件 | 角色 | 审查后关键口径 |
|---|---|---|
| place_sd_all_20261115.py | 挂单器 | dedup=state in (0,1) 在册挂单(1=PLACED 活单)+本批即时入 existing；成功码收口 (10008,10009,10010)+res.order>0，10019=NO_MONEY 记 failed；type_filling=RETURN(PENDING 单)；stops_level 预检；完结日判据 (dk+1)*86400+900<=now（无半日前视）；zf 读 final 层 |
| sd_profitlock_guard.py | 锁利守护 | 峰值口径；target=open+sgn*lock_r*risk（buy+1/sell-1）；dry 门（--once 不发单只留痕）；open_risk 按品种+开仓价 2e-4 容差匹配 prac log（订单 ticket≠持仓 ticket！）+回退最近 open+warn；peak 每拍落盘 sd_peak_state.json+启动种子；OpenProcess 唯一锁；计划任务 SD-ProfitLock 1min 心跳 |
| scripts/sd_e3s1_12h_forceclose.py | 分级强平 | **平仓块必须 dedent 在 for 循环体（if-not-due 块内 continue 之后=死代码陷阱，改后必 AST 复核可达性）**；平 BUY=SELL@bid / 平 SELL=BUY@ask；重试刷新 tick；30min cron 92212bf4d61e 无持仓静默 |
| scripts/sd_place_fx_monday.py | 周一 21:05 全品种 | 步骤① allsyms_fetch 刷数据（失败=硬退出）② 重置同日区闸 state ③ 挂单 ④ 挂=0/败>0/[同日区闸] 三条 [ALARM]；env TMP 重定向 E 盘 |
| data/_manual_prac_log.jsonl | 留痕 | open/close 双写（锁利 R 基准源） |
| sd_symbol_params_v2.json | 参数表 | **v2 重算产物（跑完替代 v1）**；v1 sd_symbol_params.json 暂停使用 |

## 三方审查后的执行定位
- 周一 21:05 全品种挂单 = **执行链验证**（不是策略 OOS 通过）；策略 OOS 需 v2 重算 + 30 笔成交
- FX 该户 10015 禁挂单（11-05 台账）/ 股指 22:30 北京才开 / HK 已收 = 预期内败单，按品种报清单，FX 禁挂→提经纪商开 pending 权限或改市价触发
- 同刻任务错峰：jince-node 21:05 与 SD 任务 21:05 同秒=MT5 IPC 争用，SD 侧已避开（21:05 单任务）
- **盘中二道波补挂（11-15 定式）**：全品种挂单任务的预期败单（FX 该户 10015 禁挂单 / 美股 22:30 才开 / HK 已收）**不等次日**——排在「全市场开市后」的二道波重跑同一脚本：dedup state∈(0,1) 自动跳过已挂、只补败单品种；数据刷新+同日区闸 state 重置都是幂等步，重跑安全。首波 21:15（错开 21:05 的 jince-node 美盘开评）→ 二道波 22:40。

## MT5 执行层坑（审查核过，别再犯）
1. **dedup 只认 state==0 = 恒空集**（MT5 ENUM_ORDER_STATE: 0=STARTED 未受理/1=PLACED 在册活挂单；失效撤单=从 orders_get 消失）。叠单防护=在册(0,1)+同日区闸两层各管一层
2. **10019=TRADE_RETCODE_NO_MONEY（不是成功）**；挂单成功集=(10008 PLACED,10009 完成,10010 已挂) 且核 res.order>0；资金不足记 failed 不 phantom open
3. **PENDING 单 type_filling 用 FOK/IOC 均非法**（10030），用 ORDER_FILLING_RETURN
4. **for-else 静默洞**：break 跳过 else → 10014/10018/10019 终态必须 break 前显式 failed.append，否则该品种既不在 placed/skipped/failed=静默消失
5. **订单 ticket ≠ 持仓 ticket**（限价成交后不同）——锁利风险基准按 品种+开仓价 匹配（容差 2*tick，非 1e-6 精确价）
6. **sell 锁盈 = SL 下移**（open-lock_r*risk）、buy = 上移；SL 同价=0R 地板也算已锁；10016 预检 bid/ask 方向：buy SL<bid / sell SL>ask
7. **10018=市场未开；10015=该账户挂单被禁（pending forbidden，别当 stop level）**；价格 round 到 symbol.digits
8. **唯一锁判活用 OpenProcess（秒级）**：CIM/wmic 嵌套 PowerShell 冷启动 30s 超时被 except 吞 = 锁静默失效双开
9. **周末态**：挂单请求可能 10009 受理但挂单秒失效（state=1）——开市前挂的全是死单，统一放全市场开市后

## 审计方法论坑（三方实锤）
- **字符串断言式深检对死代码也 PASS**（关键词在文件里≠逻辑可达）：强平死代码被 9/9 深检放行的真因；修后验证=AST 解析核对语句可达性/缩进层级，或行为级用例（mock MT5 发单记录）
- **单测手写数学公式 ≠ 验代码**（公式写对了、代码符号反了照样 PASS）：结算类引擎单测必须用真实代码跑确定性 K 线序列断言
- **外部审查结论先核源码再采纳**（三方本次 3 P0 全部实锤，但其中 dedup 方向我此前改反过一次=审查件与现场代码要逐条对行号）
- **同日区闸=zone-dk 闸**：数据不刷 dk 不前进→整批 skip；周一任务先刷数据+清 state，刷新失败=硬退出（最坏组合=数据没刷+闸拦=0 挂单静默）

## 验收口径
- 全链深检=E:/workbuddy/国外模型/hermes/scripts/sd_fullchain_audit.py（9 项 C1~C9，**断言随修复同步更新，修 bug 前先核对断言不是写反的**）
- 策略 OOS=v2 参数表 + 30 笔成交同分母；锁利动作看 data/sd_profitlock_log.jsonl
