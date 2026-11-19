import json, io, os, datetime

p = r"E:\GoldstrategyEngine\market_state.json"
out = []
out.append("FILE_MTIME=" + datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S"))
d = json.load(open(p, encoding="utf-8"))

top_keys = [k for k in d.keys()]
out.append("TOP_KEYS=" + ",".join(top_keys))

# tc meta
for k in top_keys:
    if "tc" in k.lower() and not isinstance(d[k], dict):
        out.append(f"{k}={d[k]}")
if "tc_consensus_meta" in d:
    out.append("TC_META=" + json.dumps(d["tc_consensus_meta"], ensure_ascii=False))
if "generated_at" in d:
    out.append("GENERATED_AT=" + str(d["generated_at"]))
if "timestamp" in d:
    out.append("TIMESTAMP=" + str(d["timestamp"]))

syms = d.get("symbols", d.get("markets", {}))
out.append("SYMBOL_COUNT=" + str(len(syms)))
for s, v in syms.items():
    if not isinstance(v, dict):
        continue
    keys = list(v.keys())
    out.append("=" * 60)
    out.append("SYMBOL=" + s)
    out.append("KEYS=" + ",".join(keys))
    for k in keys:
        val = v[k]
        if isinstance(val, (dict, list)):
            out.append(f"  {k}={json.dumps(val, ensure_ascii=False)[:600]}")
        else:
            out.append(f"  {k}={val}")

with io.open(r"E:\GoldstrategyEngine\_parse_out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("OK")
