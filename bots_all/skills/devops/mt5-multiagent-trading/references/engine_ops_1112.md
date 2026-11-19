# 引擎进程与开单操作纪律 (2026-11-11 沉淀)

## 引擎拉起纪律
- **生产拉起路径 = 只看门狗** `jince_watchdog.py`（拉起段已带 OPENBLAS/OMP/MKL/NUMEXPR=1 线程限流 env，防 OpenBLAS OOM 复发；76076 死于 OOM 后已 patch）。
- **chief 临时拉起必用 PowerShell**（`powershell -NoProfile -Command ... & 'python.exe' tools\jince_live24.py`）——bash `terminal background=True` 会话会被 harness 清理杀进程（19284 事故），不留常驻。
- 验活三件套：`data/live24_magic_30261103.lock` 的 pid/ts 在刷 + 单实例（wmic 查 python + jince_live24 只有一个）+ stderr 无新增 OpenBLAS error。

## MT5 magic 号图（60137964 DEMO）
| magic | 归属 |
|---|---|
| 30261103 | jince_live24 实弹引擎（L0 热通道/SL 哨兵/giveback-floor 都在这进程） |
| 20261105 | 美股批限价挂单（12h 红线制：开挂即算，到期前平） |
| 20261106 | 币系 0.01 样本腿 |
| 20261104 | 练习层（李彦明手工练手, 技能 mt5-manual-trading-practice） |
- 20261104 之外的 magic（如 LX-TEST）非本引擎产物，出现于成交=他侧 EA，带单号实证。

## 执行层风控闸（A 类挂单处置口径）
- 上游（进化营 V4.1 等）A 类单**区质量（quality 分量）为负** = 执行层拒挂，回执注明"非上游判错，执行层闸更严；质量回正下版重呈即挂"（先例：LLY.NYS quality -0.03, 11-12 00:45 版）。
- 美股批挂单必带三件套：SL/TP + 12h 强平哨 + 事件窗决策点（12h 红线按美股批 22:20 口径）。
- 重复版本快照 A 类单点位未变 = 不重复挂（COST.NAS 先例：23:3x 挂讫，00:25/00:45 快照同点位跳过）。

## 半日节点持仓段（jince_midday_deep.py）
- ③段 2026-11-11 起读共享真值源 `E:\AgentCommons\shared\live_state.json`（positions+orders，>30min 判 stale 明示；不可用才降级派生簿且 fail-LOUD 标注"非实盘断言"）——根治旧版只读挂单派生簿导致 8 张活持仓漏报误报"无 open 单"（台账 t_node_pos_miss_midday_1111）。
- 注意：`jince_node.py`（6 大节点）的 ② 段 ATE 实读有自己的 fail-open，两条线都改过，别混淆。
