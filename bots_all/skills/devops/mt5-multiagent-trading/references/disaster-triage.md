# 基础设施丢失事故 · 分诊与恢复 (金策全链)

机器 user context 变化(重装/换用户/profile 删除)会把挂在旧 profile 下的 ATE 解释器、引擎 terminal64、本地仓、gh CLI、凭证一起带走; E:\ 下的数据(引擎 data/、workbuddy、内容中心)通常全活。症状 = 全链静默断 N 天 + 大量 job 报 `GatewayUnavailableError` / `[WinError 2]` / "MT5 实读 0 品种"。

## 定性五连查(按序, 全对才定性, 别先动手)
1. **系统时钟自洽**: `date` 全行 + `date +%s` 对照 — 先把"停摆 N 天"算准(旧对话上下文停在几天前时极易算错天数); 时区文件落盘 mtime 与 epoch 不一致 = 时钟漂, 先别下停摆结论。
2. **全链断点**: `data/tick_live.json`、`data/auto_cycle.log` mtime + auto_cycle.log 末行"[全链自动运行完成]"时刻 = 断链起点; tick_live 停更早 = 行情喂先死。
3. **执行层在不在**: `Get-Process terminal64`(引擎终端)+ 引擎终端安装目录 + ATE 解释器父目录(`.workbuddy\binaries` 一族)。
4. **工具链**: `where gh` / git 位置 / 可 import MetaTrader5 的解释器逐个探。
5. **gateway 腿**: `gateway-starts.log` 末行 epoch + gateway pid 活不活 + 监听端口。
5 项全丢 = 路径丢失事件(基础设施层红), 与 IPC 瞬时抖(终端活着、 initialize 秒通)、gateway 单点故障(其它数据新鲜)三选一, 定性不同处置完全不同。

## 告警洪流分诊(恢复后 cron 连环 flush 积压旧失败)
- 每条 `GatewayUnavailableError`/`readonly database` 告警先核三样: ① 该 job 输出目录里最新 .md 的 mtime; ② gateway-starts.log 末行(最近一次拉起时刻); ③ gateway pid 活着/监听端口在不在。
- mtime 早于最近拉起时刻 = **旧账**(down 窗口里的失败, 恢复后被投递层补发), 一行销账不重诊; 只有拉起时刻**之后**的新失败才算二次掉线。
- 拉起后 ~1min 内 `GatewayUnavailableError: Gateway starting: deadline` = 启动窗内没 ready, 正常, 不算抖; `service_manager_unavailable` = 那时进程根本没起。
- 销账口径已定过的重复模式(readonly/WAL 竞争), 同类型 N 次只记"第 N 个撞点", 不逐条重跑诊断; 只有 job body 落盘非 silent(真跑挂)才升级。

## 广播/播报"缓存冒充活态"
停摆期间 LLM 生成的播报(群主持/效率播报/综合大会/周会)会把 2-6 天前 mtime 的旧数据报成"全链绿/系统活着/mt5=running/下一场 xx 开评"。**对 LLM 层的"绿"一律以磁盘实数为准**: 文件 mtime、进程列表、日志末行、`gateway_state.json`。播报里的"最后心跳 @ 10-xx 19:01"= 断链起点实锤, 不是"系统活着"。

## 恢复分工(排 23:00 窗口执行; 恢复期间账户/挂单/净值都在券商侧, 等待 0 损失, 不必抢白天)
**可自动**: ① 重建 MetaTrader5 解释器 — 找任一可用 python(hermes 自带 3.14 等), 先 `pip download MetaTrader5` 验 cp 版本 wheel 存在再装(3.14 有 cp314 wheel, 5.0.x 支持); ② 重指各脚本里写死旧 profile 路径的引用(ATE 解释器、本地仓、stamp 目录); ③ 补跑确定性脚本。
**需用户动手(不代办)**: 引擎终端重装/手登 60137964(登录铁律, 禁止代登); gh CLI 重装 + `gh auth login` 或供 GitHub token(不翻旧凭证)。
**顺序**: 解释器 → 用户登终端 → 跑确定性探针(实读账户/挂单去向)→ 拉全链 → 修 12 站部署(gh)→ 验收 gateway。

## 一次性闹钟漏响补跑(如 DST 生死测定时拉数)
确定性"仅目标日期真跑、其它日期自动跳过(防误触发)"的闹钟脚本, 目标日 LLM 腿因 gateway 挂而漏跑时:
- 当天 terminal 直跑该脚本即可补上(0 LLM、只读探针、自带日期闸), 判据 = 结果文件不存在且今天==目标日期; 跑完派风控/研发销格回填(脚本本身不解除冻结令)。
- 次日再跑会自己打印"非目标日期, 跳过", 不会误触发 — 所以只要结果文件没落, 目标日当天补跑永远来得及(当天内), 跨天就只能顺延下一年度/下一触发点。
