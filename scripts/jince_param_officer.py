# -*- coding: utf-8 -*-
"""jince_param_officer.py — 参数官哨(李令11-17'找专人负责参数'): 参数表唯一写者+一致性审计+OOS样本账本
每30min(哨), 纯确定性: 读 spec v4 JSON ↔ 参数表 ↔ 三哨脚本常量, 三处不一致=工单+输出报李;
前向样本账本: deep_opt/v4 口径平仓单计数, 30笔满=⑥线翻闸待裁工单. 无异常=静默(watchdog).
"""
import json, re, os, glob, datetime as dt

ROOT = "E:/GoldstrategyEngine"
SPEC = os.path.join(ROOT, "data", "param_spec_v4_earn_cell_20261117.json")
PTAB = os.path.join(ROOT, "data", "practice_params_all_symbols.json")
Q = os.path.join(ROOT, "data", "rd_queue.json")
LEDGER = os.path.join(ROOT, "data", "order_lifecycle.jsonl")
STATE = os.path.join(ROOT, "data", "param_officer_state.json")
SENTINELS = {
    "BTCUSD": (os.path.join(ROOT, "soul_wave_market_in_1117.py"), "SL_DIST", "TP_R_MULT"),
    "ETHUSD": (os.path.join(ROOT, "slv2_eth_market_in_1117.py"), "R_DIST", "TP_MULT"),
    "SOLUSD": (os.path.join(ROOT, "slv2_sol_market_in_1117.py"), "R_DIST", "TP_MULT"),
}

def main():
    spec = json.load(open(SPEC, encoding="utf-8"))
    cells = spec["cells"]
    need = int(spec["rules"].get("forward_samples_needed", 30))
    ptab = json.load(open(PTAB, encoding="utf-8"))
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    issues = []
    const_state = {}
    for sym, (path, sl_key, tp_key) in SENTINELS.items():
        c = cells.get(sym)
        if not c or sym not in ptab:
            continue
        p_ok = abs(ptab[sym].get("sl_mult", 9) - c["sl_mult_atr30"]) < 1e-6 and abs(ptab[sym].get("tp_mult", 9) - c["tp_mult_r"]) < 1e-6
        if not p_ok:
            issues.append(f"参数表{sym}=sl{ptab[sym].get('sl_mult')}/tp{ptab[sym].get('tp_mult')} ≠ 规格sl{c['sl_mult_atr30']}/tp{c['tp_mult_r']} (修复=参数官重写表)")
        txt = open(path, encoding="utf-8").read()
        m1 = re.search(rf"^{re.escape(sl_key)}\s*=\s*([0-9.]+)", txt, re.M)
        m2 = re.search(rf"^{re.escape(tp_key)}\s*=\s*([0-9.]+)", txt, re.M)
        const_state[sym] = {"sl": float(m1.group(1)) if m1 else None, "tp": float(m2.group(1)) if m2 else None,
                             "spec_ref_sl_pts": c["ref_sl_pts"], "spec_tp_mult": c["tp_mult_r"]}
        if m2 and abs(float(m2.group(1)) - c["tp_mult_r"]) > 1e-6:
            issues.append(f"哨{sym} TP常量{m2.group(1)}≠规格{c['tp_mult_r']} (修复=执行岗)")
        if m1 and abs(float(m1.group(1)) - c["ref_sl_pts"]) / c["ref_sl_pts"] > 0.05:
            issues.append(f"哨{sym} SL常量{m1.group(1)}偏离规格{c['ref_sl_pts']}超5% (ATR漂移, 修复=参数官重锚+执行岗改脚本)")
        if not m1 or not m2:
            issues.append(f"哨{sym} 常量解析失败(脚本被改动?) (修复=研发岗取证)")
    # OOS 样本账本: deep_opt/v4 口径的平仓单
    closed, rows = 0, []
    if os.path.exists(LEDGER):
        for ln in open(LEDGER, encoding="utf-8"):
            try:
                r = json.loads(ln)
            except Exception:
                continue
            if r.get("ev") == "close" and r.get("sym") in cells and ("deep_opt" in str(r.get("params_ver", "")) or "v4" in str(r.get("params_ver", ""))):
                closed += 1
                rows.append({"ts": r.get("ts"), "sym": r.get("sym"), "side": r.get("side"),
                             "pnl_R": r.get("pnl_R"), "verdict": r.get("verdict")})
    q = json.load(open(Q, encoding="utf-8"))
    added = []
    for i in issues:
        tid = "param_officer_mismatch_" + now.replace("-", "").replace(" ", "T").replace(":", "")
        if tid not in q:
            q[tid] = {"id": tid, "sev": "P2", "status": "queued", "by": "param-officer", "ts": now,
                      "task": i, "owner_matrix": "参数表=参数官/哨常量=执行岗/脚本取证=研发岗/翻闸=chief"}
            added.append(tid)
    if closed >= need:
        tid6 = "oos30_gate6_flip_20261117"
        if tid6 not in q:
            q[tid6] = {"id": tid6, "sev": "P1", "status": "queued", "by": "param-officer", "ts": now,
                       "task": f"3格OOS{closed}笔满{need}笔, ⑥线翻闸待chief裁定(同分母五验+净R正才翻)",
                       "owner_matrix": "裁定=chief/L5; 台账=参数官"}
            added.append(tid6)
    if added:
        json.dump(q, open(Q, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    state = {"ts": now, "issues": issues, "oos_closed": closed, "oos_needed": need,
             "sentinel_constants": const_state, "tickets_added": added, "spec": spec["spec_id"]}
    json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # watchdog: 仅异常/里程碑时出声
    if issues:
        print(f"[参数官] 不一致{len(issues)}项: " + " | ".join(issues[:5]))
    elif added:
        print(f"[参数官] 样本{closed}/{need}笔; 新增工单: {added}")
    elif closed >= need:
        print(f"[参数官] OOS {closed}笔已满, ⑥线翻闸工单在案待chief")
    # 静默=正常

if __name__ == "__main__":
    main()
