# 引擎活码热补丁 + 重启验活配方（jince_live24.py 类）

适用: 对 `E:/GoldstrategyEngine/tools/jince_live24.py` 做加法补丁(SKIP_* 闸/参数开关/执行修复)后让新码生效, 且必须保持一魔一号锁单实例纪律(魔号 30261103/30261104 各自一把锁)。

## 步骤(顺序不可乱)
1. **备份**: `cp jince_live24.py jince_live24.py.bak_<标记>`(同目录)。
2. **加法原则**: 新常量(带 ENABLE 开关)+前置判断+新留痕标记; 不碰存量逻辑, 不删旧闸。补丁锚点用 `patch` 工具精确匹配, 全角字符/注释行是好的锚(ASCII 行常重复)。
3. **编译**: `"D:/workbuddy/binaries/python/versions/3.13.12/python.exe" -m py_compile jince_live24.py`(3.13.12=引擎同款解释器, 用别的版本编译无意义)。
4. **单元验(只读)**: 补丁若改数值/步长/参数, 写 scratch 脚本真读 MT5 验证行为(如 volume_step: 股类 step=1 发 1 股, FX/金银/股指/币系 step=0.01 发 0.01), 12 品种级覆盖, 不发单。
5. **杀旧实例**: `taskkill /F /PID <旧pid>`。旧 pid 取自 `data/live24_magic_<魔号>.lock`(JSON: pid/ts/magic); 只杀自己魔号的锁 pid, 别误杀进化营实例。
6. **等哨, 不等就手动**: 看门狗窗内(5min 拍/8min 起)会自动拉起。~3min 后读锁: pid 未翻=哨没拉, **允许手动补拉**(一魔一号锁仲裁: 重复实例 1s 自退, 锁 pid 死则新实例接管, 无双实例风险)。手动拉=按原命令行 PowerShell 起 detached:
   ```
   powershell -NoProfile -Command "Start-Process -PassThru -WorkingDirectory 'E:\GoldstrategyEngine\tools' -FilePath 'D:\workbuddy\binaries\python\versions\3.13.12\python.exe' -ArgumentList 'jince_live24.py'"
   ```
   原命令行恢复法: `wmic process where "processid=<pid>" get commandline`(tasklist 的 /FI 过滤在本宿主会假 0 命中, 查活进程一律 wmic)。
7. **验活**: 40-60s 后读锁 = 新 pid + ts 新鲜 + magic 对; `wmic` 验新 pid 命令行与补丁前一致; 新码生效判据 = 锁写时刻晚于补丁文件 mtime(启动即写锁)。服务端三件套(SL/TP/12h 哨)不随引擎重启丢, 空窗期裸奔风险=零。

## 坑
- **僵尸引擎签名(11-14 实踩)**: stdout 日志循环刷 `loop err: name 'X' is not defined`(未接住的 NameError)= 主循环每轮崩, 进程**活着但从未处理过新信号**, 看门狗只看进程存活会持续误判健康。修变量后必须热切换并验 `loop err` 停止刷屏; 判引擎健康看"日志尾在正常拒单/留痕", 不看进程存在。
- **手动拉起后必验锁 pid=自家 pid(一魔一号静默自退)**: 新实例遇活锁 1s 自退(退出码 0, 输出"已有活实例持锁, 本实例自退"), 拉了≠成了; 若旧实例是补丁前启动的(跑旧码), 手动拉新码会被静默顶掉继续旧码——杀旧→拉新→读锁 pid 对上新 pid 三步缺一不可。
- **Popen 拉机优于 Start-Process**: 需日志重定向时用 Python `subprocess.Popen([3.13.12 解释器, 'jince_live24.py'], cwd=tools, env={OMP/MKL/NUMEXPR 线程=1}, stdout/stderr append 到 logs/, creationflags=0x08000000)` 脱离式拉起(76076 OOM 教训: 线程变量必设); Start-Process 无重定向, 引擎 print 进虚空。
- **源码落盘禁止 shell 承载**: 整文件改写/新脚本一律 write_file 或 Python `open().write()` 直写; 经 shell heredoc/内联替换传源码在本宿主被转义毁过(落地 7 字节模板残留), write_file 拒重写时先 read_file 再整写。
- 验活读锁必认真名 `data/live24_magic_<魔号>.lock`(data/ 根下没有 `live24_lock.json`)——猜错路径=假阴性, 会把"引擎没重启"误判成死引擎。
- 杀旧后**别马上再杀/再拉**(churn): 锁 ts 在旧进程死前会持续刷新, 拿"锁 ts 没变"判活要扣掉最后刷新时刻, 防把死锁当活锁。
- `Start-Process` 无 stdout 重定向, 引擎 print 进虚空; 验活认锁+进程, 不认日志。
- 手动拉起的实例不受看门狗 8min 窗管, 崩了要等下一拍才拉——拉完 5min 内复拍锁一次防闪退。

## 看守实体 + 一键 kill switch + 风控量化哨(11-14 实测补齐)
- **live24 的看守实体 = `E:\workbuddy\国外模型\hermes\scripts\jince_watchdog.py`**(cron 15min 拍; 不等拍时手动跑一次即拉起: `D:/jince_sass/.venv/Scripts/python.exe jince_watchdog.py`)。动手前查 `data/jince_live24_retire.json`: active=true=退役旗, 阻止拉起。
- **一键 kill switch(P0, 独立于主引擎)**: 写 `E:\GoldstrategyEngine\data\kill_switch.json` state=TRIGGERED → 每 1min 看守 `jince_kill_switch_watch.py` 触发 `jince_kill_switch_exec.py`(ATE 通道: 全撤挂单+市价全平+halt 引擎+30s 复核, 防主循环死锁)。恢复=人工: 翻回 ARMED + risk_state.halt=false + chief 岗留痕(L5 留李); 每月 paper 演练(drill 只验链路不碰实单)。
- **MC/VaR 风控量化哨** `jince_mc_var_report.py`(每日 07:45 no_agent, 全绿静默): 交易级损益台账 bootstrap×1000 + 日 VaR95; 红线=日 VaR>2R / MaxDD95>50% 总 R / 样本<30 笔; 红报 bot-chat。
- **休市订单生命周期**: 休市品种(周末股指/外汇/黄金)的挂单任何操作含删除/修改都返 10018 market closed——遗留挂单当场清不掉, 必须挂"重开后清理"哨(开盘第一动作=撤遗留挂单, 留无主单痕); 原因=broker 对休市品种连删除都拒绝。
- **P2 顶配三件(确定性 0-LLM, 实盘升档热插口)**: 执行算法 `E:/GoldstrategyEngine/tools/exec_algo.py`(TWAP 切片/点差地板/regime 手数调制, --selftest 5 断言); L2 代理采集器 `jince_l2proxy_collector.py`(30s 采样 8 品种→l2proxy_ticks.jsonl, HVN/LVN 区供结构锚定 TP 落 LVN/SL 避 HVN 内侧); regime 门 `jince_regime_zone_runner.py`(每 30min: 区+regime_state.json+采集器自愈 ensure_collector)。live24 开单路径接入 regime 门为 fail-safe 加法: HIGHVOL=拒开新仓, 数据缺/过期>3h=放行+30min 红一次, 不静默。
