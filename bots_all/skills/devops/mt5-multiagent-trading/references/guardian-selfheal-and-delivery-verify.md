# 看守自愈 + 交付验活 + rd_queue 工单派发（11-14 类级运维）

## 1. boot_guardian.py 自愈语义与验活
- `self_heal(component, fn)` 统一入口: 计数**内存态**(进程重启=天然清零)。
- 11-14 修复(备份 `boot_guardian.py.bak_window_1114`): ① `SELF_HEAL_WINDOW=600s` 滑动窗: now−last_fail>10min 计数清零(日志 [HEAL-UNLATCH]); ② fn 返回 **None**(ensure_jince_bot/ensure_auto_run_cycle 无 return 值)视为"已尝试"不计数, 显式 False 才递增——旧码把 None 当失败, 组件缺席每 60s 误计一次, 5 分钟必 latch; ③ 本机不存在的 4 个 legacy 任务名(JinCeWatchdog/JinCeBotSelfHeal/JinCeAutoCycle/Hermes_Gateway)的组件改 `log_once`(1h 去重)只记不拉不刷警报; mt5/event_guard/gateway 仍走 self_heal; ④ gateway 匹配器 `["hermes.exe","serve"]`→`["hermes_cli.main","--profile"]`(实际网关=`python -m hermes_cli.main --profile ...`)。
- **L5 规则**: jince_bot 组件(10-19 equity runner `--execute`, 实盘进程)缺席时只 log_once, DIRECT backstop 已禁用——自动拉起实盘 runner=越 L5 红线; 复活 runner=李彦明拍板。旧码危险标志=`data/logs/boot_guardian.log` 出现 "jince_bot runner DIRECT backstop launched (equity=...)" 行。
- 看守重启验活序: py_compile → taskkill /F 所有 boot_guardian pid(原生单斜杠参数) → sleep 30-60s, _guardian_watchdog(CHECK=300s) 自动拉新实例(可能同秒多守护同秒抢拉=双实例, 属既有现象, 去重另立工单; 验孤儿已清 = 进程列表仅剩 1 个 live24 pid + 锁文件 owner pid 与之匹配 + bridge 状态文件 status=connected(活体判定仍以锁 ts 心跳为准)) → 验活=新 pid 在列 + `data/logs/boot_guardian.log` 出新行(⚠ 日志在 **data/logs/** 下, 不是 data/ 直下) + alerts.log 无新 [SELF-HEAL LIMIT]。
- 终端重启窗(每 ~2h 自重启)后固定检查: grep alerts.log [SELF-HEAL LIMIT] + 锁文件 ts 心跳。

## 2. 交付验活哨 jince_delivery_verify.py（「表面说结果, 代码空白」的机器保障）
- 路径 `E:\GoldstrategyEngine\scripts\jince_delivery_verify.py`, 确定性 0-LLM(纯 stdlib, 任意 python 可跑); 输出 `data/delivery_verify.json` {ts,n_checked,fails,warns,clean}。
- 检查面: ① task_ledger status=DONE 任务 → evidence 必非空, evidence 条目含本地路径(E:/...)则文件必须存在且非 0B; ② rd_queue 关闭族(done/closed*/spec_landed/forward_contract_landed/sop_landed/decided/reject*/design_approved*/risk_officer_verdict_delivered/reverify_done*) → task+note+accept 拼接 ≥30 字, 过短=存疑; ③ data/rd_verify_batch*.json 全量 → 可解析 + ≥300B + 含裁定键之一(theme/items/per_sym/five_gate/verdict/summary/plain_summary/results), 缺键只 warn; ④ **[11-15 新增] 深研拍-日志对账**: research/ 内 48h 内深研产物(文件名含 arbr_/soul_/hourwindow/fx_gold/p5_orb/orb_confirm/deep_study, 取文件名 8 位日期)必须有 family_deep_study_log.jsonl 同日 ts 行, 缺=FAIL 假交付嫌疑。深研产物命名变体出现时扩该 regex, 否则新族产物漏出对账面。
- **LLM 截断拍（'Response remained truncated after N continuation attempts'）→ 确定性脚本替代**: 汇总/rollup/机械整理类 LLM cron 拍反复截断=任务形态错了(读多写多+长群报), 修法是新建 no_agent 确定性脚本接管同类活(读台账 jsonl→分类落 playbook json→只开 rd_queue 工单不擅改引擎码→stdout 大白话总账+内容 hash 去重门, 稳态空输出)。**一次性 LLM 拍失败即焚**(enabled=false/state=completed 不可 update), 替完活后把教训写状态卡铁律: 同类拍以后一律排 no_agent 版(实例: 深研 R4 汇总拍挂→jince_r4_rollup.py 替代讫, playbook.json/rd_queue 工单/群报三件已落)。
- **LLM 拍「已落盘」宣称必实查才销账**: 分品系深研类 LLM 拍连续三拍宣称「family_deep_study_log 追加/第 N 行」均未落盘(产物 json/脚本/playbook 都在, 日志没写)——宣称不可信, 主 bot 收口前逐条实查(wc -l + tail 目标文件), 假宣称=主 bot 按留痕铁律补记(含补记说明)再销账, 同时把该族产物加进检查面④防第四次; 只销「产物+日志」两齐的账, 缺日志的账标 redo_flag 等验活哨下轮查销。
- 回派规则: 7 天内 fails → 自动生成 `redo_<src>_<ref>_<date>`(priority 1, queued, 验收话术="交付物真实存在且非0B+关键字段可解析+哨复核通过"), 按 ref 幂等; >7d 旧账降 warns 只留痕(防刷屏)。首跑实测: 47 批产物 0 坏文件, 抓到 5 件旧「DONE 无 evidence」。
- 噪声校准: warns 多(历史批次自定键)是常态, 只看 fails 发声; 挂 cron 时 no_agent 静默口径=clean 空 stdout(watchdog 模式), NOT-CLEAN 才出声(与对话框瘦身铁律同族)。
- **使用铁律**: 报「已派发/已完成/已验活」前先跑一次(或读 delivery_verify.json)——宣称必须带验活把手(可实读的文件+关键字段+可重跑命令), 无把手=未完成。

