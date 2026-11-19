# 只读读外部账户 & 归档规则 深度

## 只读读外部 MT5 账户(2026-10-06, 客户实盘 81223578 实例)
用户发来第三方账户(客户实盘号)要"深度分析/学习做单思路"时, 这是**只读任务**, 铁律: 零交易动作(不 order_send/撤单/改 SLTP), 账户密码不落任何留痕文件/群消息(机密例外), 分析完该会话 MT5 连接即关闭、引擎账户纹丝不动。
**① 引擎终端是共享单例会(白标 TMGM), 绝不切它走 — 走独立终端(独立 datafolder):** 优先 attach 用户为外部账户装好的独立终端(如 `E:\mt5_friend_observer`, 用户手动登录), agent 不自起/不杀 terminal64 — 完整规则见下方「只读拉客户账户的正确姿势」节; 无用户终端时才自起 guest 实例且全程只起一次不死循环。guest 冷启动首次 login 常报 `-10005 IPC timeout` 但 account_info 已读到目标账户 = 半连上, 等 5-10s 或重 login 一次即全通, 别当失败。
**⚠ 只读拉客户账户的正确姿势 = attach 用户已装好的终端, agent 不 spawn/kill 任何 terminal64 (2026-10-06 三轮失败后定):** ① **绝不自己起/杀/重启 terminal64 实例。** 用户已为外部账户装好独立终端(独立 datafolder, 如 `E:\mt5_friend_observer`), agent 只做 `mt5.initialize(data_folder=该路径)` attach + 用户手动登录 + 只读拉数; 反复 spawn/kill/IPC 探活 = 终端翻车 + 引擎终端 IPC 被连带带崩 + 用户其他账户也登不上 的根因, 一旦动手 churn 过就认账停止, 不再试"再拉一次"。动手前先枚举 `wmic process where "name='terminal64.exe'" get ProcessId,CommandLine` 分清三类: 引擎默认终端(无 datafolder 参数, PID 会随终端自重启变化, 不碰) / 用户外部终端(带用户 datafolder, 本次 attach 目标) / agent 起过的 guest 残留(带自己 datafolder, 一律 taskkill 清掉并停止再用该方式)。`mt5.login` 偶发 10003 多为该终端数据目录仍在同步, 等 20-30s 再试一次即通, 别换终端别重起。② **"登录成功"判据 = `account_info().login == 目标账号`, 绝不用"余额≠0"当闸。** 刚登录的终端余额常读到 0(数据未同步完), 拿余额当闸门 = 死循环空转不拉数(本次三轮卡死即此 bug); 余额 0 也可能是账户实况, 成交流水/账户健康与余额是两码事, 余额为 0 照常拉 history_deals。③ **所有 terminal64 IPC 探测带 timeout, 输出逐行 flush。** 裸 `mt5.initialize()` 挂起会让一条命令烧满超时(本次 90-120s 连烧三条), 探测一律 `timeout N python -c` 形式且 20-30s 即判, 判不通立刻停而不是循环重试。④ **用户报"我的其他账户也登不上了" = 我的终端 churn 事故, 处置四步: 先验引擎 demo 账户仍可读(红线确认), 立刻停止一切终端起/杀/登录尝试(再试只会更乱), 让用户在自己终端手动重新登录, 之后只 watch 引擎 30min 全链心跳自动自愈; 不代登不重起不补探。** ⑤ 拉数脚本登录循环的"放行判据"写死为账号匹配, 禁止写余额/净值类判据。登录参数以账户截图为准: 服务器名=账号标识串(如 ECMarkets-MT5-Live01), 账户号+密码用户会给(密码只用这一次, 读完全程不写盘不落留痕)。
**② 全量历史分段拉, 别一次拉 2020 至今(必超时):** `history_deals_get`/`history_orders_get` 按 180 天一段循环拉, 每段以 `ds[-1].time` 前进; 拉完先落盘再分析(拉取与分析分离, 中途崩不丢已拉段)。deals 比 orders 信息全(entry/profit/swaps/commission/reason 齐全), 做单思路分析主看 deals, orders 补挂单/撤销行为。
**③ 做单思路拆解五问(从 deals 实数算, 不凭印象):** ①分时段胜率+期望R(同分母) ②多空比例与持单时长分布 ③止损兑现率(触 SL 占比)/止盈兑现率/扛单率 ④单笔风险占净值比+单日最大连亏 ⑤品种集中度和 hedge 对锁习惯(该账户是 Hedge 模式)。结论必带丑话: 历史回测≠未来收益, 且这是别人的账户 — 只学思路不碰他的单。
**④ 收尾:** guest 终端 `mt5.shutdown()` + taskkill 隔离实例(别留后台挂客户账号连接), 临时拉数脚本与 _guest_analysis 留盘作留痕(数据本身非机密可留, 密码绝不留)。

---

## 归档实时数据文件 踩坑(2026-10-05, 全面体检误归档致研判崩)
"数据文件超期归档" 不能只按"文件 mtime 老"判断该不该归档, 必须先扫实时脚本 import 链是否还在读:
1. 用正则扫 multi_agent/trading/*.py + 根 *.py 里所有 "xxx.json" 引用, 得到 refs 集合;
2. 只对 refs 里"不存在于 data/" 且"存在于 data/_archive/" 的文件才回血(不能直接删/不能只按 mtime 归档);
3. 判"哪些文件是实时账本"的正确方法=被 ≥1 个实时 py 引用, 而非"文件新不新"。
本次误归了 47 个实时账本(symbol_universe.json 被 daily_advisory.py 读 → 研判节点 FileNotFoundError 崩), 全回血后研判 exit=0、全链绿。铁律: 任何"清理/归档"动作前, 先跑一遍 refs 扫描, 把被读文件排除, 只归档 refs 里没有的。
