import json, io
d = json.load(open(r"E:\GoldstrategyEngine\market_state.json", encoding="utf-8"))
out = io.StringIO()
out.write("=== tc_consistency_summary ===\n")
out.write(json.dumps(d.get("tc_consistency_summary"), ensure_ascii=False, indent=1) + "\n")
out.write("\n=== FULL SYMBOL DICT (XAUUSD sample keys) ===\n")
first = list(d["symbols"].values())[0]
out.write(str(list(first.keys())) + "\n")
out.write("\n=== ALL SYMBOLS FULL ===\n")
out.write(json.dumps(d["symbols"], ensure_ascii=False, indent=1) + "\n")
open(r"E:\GoldstrategyEngine\_tmp_parse_auto3.txt", "w", encoding="utf-8").write(out.getvalue())
print("OK")
