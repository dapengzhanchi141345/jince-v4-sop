
import json, time, os
base = r"E:\GoldstrategyEngine\data"
T1 = ['BTCUSD','ETHUSD','SOLUSD','BNBUSD','XRPUSD','ADAUSD','DOGEUSD','LTCUSD','BCHUSD','DOTUSD','POLUSD','UNIUSD','XLMUSD','KSMUSD','TAOUSD','XTZUSD']
et = json.load(open(os.path.join(base,"edge_tracker.json"), encoding="utf-8"))
syms = et["symbols"]

rows, tot_n, tot_w, tot_wl, tot_ll = {}, 0, 0.0, 0.0, 0.0
n_with_data = 0
for s in T1:
    v = syms.get(s) or {}
    n = v.get("n", 0)
    if n > 0: n_with_data += 1
    gw = v.get("gross_w", 0.0) or 0.0
    gl = v.get("gross_l", 0.0) or 0.0
    rows[s] = {"n": n, "wr": v.get("wr"), "pf": v.get("pf"), "gross_w": gw, "gross_l": gl, "exp_R": v.get("exp_R")}
    tot_n += n; tot_wl += gw; tot_ll += gl
pf_all = (tot_wl / tot_ll) if tot_ll > 0 else None

# 分盘口 8 组同分母口径（session_tag）
sess_groups = {}
for s in T1:
    for g, gv in (syms.get(s, {}).get("session_tag") or {}).items():
        a = sess_groups.setdefault(g, {"n":0, "w":0, "gw":0.0, "gl":0.0})
        a["n"] += gv.get("n",0); a["gw"] += gv.get("gross_w",0.0) or 0; a["gl"] += gv.get("gross_l",0.0) or 0
        a["w"] += int(round((gv.get("wr") or 0) * gv.get("n",0)))

baseline = {
  "id": "v15_v16_baseline_T1regime",
  "ts": int(time.time()),
  "note": "B-arm baseline (current deterministic regime routing, no ML) on T1 16 crypto, from edge_tracker same-denom session-tag groups. A-arm (Mamba zero-warmup / Mantis reject-gate) runs same-denom after extnet unlock; risk-officer re-computes on full event set.",
  "universe": T1,
  "source": "edge_tracker.json symbols[T1] + session_tag groups; updated ts=%d" % et.get("updated", 0),
  "n_symbols_with_data": n_with_data,
  "n_events_total": tot_n,
  "pf_amount": round(pf_all, 4) if pf_all is not None else None,
  "gross_w": round(tot_wl, 2), "gross_l": round(tot_ll, 2),
  "exp_R_available": all((syms.get(s,{}).get("exp_R") is not None) for s in T1 if (syms.get(s) or {}).get("n",0)>0),
  "by_symbol": rows,
  "by_session_group": {k: {kk: vv for kk,vv in v.items()} for k,v in sess_groups.items()},
  "caveats": [
    "sample is T1-16 only, n small; most volume is magic 20260708 teaching batch, NOT live P4",
    "exp_R null in edge_tracker (R-based needs per-deal R, currently amount-based PF only)",
    "BLOCKED: this file is the B-arm only; A-arm requires extnet + mamba_ssm/transformers + HF weights"
  ],
}
out = os.path.join(base, "v15_v16_baseline_T1regime.json")
json.dump(baseline, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("WROTE", out)
print("n_with_data=%d n_events=%d PF_amount=%s gw=%.2f gl=%.2f expR_avail=%s" % (n_with_data, tot_n, baseline["pf_amount"], tot_wl, tot_ll, baseline["exp_R_available"]))
print("session groups:", json.dumps(baseline["by_session_group"], ensure_ascii=False))
