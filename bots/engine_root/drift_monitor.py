# drift_monitor.py — Live Drift Monitor（补 WFER 盲区）
#
# 目的: 进化引擎现有 WFER 只测 walk-forward 内部退化,
#       缺"live 实际成交表现 vs 进化回测基线"的偏差监控。
#       本模块为**只读漂移监控**: 绝不交易 / 不改仓 / 不自动回滚 / 不写 evolution_state。
#
# 设计要点:
#   1. MT5 惰性导入 —— 仅函数内 `import MetaTrader5 as mt5`, 模块顶层绝不调 MT5,
#      保证 import 安全 (selftest 不会因 MT5 未连而崩)。
#   2. 基线来源 load_baseline(): 优先 evolution_state.json 的 best_strategy.baseline
#      (由 continuous_evolution_v2 写入的回测 pf/win_rate); 缺失则回退 evolution_data.json
#      末条 win_rate (pf 记 None)。
#   3. 实盘指标 compute_live_metrics(): 优先 mt5.history_deals_get 近 N 天平仓成交;
#      MT5 不可用 → 兜底 trade_journal.jsonl 的 FILL+CLOSE(按 ticket 配对);
#      两者皆不足 → NO_DATA。
#   4. 评估 assess_drift(): GREEN / RED / NO_DATA, 仅给建议(回滚是 CIO 决策)。
#   5. run_drift_check(): 编排上述, 写 data/continuous_evolution/drift_report.json (DRY)。
#
# 铁律: 本模块**只读**。不得直接改 evolution_state / 不得平仓 / 不得自动回滚。

import os
import json
import time
from datetime import datetime, timedelta

# ═══ 只读总开关 ═══
DRIFT_MONITOR_ENABLED = True

# ═══ 路径 (相对本文件) ═══
_BASE = os.path.dirname(os.path.abspath(__file__))
_EVOLVE_DIR = os.path.join(_BASE, "data", "continuous_evolution")
_STATE_PATH = os.path.join(_EVOLVE_DIR, "evolution_state.json")
_DATA_PATH = os.path.join(_EVOLVE_DIR, "evolution_data.json")
_JOURNAL_PATH = os.path.join(_EVOLVE_DIR, "trade_journal.jsonl")
_REPORT_PATH = os.path.join(_EVOLVE_DIR, "drift_report.json")
# P0-1 修复: live 自身滚动基线(样本外 vs 样本外自相对漂移), 替代进化样本内回测基线.
#   演进样本内回测 PF(如 BTCUSD 44.68) 与 live 样本外 PF(0.87) 属错配, 拿来比会永远 RED.
#   正确基线应为系统自身的近期 live 表现: 当前窗口 vs 上一窗口自相对漂移.
LIVE_BASELINE_PATH = os.path.join(_EVOLVE_DIR, "drift_live_baseline.json")

# 阈值常量 (与进化引擎一致: RR=2.0 对应盈亏平衡胜率 33.3%)
RR_BALANCE_WIN_RATE = 0.333
GREEN_WIN_RATE_FLOOR = 0.25
PF_DRIFT_RATIO = 0.6  # live.pf 低于 baseline.pf*该比例 → 漂移红线

# 本系统固定 magic number (P0-HIGH-3): 仅统计带此 magic 的成交, 过滤账户里
# 其它手动/其它 EA 的成交, 避免实盘漂移统计被污染 (审计事实#3: 41笔仅2笔系统开).
# 与 guardian_executor.SYSTEM_MAGIC 必须一致; 用 try 兜底以防 guardian 导入异常.
try:
    from guardian_executor import SYSTEM_MAGIC
except Exception:
    SYSTEM_MAGIC = 20260708

# 本系统平仓样本下限: 低于此数视为样本不足 (避免小样本虚判 GREEN/RED)
MIN_SYSTEM_TRADES = 5

# 漂移相对评估的最低置信样本数 (P1, 2026-07-09): 低于此数(小样本, 如当前 8 笔)
# 不做相对漂移 RED 判定, 降级 NO_DATA, 避免虚警误导 CIO. 绝对净亏线(pf<1.0)
# 已在 assess_drift 上方硬约束, 不受样本量限制.
MIN_CONFIDENT_TRADES = 30


