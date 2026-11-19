import json

d = json.load(open(r"E:\GoldstrategyEngine\market_state.json", encoding="utf-8"))
out = []
out.append("TC_SUMMARY=" + json.dumps(d.get("tc_consistency_summary", {}), ensure_ascii=False, indent=1))
x = d["symbols"]["XAUUSD"]
out.append("SYMBOL_KEYS=" + ",".join(list(x.keys())))
out.append("XAUUSD_FULL=" + json.dumps(x, ensure_ascii=False, indent=1, default=str))
open(r"E:\GoldstrategyEngine\_parse_out3.txt", "w", encoding="utf-8").write("\n".join(out))
print("OK")
