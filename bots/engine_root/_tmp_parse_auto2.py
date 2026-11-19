import json, os, datetime, io

out = io.StringIO()
p = r"E:\GoldstrategyEngine\market_state.json"
st = os.path.getmtime(p)
out.write("market_state.json mtime=%s\n" % datetime.datetime.fromtimestamp(st).strftime("%Y-%m-%d %H:%M:%S"))

d = json.load(open(p, encoding="utf-8"))
out.write("TOPKEYS=%s\n" % list(d.keys()))

sy = d.get("symbols", d)
out.write("\n=== SYMBOLS ===\n")
for k, v in sy.items():
    if not isinstance(v, dict):
        continue
    out.write("%s | score=%s | bias=%s | signal=%s | price=%s | adx=%s | rsi=%s | dtrend=%s | wtrend=%s | dw=%s | sup=%s | res=%s\n" % (
        k, v.get("bias_score"), v.get("bias") or v.get("bias_code"), v.get("signal"),
        v.get("price") or v.get("current_price"), v.get("adx"), v.get("rsi"),
        v.get("daily_trend"), v.get("weekly_trend"), v.get("dw_status") or v.get("d_w_alignment"),
        v.get("support"), v.get("resistance")))

out.write("\n=== TC ===\n")
for key in ("tc_consistency", "tc_consensus_meta", "tc_summary", "consistency"):
    if key in d:
        out.write("%s = %s\n" % (key, json.dumps(d[key], ensure_ascii=False)))

out.write("\n=== OTHER TOP ===\n")
for k, v in d.items():
    if k in ("symbols",):
        continue
    if not isinstance(v, (dict, list)):
        out.write("%s = %s\n" % (k, v))

open(r"E:\GoldstrategyEngine\_tmp_parse_auto2.txt", "w", encoding="utf-8").write(out.getvalue())
print("OK")
