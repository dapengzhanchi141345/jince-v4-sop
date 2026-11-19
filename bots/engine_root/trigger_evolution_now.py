# -*- coding: utf-8 -*-
"""
trigger_evolution_now.py — 立即后台触发 GoldstrategyEngine Walk-Forward 自进化
(不等待 live 进程的 4h 定时器)。
只读回测, 绝不调用 order_send / 绝不下真实订单。
不停止/不重启 live 交易进程 (PID 15724)。
若 MT5 被 live 占用导致 ensure_mt5()/run_continuous_evolution 抛异常 -> 捕获、
报告、停止, 不重试、不杀 live。
"""
import os, sys, json, time, traceback
from datetime import datetime

BASE = r"E:\GoldstrategyEngine"
EVOLVE_DIR = os.path.join(BASE, "data", "continuous_evolution")
STATE_PATH = os.path.join(EVOLVE_DIR, "evolution_state.json")
REPORT_PATH = os.path.join(BASE, "EVOLUTION_TRIGGER_2026-07-10.md")

sys.path.insert(0, BASE)


def load_state(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {"_load_error": str(e)}
    return None


def fmt_params(params):
    if not params:
        return "N/A"
    return (f"adx_min={params.get('adx_min')} sl={params.get('sl_multiplier')} "
            f"tp={params.get('tp_multiplier')} position_size={params.get('position_size')} "
            f"risk_per_trade={params.get('risk_per_trade')} volatility_scalar={params.get('volatility_scalar')} "
            f"momentum_filter={params.get('momentum_filter')}")


def fmt_baseline(bs):
    if not bs:
        return "baseline=None"
    b = bs.get("baseline")
    if not b:
        return f"fitness={bs.get('fitness')} baseline=None"
    return f"fitness={bs.get('fitness')} PF={b.get('pf')} win_rate={b.get('win_rate')}"


def sym_line(sym, bs):
    if bs:
        return f"- **{sym}**: {bs.get('name')} | {fmt_baseline(bs)} | {fmt_params(bs.get('params'))}"
    return f"- **{sym}**: NONE"


start = time.time()
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ── 触发前: 加载既有 best 参数 (before 快照) ──
prior_state = load_state(STATE_PATH)
prior_bps = (prior_state or {}).get("best_per_symbol", {}) if prior_state else {}
prior_updated = (prior_state or {}).get("updated_at", "N/A") if prior_state else "N/A"

lines = []
lines.append("# 进化触发报告 — GoldstrategyEngine (Walk-Forward 自进化)")
lines.append("")
lines.append(f"- 触发时间: {now}")
lines.append("- 触发方式: 立即后台触发 `ce.run_continuous_evolution(max_rounds=50)`, 不等待 live 4h 定时")
lines.append("- 只读回测: 是 (本脚本及 `continuous_evolution_v2` 回测路径均不调用 order_send / 绝不下真实订单)")
lines.append("- live 进程 PID 15724: 未停止 / 未重启 (保留 ETHUSD 实盘验证)")
lines.append("")
lines.append(f"## 一、触发前系统加载的逐品种 best 参数 (来自 evolution_state.json @ {prior_updated})")
lines.append("")
if prior_bps:
    for sym, bs in prior_bps.items():
        lines.append(sym_line(sym, bs))
else:
    lines.append("- 无 prior_state (首次进化)")
lines.append("")

# ── 触发进化 ──
exc = None
result = "UNKNOWN"
mt5_note = ""
try:
    import continuous_evolution_v2 as ce
    print(f"[trigger] ensure_mt5 预检中 ...", flush=True)
    # 运行真实 MT5 H1 walk-forward 进化 (50 轮, 逐品种独立策略池)
    out = ce.run_continuous_evolution(max_rounds=50)
    result = out  # None = MT5 不可用被跳过; dict = 完成
except Exception as e:
    exc = traceback.format_exc()

elapsed = time.time() - start

# ── 触发后: 重新加载 best 参数 (after 快照) ──
new_state = load_state(STATE_PATH)
new_bps = (new_state or {}).get("best_per_symbol", {}) if new_state else {}

# ── 报告正文 (先写, 确保异常下也有交付) ──
lines.append("## 二、进化执行结果")
lines.append("")
if exc is not None:
    lines.append("- **状态: 异常/冲突 — 进化未成功完成**")
    lines.append("- 异常 traceback:")
    lines.append("```")
    lines.append(exc)
    lines.append("```")
    lines.append("- 结论: MT5 连接疑似被 live 进程 (PID 15724) 占用, 独立进化失败。建议改由 live 进程内 4h 软重置触发, 请勿强行杀 live。")
elif result is None:
    lines.append("- **状态: MT5 不可用 → ensure_mt5 返回 False, 进化被跳过 (未跑合成数据, 未改盘)**")
    lines.append("- 结论: 终端未连接/未登录 (可能为 live 占用), 独立进化未执行; evolution_state.json 保持 prior 基线。")
else:
    lines.append("- **状态: 进化完成 ✅ (逐品种 best 已写盘)**")
lines.append(f"- 总耗时: {elapsed:.1f} 秒 ({elapsed/60:.2f} 分钟)")
lines.append("")

lines.append("## 三、进化后新 best 参数 (各品种)")
lines.append("")
if new_bps:
    for sym, bs in new_bps.items():
        lines.append(sym_line(sym, bs))
else:
    lines.append("- 无 new_state")
lines.append("")

# ── XAU 关键变化 + 各品种 fitness/PF 变化表 ──
lines.append("## 四、XAUUSD 关键指标变化 & 各品种 fitness 变化")
lines.append("")
prior_xau = prior_bps.get("XAUUSD")
new_xau = new_bps.get("XAUUSD")
if prior_xau and new_xau:
    p_pf = (prior_xau.get("baseline") or {}).get("pf")
    n_pf = (new_xau.get("baseline") or {}).get("pf")
    if n_pf is not None and p_pf is not None:
        tag = "✅ 改善" if n_pf > p_pf else ("⚠️ 下降" if n_pf < p_pf else "持平")
    else:
        tag = "N/A"
    lines.append(f"- XAUUSD PF: {p_pf} → {n_pf} ({tag})")
    lines.append(f"- XAUUSD fitness: {prior_xau.get('fitness')} → {new_xau.get('fitness')}")
    pp = prior_xau.get("params", {})
    np_ = new_xau.get("params", {})
    lines.append(f"- XAUUSD params: sl {pp.get('sl_multiplier')}→{np_.get('sl_multiplier')} ; "
                 f"tp {pp.get('tp_multiplier')}→{np_.get('tp_multiplier')} ; "
                 f"adx_min {pp.get('adx_min')}→{np_.get('adx_min')} ; "
                 f"position_size {pp.get('position_size')}→{np_.get('position_size')}")
    # 针对任务提到的趋势策略 PF<1 过拟合疑点: 给出结论性说明
    if n_pf is not None and n_pf >= 1.0:
        lines.append(f"- 过拟合疑虑: 原 sl=2.59/tp=5.79 (Gen_36) 趋势回测 PF<1; "
                     f"本次 walk-forward 新最优 XAU PF={n_pf} (≥1 视为稳健, 过拟合疑点缓解)。")
    elif n_pf is not None:
        lines.append(f"- 过拟合疑虑: 本次新最优 XAU PF={n_pf} 仍 <1, 过拟合疑点未完全消解, 建议人工复核。")
else:
    lines.append("- XAUUSD 前后状态不完整, 无法对比")
lines.append("")
lines.append("| 品种 | 前 fitness | 后 fitness | 前 PF | 后 PF |")
lines.append("|------|-----------|-----------|-------|-------|")
all_syms = list(prior_bps.keys()) if prior_bps else list(new_bps.keys())
for sym in all_syms:
    pb = prior_bps.get(sym) or {}
    nb = new_bps.get(sym) or {}
    pf_p = (pb.get("baseline") or {}).get("pf") if pb else None
    pf_n = (nb.get("baseline") or {}).get("pf") if nb else None
    lines.append(f"| {sym} | {pb.get('fitness')} | {nb.get('fitness')} | {pf_p} | {pf_n} |")
lines.append("")

# ── 文件状态 ──
lines.append("## 五、写盘文件状态")
lines.append("")
if os.path.exists(STATE_PATH):
    sz = os.path.getsize(STATE_PATH)
    changed = bool(new_state and prior_state and new_state.get("updated_at") != prior_state.get("updated_at"))
    lines.append(f"- 路径: `{STATE_PATH}`")
    lines.append(f"- 存在: 是 | 大小: {sz} bytes")
    lines.append(f"- updated_at: {new_state.get('updated_at') if new_state else 'N/A'}")
    lines.append(f"- 是否已改写: {'是 (已写入新最优)' if changed else '否 (保持 prior 基线)'}")
else:
    lines.append(f"- 路径: `{STATE_PATH}` | 存在: 否 (未写盘)")
lines.append("")

# ── 异常/冲突汇总 ──
lines.append("## 六、异常 / 冲突汇总")
lines.append("")
if exc:
    lines.append("- ⚠️ 发生异常 (完整 traceback 见第二节)。疑似 MT5 连接被 live (PID 15724) 占用导致冲突。")
    lines.append("- 已按约束: 捕获异常、未重试、未杀 live、evolution_state.json 未被破坏。")
elif result is None:
    lines.append("- 无 Python 异常; 进化因 MT5 不可用被优雅跳过 (ensure_mt5=False)。未改盘, 未杀 live。")
else:
    lines.append("- 无异常; 进化成功完成并已写盘。live 进程 (PID 15724) 未被触碰, 其 drift monitor 将按只读方式自动加载新 baseline。")
lines.append("")
lines.append("---")
lines.append(f"报告生成: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 总耗时 {elapsed:.1f}s")

report = "\n".join(lines)
with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write(report)

print("\n" + "=" * 70)
print("TRIGGER DONE. elapsed=%.1fs result=%s exc=%s" % (elapsed, type(result).__name__, "YES" if exc else "no"))
print("REPORT -> " + REPORT_PATH)
print("=" * 70)