## 3. rd_queue 工单派发形态（让「深度优化」变成可机械执行）
- 研究课题进 rd_queue 后别留纯研究 prompt, 升级成工单再派: owner(责任岗) + task 写死目标代码位置/新常量名/默认值(缺省=旧值, 先观察模式只 log 不拒单) + 回退开关(删常量/mult 置 1.0) + 五验口径(同分母+扣 0.095R+OOS70/30); status=queued, five_gate=true, 备份 `.bak_<tag>` 后 json 整写, 按 id 幂等。
- 话术原则: 全部「只否决/降档, 不放大开单」; 翻闸=risk-officer+李彦明双裁(L5); 观察期数据(前向 n 笔/log 计数)写进 accept。
- 实例(11-14 webgap 系列 5 件): ADX 逐品种阈值扫描 / 离场 MAE-MFE 面板(配 exit_panel.py 自动裁定: 族样本≥30 且中位效率<60%→离场修复课题) / 事件窗成本闸(EVENT_COST_MULT 3x) / JPY 干预标签源(BOJ 议息+干预新闻→L4 升级源) / 币系 12/5 门(周末降档+16-17UTC 点差>2x 拒)。
- 离场面板 `E:\GoldstrategyEngine\scripts\jince_exit_panel.py`(确定性 0-LLM): 吃 mfe_mae_track.jsonl, 逐族 medMFE/p90|MAE|/效率, 异常 R(|R|>50) 剔除计数留痕; 口径注意: p90 取 **|MAE|** 排序(裸 MAE 为负值, 直接分位=最不不利端, 指标会反), 全量数据需接 MT5 历史 deals 导出后切换。

