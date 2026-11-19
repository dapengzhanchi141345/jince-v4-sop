
import json, os, time, glob, collections
base = r"E:\GoldstrategyEngine\data"
now = time.time()
wk = now - 7*86400
out = {}

# 1) veto_log 7d by type (strip RISK-NET-GATE noise)
vl = {}
try:
    p = os.path.join(base, "veto_log.jsonl")
    for l in open(p, encoding="utf-8", errors="replace"):
        l = l.strip()
        if not l: continue
        try: e = json.loads(l)
        except: continue
        ts = e.get("ts") or e.get("time") or 0
        try: ts = float(ts)
        except: ts = 0
        if ts >= wk:
            t = e.get("type") or e.get("kind") or e.get("gate") or "?"
            vl[t] = vl.get(t, 0) + 1
except Exception as ex: vl = {"err": str(ex)}
out["veto_7d"] = vl

# 2) rd_verify_batch latest pending
batches = sorted(glob.glob(os.path.join(base, "rd_verify_batch_*.json")))
nv = None
if batches:
    b = json.load(open(batches[-1], encoding="utf-8"))
    items = b.get("items", [])
    pend = [i for i in items if (i.get("status") in ("PENDING","WATCH",None)) or ("待" in json.dumps(i, ensure_ascii=False))]
    nv = {"file": os.path.basename(batches[-1]), "total": len(items), "pending": len(pend),
          "top": [i.get("hypo") or i.get("id") for i in pend[:3]]}
out["rd_batch"] = nv

# 3) edge_tracker session aggregation (30d closes, old-batch calibration)
et = json.load(open(os.path.join(base, "edge_tracker.json"), encoding="utf-8"))
syms = et.get("symbols", {})
tot = {"n":0,"w":0,"gw":0.0,"gl":0.0}
sess = collections.defaultdict(lambda: {"n":0,"w":0})
for s in syms.values():
    if not isinstance(s, dict): continue
    for tag, g in (s.get("session_tag") or {}).items():
        tot["n"] += g.get("n",0); tot["w"] += g.get("wins",0)
        tot["gw"] += g.get("gross_w",0.0); tot["gl"] += g.get("gross_l",0.0)
        k = tag.split(":")[0]
        sess[k]["n"] += g.get("n",0); sess[k]["w"] += g.get("wins",0)
pf = (tot["gw"]/tot["gl"]) if tot["gl"]>0 else (99 if tot["gw"]>0 else 0)
out["edge"] = {"n": tot["n"], "wr": round(tot["w"]/tot["n"],3) if tot["n"] else 0, "pf": round(pf,3),
               "sess": dict(sess), "updated": et.get("updated")}

# 4) freeze state + live book
rf = json.load(open(os.path.join(base, "risk_freeze_state.json"), encoding="utf-8"))
out["freeze"] = {"level": rf.get("level"), "ts_age_min": round((now - rf.get("ts",now))/60,1),
                 "pol": rf.get("policy"), "pos": rf.get("positions"), "pend": rf.get("pending_orders")}

# 5) discussion_log 7d node counts
cnt = collections.Counter()
p = os.path.join(base, "discussion_log.jsonl")
if os.path.exists(p):
    for l in open(p, encoding="utf-8", errors="replace"):
        l = l.strip()
        if not l: continue
        try: e = json.loads(l)
        except: continue
        ts = e.get("ts") or 0
        try: ts = float(ts)
        except: ts = 0
        if ts >= wk: cnt[e.get("node","?")] += 1
out["nodes_7d"] = dict(cnt)

# 6) event risk
try:
    er = json.load(open(os.path.join(base, "event_risk.json"), encoding="utf-8"))
    evs = er.get("events", [])
    hi = [e for e in evs if "HIGH" in str(e.get("impact", e.get("level","")))]
    out["events"] = {"level": er.get("level"), "n_total": len(evs), "n_high": len(hi),
                     "titles": [str(e.get("title"))[:40] for e in hi[:5]]}
except Exception as ex:
    out["events"] = {"err": str(ex)}

print(json.dumps(out, ensure_ascii=False, indent=1))
