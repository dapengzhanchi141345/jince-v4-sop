# 开单路径闸栈 & “0 开新仓”诊断

## 诊断步骤（按序，别跳步）
1. **先读最新一拍 brief/日志的实际拒单原因行**（`[FAIL] ... 闸: ...` / `[stop] ...`）：币系 `data/crypto_pending_brief.md`、全链 `data/auto_cycle.log`。日志行 = 真因，权威高于闸源状态推断。
2. 按该开单路径的闸栈表（下）逐道核对，不凭单一闸源归因。
3. 核对闸源新鲜度再下结论：`jince_gate.json` 陈旧 >600s 也 fail-closed 拒单；`risk_state.json`/`l4_consec_bridge.json` 超 30min 判过期（见共享数据铁律）。

## exp_r 总闸（全局、最深的一道）
- 码：`multi_agent/trading/_exp_r_gate.py`；4 条开新仓路径（pending_orders / crypto_pending / equity_pending / trader_cio_gate）在 `mt5.order_send` 前调用；`portfolio_governor` 的减仓/平仓**不挂**此闸（泄压方向，挂上=锁死仓位）。
- 闸值源：`MQL5/Files/jince_gate.json`（`tools/mt5_live_console.py` gate_writer 每 60s 重写），值 = `evolution/incumbent_genome.json` 的 `fitness.exp_r`（`rid` 标当前冠军，`rid=base` = 还停在基础基因组）。
- 拒单条件（fail-closed）：快照缺失/损坏；陈旧 >600s（`_STALE_S`）；`exp_r <= 0.1`（`_THRESHOLD`）。
- 单路径窄口子 override：`evolution/gate_override_<path>.json`，字段 `{enabled, exp_r, source, review_by(YYYY-MM-DD)}`；过期/缺失/损坏 → 回落全局闸（fail-closed）。调用方须传 `read_exp_r_gate(path=...)` 才启用；**不传 path = 走全局闸**（现 crypto 路径即如此，白名单例外腿也被总闸盖住）。
- 先例：XAU 突破腿用路径闸开过有期限窄口子（独立 OOS 证据）——同类窄开法。

## 各路径闸栈表（只作用于本路径，禁止跨路径推断）
| 路径 | 闸门（依序） | 注 |
|---|---|---|
| crypto 例外腿（`crypto_pending.py` run_cycle 例外腿块） | `_is_exception_symbol`（one_leg_repost：已有活腿/持仓即跳）→ `_is_d_grade`（读 alpha_rating adjusted）→ 模块级 `can_open` → `place()` 内 exp_r 总闸 | 独立 subprocess（`auto_run_cycle.step2b_crypto` 裸跑 `python crypto_pending.py`），**不读 `new_entry_scale`/账户级冷却** |
| 模块级 `can_open` | 模块自身 state（`*_pending_state.json`）的 `consec_losses>=3 且 now<cooldown_until` | 模块 state 与账户级 `risk_state`/`l4_consec_bridge` 是**两本账**：模块自身冷却可能早已过期，账户级仍锁着——判“会不会被挡”必须实读对应那本账，别混 |
| 账户级冷却（L4 桥） | `l4_consec_bridge.json` → D 侧 write_risk_state 读-合并从严 → `risk_state.new_entry_scale=0.0` | 作用于 D 侧路径缩放；crypto 独立 subprocess 路径不受它挡 |
| 币系冻结桥 | `crypto_freeze_gate.json` active=true → 币系 0 开新腿；`exceptions.<SYM>` 白名单腿（0.5x/one_leg_repost）放行 | 白名单放行**不等于豁免 exp_r 总闸** |

## OOS 自锁与解锁
- 症：冠军基因组成负期望（`rid=base`、exp_r<0.1）→ exp_r 总闸全拒 → 0 新仓 → 无前向 OOS 样本 → 无法验证出正期望基因组 → 冠军一直负 = 自锁。OOS 观察腿（为攒样本而开单）被 fail-closed EV 闸一并焊死。
- 解锁两案（**裁定归风控，执行方不代裁**）：A = 给 OOS 观察腿出窄 override（`gate_override_<path>.json`，带复核日+证据，只放攒样腿、不松交易腿纪律）；B = 不开口，等 meta-evolver 跑出正期望冠军（闸自动开；慢、不保证，期间 OOS 恒 0）。
- 报障口径：报“0 开新仓”列全生效闸源（账户冷却 + exp_r 总闸 + 冻结桥…），不单一归因；报“攒样停滞”先区分「单摸不到价」（攒样机制问题）vs「闸拒」（exp_r 总闸问题）——修复属主不同（机制=研发码格，闸=风控裁定）。
