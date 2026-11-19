import json

d = json.load(open(r"E:\GoldstrategyEngine\market_state.json", encoding="utf-8"))
ks = ["price","bias","adx","adx_regime","score","recommendation","momentum",
      "tc_consensus","tc_consistent","weekly_direction","dw_status","dw_confidence",
      "dl_direction","dl_confidence"]
out = []
for s, v in d["symbols"].items():
    out.append(s + " | " + " | ".join(f"{k}={v.get(k)}" for k in ks))
open(r"E:\GoldstrategyEngine\_parse_out4.txt", "w", encoding="utf-8").write("\n".join(out))
print("OK")