## 4. Windows 进程取证（MSYS/PowerShell 坑, 11-14 连踩）
- 活体判定统一 `Get-CimInstance Win32_Process -Filter "name like 'python%'"` + CommandLine 匹配(全表 -Filter 预筛必带, Where-Object 全扫超时); git-bash tasklist 看不到 pythonw 命令行 → 假阴性。
- 引擎活体指征 = `data/live24_magic_<magic>.lock` ts 心跳每轮在刷(日志 mtime 次之——新实例 stdout 重定向目标可能没变, 旧 mtime ≠ 死)。
- PowerShell 诊断: 写 .ps1 + `-NoProfile -ExecutionPolicy Bypass -File`; 内联 -Command 双引号串里 `$_`/`$env` 被 bash 先展开(变成上个位置参/路径), 必炸。
- 原生程序参数单斜杠: `taskkill /F /PID n`(MSYS 转换关闭, //F 原样透传报「无效参数」); 但 bash 侧 `cd /c/Users/...` 等内建仍可用。同族: `cmd //c` 只是 git-bash terminal 工具形态, 原生 Python `subprocess.run(['cmd','//c',...])` 里 cmd.exe 不认 `//c` = 命令不执行且静默失败, 原生路径一律 `/c`; 巡感/快照脚本调 `cmd /c` 后必 dry-run 一次看产物 mtime 证真跑了——「拉起了」≠「执行了」。
- 杀进程后验新实例: 等 30-60s 再列(看门狗接力窗), 引擎重拉前轮询到旧 pid 真没了(锁残留窗, 见 SKILL 引擎节)。

## 5. 冻结/退役类闸的跨引擎覆盖（御史红项族根因）
- 闸只对读它的执行链生效：多 magic 账号有多条开/撤单路径（live24 系统腿 magic、进化营 SD 批 magic、人工通道），闸源（retire_freeze_gate.json 类）只挂一条链=「冻结」是假的——其它通道照挂冻结品种新腿、照平冻结品种仓。
- 报「冻结闸已生效」前必 grep 闸文件名枚举全部读方（tools/*/scripts/* + 各引擎开单路径）与现存开单路径清单对读；任何不在读方清单里的开单路径=覆盖洞。
- 洞内已挂违规单止血三步：①orders_get() 全量按冻结品种过滤出 ticket（comment 前缀如 SD-E3S1-XXX 辅助确认归属通道）②order_send TRADE_ACTION_REMOVE 逐张撤 + 下一拍实读该品种挂单归零，动作留痕 sd_guard_run.log ③根修工单进 rd_queue（P1/QUEUED，验收=违规通道 0 新腿 0 重挂 + 闸 active=false 回归行为不变），改码走 23:00-06:00 调试窗+五验，chief 翻闸。对用户的报法写「止血完毕+根修在案+该通道闸已生效」，不写「闸已全局生效」。

## 6. 验活红绿双验 + 哨兵健壮性(11-14 实锤, 防"说修好了实盘还是问题重重")
- **红绿双验铁律**: 哨/自检/闸声称"修好了"前必做红绿双验——故意破坏输入(删价快照/坏 fixture/喂过期数据)断言显式 FAIL, 再恢复断言全绿, 双验都过才许交付。纯纸面验证(只读码不跑, 或只在健康输入上跑)=假绿, 禁止。
- **日志泄漏判定**: 判"仍在漏还是历史残留"必看日志 mtime/末条时间戳, 无时间戳的 grep 命中不能证"仍在漏"。
- **新数据/工单落盘前核消费端 schema**: 先读消费端代码(学习哨=LLM 容忍, 心跳哨读 mtime fail-open), 对旧 schema 容错=可落, 不容错=打回; 落盘后与同目录既有条目做 schema 对照。
- **哨兵脚本健壮性(两类真实死因, 写进每个新哨/自检脚本)**: ① cron no_agent 脚本跑 uv python 无 tzdata → `ZoneInfo('Asia/Shanghai')` 抛 ZoneInfoNotFoundError 整脚本死, 必套 try/except 回退固定 `timezone(timedelta(hours=8))`; ② Windows 控制台出 GBK 字节 → `subprocess.run(text=True)` 一律 `errors='replace'`, 否则 _readerthread UnicodeDecodeError=哨静默死; ③ JSONL 追加写必 `json.dump` 后跟 `f.write('\n')`——不跟换行=行粘连, 所有逐行 `json.loads(line)` 解析失败, 按最后一行 ts 判新鲜度的哨会把活流判"空"→自愈门误判死并反复重启采集器(11-14 实踩)。
- **数据有效性闸**: 一切自检 fixture 必带来源+实时价快照+新鲜度, 缺=显式 FAIL 禁静默通过(jince_exec_preflight.py 已固化: fixture 必含 bid_now, 快照缺失=红)。
- **接量化哨前先查源台账形状**: 数行 kind 分布+行数, 选样本够的表(日结 4 行表≠够 VaR/MC, 交易级 131 行表=够; 11-14 MC/VaR 哨实踩一次); 样本不足=显式红, 不静默降标。
