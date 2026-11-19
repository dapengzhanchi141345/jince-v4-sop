# 高流动性宇宙深优配方（liq13）

## 宇宙定义
liq12（11-13 R12 裁定）+ SOL（spec v4 赚钱格币）= 13 只:
AUDUSD / BTCUSD / ETHUSD / EURUSD / GBPJPY / GBPUSD / JPN225 / US30 / USDJPY / XAGUSD / XAUUSD / XTIUSD / SOLUSD
（终端名=缓存名，JPN225/US30/XTIUSD 在 TradeMax 60137964 账号均为可交易名。）

## 缺 K线补拉（tf_cache 无该品种 npz）
- 数据官 jince_data_officer.py 是 tf_cache 唯一 30min 刷新者，但其 75/75 名单不含新增品种 → 主 bot 一次性补拉（先例多次），照数据官配方:
  - 解释器 = `D:/workbuddy/binaries/python/versions/3.13.12/python.exe`（黄金法；env MT5_TERMINAL/MT5_LOGIN + MetaTrader5.initialize，15s 封顶）
  - 拉取: `mt5.symbol_select(sym, True)` + `mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M30, 0, 30000)`；**周期常量是数字枚举（M30=30）不是原始秒，传 1800 恒 Invalid params（见技能 mt5-live-read 周期常量条）**
  - 写盘: `np.savez_compressed(tmp, t=time.astype('int64'), o/h/l/c float32)` + pid-suffix tmp + `os.replace`；PermissionError=LOCKED 留盘下批（数据官会接力）；每批落 fetch 报告 json（bars/first/last/status）
- npz 的 `t` 存 server钟 epoch（与既有 npz 同轴）；时段闸/OOS 切分全在同一 t 轴上，整体 +2h 偏差不破坏同分母对比，不必重标定

## 深优批（确定性 0LLM）
- 脚本模板 = `research/liq_universe_deep_opt_20261118.py`（import rd_verify_batch_20261114 的 prepare30/gen_signals/simulate/five_gates/verdict_of，与 all_sym_deep 1117 批同分母）
- 协议: 每品种 SL{0.5,0.8,1.2,2.0}×ATR30 × TP{1.5,2.0,3.0}R（封顶 12ATR）12 格 + 顶格 giveback{0.4,0.8} 离场层变体 + 顶格重叠窗 13-17（存储 t 轴 hour∈[13,17)）时段变体；扣 0.095R（T5 压力档 0.15R），OOS 70/30 双段，winsor[-3,8]，⑥线净均R≥1.0；逐品种裁定禁跨品种平均
- 裁定映射: 全 T+⑥=APPROVE 候选 | ⑥不过但 ≥3/6=WATCH 前向攒样 | <3=REJECT；⑥不过一律不放大
- runner: 3.13.12 python（研究层可用 numpy）；全批约 1-2 分钟
- 产物: `data/rd_verify_batch_liq13_deep_*.json`（generated 戳认新旧，重跑前备份 prev）
- best 格选取口径: 按（裁定优先级 APPROVE>WATCH>REJECT → 五验分 → 净R）排序，格键解析 `SL{a}_TP{b}R` = a=key[0][2:], b=key[1][2:-1]

## 结构结论（每批刷新复验，勿当常数）
- 全宇宙最优 TP=3R、最优 SL 在 0.5-0.8×ATR30 紧损族（2.0 宽损族普遍全负）→ 印证 spec v4 赚钱格方向
- 时段窗变体（重叠 13-17）多为 REJECT/负 delta → 突破型事件集上时段闸不增值，与灵魂批『杀伤时段 OBSERVE 不放大』同口径
- 赚钱格 gate 计数随数据更新漂移：每批复验批必与上批同格对账，升降级注记 earn_cell 队列件 note，翻闸权属 chief R11 双裁

## 注册（四账, 0翻闸0放大）
- rd_queue +1 件: id=`liq13_deep_opt_YYYYMMDD`, status=decided_watch/decided_reject, five_gate=true, 字段=source/task/test_design/note；写入前 shutil.copy 备份 .bak_<tag>，按 id 幂等去重；升降级另注记既有 earn_cell 件 note 不新开重复件
- rd_watchlist + 键 `liq13_watch_forward_YYYYMMDD`（schema 照 liq12_watch_forward 件: status=WATCH_FORWARD_OOS/chief/items/gate/evidence）
- rd_ledger_24h +1 条播报（theme_cn/candidate/verdict/p4_gap 4 键齐 + heartbeat）
- task_ledger +1 条（DONE + evidence=产物路径清单）；状态卡 append 条目（大白话+四账+盘面时戳快照）
- 报告 = docx 技能（封面+目录域+彩色表+matplotlib 双图+页码），存 内容中心\交付\；图表 hex 颜色要 `#` 前缀（docx 技能坑条）
