#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金策下单中央门 (闸不咬合#4 根因修复, 李令 2026-11-17 练习阶段全放开后建):
任何下单动作(ATE直下/脚本/子bot)必须先过本门:  三门预检 + 强制 wave_id/actor 台账。
无台账挂单 = L4 扫描器撤单对象(11-17 15:5x 先例: v3-fwd 4单被 L4-retired-violations-batch3 撤, 挂单方不可定位)。

用法:
  python order_gate.py check --sym XAUUSD --side sell --vol 0.01 --wave <wave_id> [--actor mainbot] [--note ...]
verdict PASS -> 写 order_lifecycle.jsonl gate_check 行(actor台账), exit 0
verdict BLOCK -> exit 1 (stderr 打印原因)
确定性零LLM; 门文件只读; 台账只追加。
"""
import json, argparse, datetime, os, sys, glob

BASE = os.path.dirname(os.path.abspath(__file__))
GATE_FILES = ["retire_freeze_gate.json", "l4_veto_gate.json", "crypto_freeze_gate.json", "risk_freeze_state.json"]
COIN_SYMBOLS = {"BTCUSD","ETHUSD","SOLUSD","XRPUSD","LTCUSD","BNBUSD","ADAUSD","BCHUSD","DOGEUSD",
                "DOTUSD","KSMUSD","POLUSD","TAOUSD","UNIUSD","XLMUSD","XTZUSD"}
LEDGER = os.path.join(BASE, "data", "order_lifecycle.jsonl")

def load_gate(name):
    p = os.path.join(BASE, "data", name)
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None

def gate_hit(name, g, sym):
    if not g or g.get("active") is not True:
        return None  # active=false = 放行留痕模式, 不拦
    if any(sym in (g.get(k, []) or []) for k in ("scope_symbols", "symbols")):
        return f"{name}: 命中scope_symbols/symbols"
    scope = str(g.get("scope", ""))
    if sym in COIN_SYMBOLS and scope in ("coins", "crypto_family"):
        return f"{name}: 币系族冻结(scope={scope})"
    if "all" in scope and g.get("active") is True:
        return f"{name}: 全市场冻结(scope=all)"
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sym", required=True)
    ap.add_argument("--side", choices=["buy", "sell"])
    ap.add_argument("--vol", type=float, default=0.01)
    ap.add_argument("--wave", default="")
    ap.add_argument("--actor", default="mainbot")
    ap.add_argument("--note", default="")
    a = ap.parse_args()

    hits = []
    checked = []
    for name in GATE_FILES:
        g = load_gate(name)
        checked.append(name + ("" if g is None else ("(active)" if g.get("active") else "(off)")))
        h = gate_hit(name, g, a.sym)
        if h:
            hits.append(h)
    if not a.wave.strip():
        hits.append("中央门强制项: 无 wave_id (下单动作必带 wave_id+actor 台账, 闸不咬合#4修复)")

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    verdict = "BLOCK" if hits else "PASS"
    row = {"ev": "gate_check", "ts": ts, "verdict": verdict, "sym": a.sym, "side": a.side,
           "vol": a.vol, "wave": a.wave, "actor": a.actor, "hits": hits,
           "gates_checked": checked, "note": a.note, "live": True, "tool": "order_gate.py"}
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"verdict": verdict, "hits": hits, "ledger_row": row}, ensure_ascii=False, indent=1))
    sys.exit(0 if verdict == "PASS" else 1)

if __name__ == "__main__":
    main()
