import json, os, datetime

p = r"E:\GoldstrategyEngine\market_state.json"
out = []
out.append("FILE_MTIME=" + datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S"))
d = json.load(open(p, encoding="utf-8"))

def g(o, *keys, default=None):
    for k in keys:
        if isinstance(o, dict) and k in o:
            return o[k]
    return default

out.append("TOP_KEYS=" + ",".join(list(d.keys())))
out.append("GENERATED=" + str(g(d, "generated_at", "timestamp", "updated_at")))
out.append("TC_META=" + json.dumps(g(d, "tc_consensus_meta", default={}), ensure_ascii=False))

syms = d.get("symbols", d)
for s, v in syms.items():
    if not isinstance(v, dict):
        continue
    line = {
        "sym": s,
        "score": g(v, "score", "total_score"),
        "rec": g(v, "recommendation", "action"),
        "bias": g(v, "bias", "trend_bias", "daily_bias"),
        "adx": g(v, "adx", "ADX"),
        "trend": g(v, "trend_strength", "trend_state"),
        "price": g(v, "price", "current_price", "close"),
        "mom": g(v, "momentum", "momentum_state"),
        "wk": g(v, "weekly_trend", "weekly_bias"),
        "dw": g(v, "dw_alignment", "daily_weekly", "dw_state"),
        "dwc": g(v, "dw_confidence"),
        "tc": g(v, "tc_consensus", "tc_bias"),
        "tcm": g(v, "tc_match", "tc_consistency", "tc_agreement"),
        "sup": g(v, "support"),
        "res": g(v, "resistance"),
        "dl": g(v, "dl_signal", "dl_direction", "dl_combined"),
        "dlc": g(v, "dl_confidence"),
    }
    out.append(json.dumps(line, ensure_ascii=False, default=str))

open(r"E:\GoldstrategyEngine\_parse_out2.txt", "w", encoding="utf-8").write("\n".join(out))
print("OK")