def load_baseline():
    """读取漂移基线 (P0-1 修复后)。

    优先级:
      0) live 自身滚动基线 drift_live_baseline.json (样本外 vs 样本外, 自相对漂移, 首选)
      1) evolution_state.json -> best_strategy.baseline (样本内回测 pf/win_rate, 仅信息参考)
      2) 回退 evolution_data.json 末条 win_rate (pf 记 None)
    返回 {pf, win_rate, source, trade_count?} 或 None(三者皆无)。
    """
    # 0) live 自身滚动基线(首选): 仅在样本充足(>=置信地板)时采用, 避免小样本虚基线
    if os.path.exists(LIVE_BASELINE_PATH):
        try:
            with open(LIVE_BASELINE_PATH, "r", encoding="utf-8") as f:
                bl = json.load(f)
            if (isinstance(bl, dict) and isinstance(bl.get("pf"), (int, float))
                    and (bl.get("trade_count") or 0) >= MIN_CONFIDENT_TRADES):
                return {
                    "pf": bl.get("pf"),
                    "win_rate": bl.get("win_rate"),
                    "trade_count": bl.get("trade_count"),
                    "source": "live_rolling",
                }
        except Exception:
            pass
    # 1) evolution_state.json 的 best_strategy.baseline (样本内回测, 仅信息参考)
    if os.path.exists(_STATE_PATH):
        try:
            with open(_STATE_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
            bs = state.get("best_strategy") or {}
            bl = bs.get("baseline")
            if isinstance(bl, dict) and ("pf" in bl or "win_rate" in bl):
                return {
                    "pf": bl.get("pf"),
                    "win_rate": bl.get("win_rate"),
                    "source": "evolution_state.baseline",
                }
        except Exception:
            pass
    # 2) 回退 evolution_data.json 末条 win_rate
    if os.path.exists(_DATA_PATH):
        try:
            with open(_DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            results = data.get("results") or []
            if results:
                last = results[-1]
                wr = last.get("win_rate")
                if wr is not None:
                    return {"pf": None, "win_rate": wr, "source": "evolution_data.fallback"}
        except Exception:
            pass
    return None


def _save_live_baseline(live):
    """持久化 live 自身滚动基线(供下一窗口自相对漂移对照). 只读安全, 异常静默."""
    try:
        if not isinstance(live, dict) or live.get("status") == "NO_DATA":
            return
        pf = live.get("pf")
        n = live.get("trade_count")
        if not isinstance(pf, (int, float)) or not isinstance(n, (int, float)):
            return
        if n < MIN_CONFIDENT_TRADES:
            return
        snap = {
            "pf": round(pf, 4),
            "win_rate": live.get("win_rate"),
            "trade_count": n,
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
        with open(LIVE_BASELINE_PATH, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _compute_from_journal():
    """兜底: 从 trade_journal.jsonl 读 FILL+CLOSE(按 ticket 配对)算盈亏。

    若无 CLOSE 记录 → NO_DATA(reason: journal 无平仓记录)。
    """
    if not os.path.exists(_JOURNAL_PATH):
        return {"status": "NO_DATA", "reason": "样本不足(journal 不存在)"}
    fills, closes = {}, {}
    try:
        with open(_JOURNAL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                t = rec.get("type")
                tk = rec.get("ticket")
                if t == "FILL":
                    fills[tk] = rec
                elif t == "CLOSE":
                    closes[tk] = rec
    except Exception:
        return {"status": "NO_DATA", "reason": "样本不足(journal 读取失败)"}

    if not closes:
        return {"status": "NO_DATA", "reason": "journal 无平仓记录"}

    # 优先用 CLOSE 记录自带的盈亏字段; 否则用 FILL/CLOSE 价格差近似
    pnls = []
    for tk, c in closes.items():
        pnl = None
        for k in ("pnl", "profit", "realized_pnl", "close_pnl"):
            if isinstance(c.get(k), (int, float)):
                pnl = float(c[k])
                break
        if pnl is None:
            frec = fills.get(tk)
            if frec and isinstance(c.get("price"), (int, float)) and isinstance(frec.get("price"), (int, float)):
                direction = 1 if str(frec.get("direction", "")).upper() == "BUY" else -1
                pnl = direction * (float(c["price"]) - float(frec["price"]))
        if pnl is not None:
            pnls.append(pnl)

    if not pnls:
        return {"status": "NO_DATA", "reason": "journal 平仓记录无可算盈亏"}

    gross_w = sum(p for p in pnls if p > 0)
    gross_l = -sum(p for p in pnls if p < 0)
    wins = sum(1 for p in pnls if p > 0)
    total = len(pnls)
    pf = (gross_w / gross_l) if gross_l > 0 else (None if gross_w <= 0 else None)
    return {
        "status": "OK",
        "pf": round(pf, 4) if pf is not None else None,
        "win_rate": round(wins / total, 4),
        "trade_count": total,
        "source": "journal",
    }


def compute_live_metrics(days=30):
    """计算 live 实盘指标。

    优先: mt5.history_deals_get 近 N 天平仓成交。
    MT5 不可用(未初始化/异常) → 兜底 journal。
    两者皆不足 → NO_DATA。
    """
    # —— 优先 MT5 历史成交 (P0-HIGH-3: 仅统计本系统标签 magic==SYSTEM_MAGIC) ——
    try:
        import MetaTrader5 as mt5  # 惰性导入: 顶层绝不调 MT5
        # terminal_info() 非 None 才代表已 initialize 且连上终端 (避免重复初始化干扰 live 循环)
        if mt5 is not None and mt5.terminal_info() is not None:
            now = datetime.now()
            from_date = now - timedelta(days=days)
            deals = mt5.history_deals_get(from_date, now)
            if deals:
                gross_w = 0.0
                gross_l = 0.0
                wins = 0
                trades = 0
                for d in deals:
                    # P0-HIGH-3: 仅本系统成交计入 (按 magic 标签过滤, 排除账户里
                    #   其它手动/其它 EA 的成交, 防 RED 伪阳性 — 审计事实#3)
                    mg = getattr(d, "magic", None)
                    if mg is not None and mg != SYSTEM_MAGIC:
                        continue
                    p = getattr(d, "profit", 0.0) or 0.0
                    if p == 0.0:
                        continue  # 开仓 deal 无盈亏, 跳过
                    trades += 1
                    if p > 0:
                        gross_w += p
                        wins += 1
                    else:
                        gross_l += -p
                # 本系统平仓样本不足 → NO_DATA (避免小样本虚判)
                if trades < MIN_SYSTEM_TRADES:
                    return {
                        "status": "NO_DATA",
                        "reason": "本系统样本不足",
                        "trade_count": trades,
                        "source": "mt5",
                    }
                pf = (gross_w / gross_l) if gross_l > 0 else None
                return {
                    "status": "OK",
                    "pf": round(pf, 4) if pf is not None else None,
                    "win_rate": round(wins / trades, 4),
                    "trade_count": trades,
                    "source": "mt5",
                }
            # deals 为空(近期无平仓) → 走 journal 兜底
    except Exception:
        # MT5 不可用 / 异常 → 静默兜底
        pass

    # —— 兜底 journal (journal 本就是我们系统写入, 天然带 SYSTEM 标签) ——
    return _compute_from_journal()


def assess_drift(live, baseline):
    """评估实盘漂移。只读评估, 仅给建议(回滚是 CIO 决策)。

    - NO_DATA(live) → 持续收集样本
    - **绝对平衡线 (P0-HIGH-2, 最高优先级)**: live.pf < 1.0 (净亏损系统)
      → 直接 RED, 标注"净亏损系统"
    - 相对漂移: live.pf < baseline.pf*0.6 → RED
    - 否则 (pf>=1.0 且相对未漂移 且 胜率达标) → GREEN
    """
    if not isinstance(live, dict) or live.get("status") == "NO_DATA":
        return {"status": "NO_DATA", "suggest": "持续收集实盘样本"}
    if not isinstance(baseline, dict):
        return {"status": "NO_DATA", "suggest": "baseline 缺失, 无法评估漂移(等待进化基线写入)"}

    pf = live.get("pf")
    wr = live.get("win_rate")
    bpf = baseline.get("pf")

    # 绝对平衡线: 实盘净亏损 (pf<1.0) → 直接 RED (最高优先级, 审计事实#2)
    if isinstance(pf, (int, float)) and pf < 1.0:
        return {
            "status": "RED",
            "suggest": "实盘净亏损系统 (pf<1.0), 待优化提升至 pf≥1.0 (优化期正常现象, 非紧急回滚)",
            "reasons": [f"实盘 pf={pf:.2f} < 1.0 (净亏损系统)"],
        }

    # 样本地板 (P1, 2026-07-09): 相对漂移评估需 ≥30 笔才有统计置信,
    #   小样本(如当前 8 笔)不判 RED, 降级 NO_DATA, 避免虚警误导 CIO.
    #   绝对净亏线(pf<1.0)已在上方硬约束, 不受样本量限制.
    n = live.get("trade_count")
    if isinstance(n, (int, float)) and n < MIN_CONFIDENT_TRADES:
        return {"status": "NO_DATA",
                "suggest": f"实盘样本 {n} 笔 < 置信地板 {MIN_CONFIDENT_TRADES}, "
                           f"相对漂移评估暂停(仅绝对净亏线 pf<1.0 生效)"}

    # P0-1 修复: 相对漂移仅在基线为 live 自身滚动基线(live_rolling)时生效.
    #   若基线仍来自进化样本内回测(evolution_state.baseline), 属"样本内 vs 样本外"错配,
    #   不做相对 RED (避免 44.68 永远判 RED); 仅以胜率维度提示.
    bsrc = baseline.get("source")
    if bsrc == "live_rolling":
        pf_ok = (bpf is None) or (isinstance(pf, (int, float)) and pf >= bpf * PF_DRIFT_RATIO)
    else:
        # 回测基线(信息参考): 不触发相对 RED, pf_ok 视为通过
        pf_ok = True

    # GREEN: 双维度达标
    if pf_ok and isinstance(wr, (int, float)) and wr >= GREEN_WIN_RATE_FLOOR:
        return {"status": "GREEN", "suggest": "实盘表现与基线一致, 无需干预"}

    # RED: 给出具体原因
    reasons = []
    if (bsrc == "live_rolling" and isinstance(pf, (int, float)) and bpf is not None
            and pf < bpf * PF_DRIFT_RATIO):
        reasons.append(f"pf={pf:.2f} < 上一滚动基线*0.6={bpf * PF_DRIFT_RATIO:.2f} (自相对漂移)")
    if isinstance(wr, (int, float)) and wr < RR_BALANCE_WIN_RATE:
        reasons.append(f"胜率={wr:.1%} < 盈亏平衡线 {RR_BALANCE_WIN_RATE:.1%} (RR=2.0)")
    status = "GREEN" if not reasons else "RED"
    return {
        "status": status,
        "suggest": "无相对漂移" if not reasons else "实盘自相对漂移超阈值, 建议审视近期策略变更",
        "reasons": reasons,
    }


def run_drift_check(days=30):
    """编排漂移检查, 写 drift_report.json (DRY, 只读不交易)。

    返回结果 dict(status/baseline/live/suggest/red_alarm)。
    绝不直接改 evolution_state / 绝不平仓 / 绝不自动回滚。
    """
    if not DRIFT_MONITOR_ENABLED:
        return {"status": "DISABLED", "suggest": "漂移监控已关闭(DRIFT_MONITOR_ENABLED=False)"}

    baseline = load_baseline()
    live = compute_live_metrics(days=days)
    # P0-1 修复: 持久化 live 自身滚动基线(供下一窗口自相对漂移对照).
    #   仅在样本充足且 pf 为数值时写入, 避免小样本/无盈亏虚基线.
    _save_live_baseline(live)
    assessment = assess_drift(live, baseline)

    result = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "enabled": DRIFT_MONITOR_ENABLED,
        "baseline": baseline,
        "live": live,
        "status": assessment["status"],
        "suggest": assessment.get("suggest"),
        "reasons": assessment.get("reasons"),
        "red_alarm": assessment["status"] == "RED",
        "read_only": True,  # 声明: 本检查未做任何写仓/回滚动作
    }

    # 仅写 drift_report.json, 不触碰 evolution_state / 不交易
    try:
        with open(_REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return result


def format_log(result):
    """生成一行可读日志 (供 run_trader 打印)。"""
    if not isinstance(result, dict):
        return f"[漂移监控] 异常结果: {result}"
    status = result.get("status")
    if status == "RED":
        tag = "[RED] 漂移告警"
    elif status == "GREEN":
        tag = "[GREEN] 漂移正常"
    elif status == "NO_DATA":
        tag = "[NO_DATA] 样本不足"
    else:
        tag = f"[{status}]"
    base = result.get("baseline") or {}
    live = result.get("live") or {}
    return (f"[漂移监控] {tag} | baseline(pf={base.get('pf')}, wr={base.get('win_rate')}) "
            f"| live(pf={live.get('pf')}, wr={live.get('win_rate')}, "
            f"n={live.get('trade_count')}, src={live.get('source')}) "
            f"| {result.get('suggest')}")


if __name__ == "__main__":
    out = run_drift_check()
    print(format_log(out))
    print(json.dumps(out, indent=2, ensure_ascii=False))
