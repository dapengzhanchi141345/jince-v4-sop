import json, os, time

p = r"E:\GoldstrategyEngine\market_state.json"
out = []
out.append("MTIME=" + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(p))))
d = json.load(open(p, encoding="utf-8"))

def walk(o, prefix="", depth=0):
    if depth > 2:
        return
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, (dict, list)):
                out.append("  " * depth + f"[{prefix}{k}] type={type(v).__name__} len={len(v)}")
                walk(v, "", depth + 1)
            else:
                out.append("  " * depth + f"{prefix}{k} = {v}")

# top-level keys
out.append("TOP KEYS: " + ", ".join(list(d.keys())))
for k, v in d.items():
    if not isinstance(v, (dict, list)):
        out.append(f"TOP {k} = {v}")

out.append("---- FULL JSON (truncated per symbol) ----")
out.append(json.dumps(d, ensure_ascii=False, indent=1)[:20000])

open(r"E:\GoldstrategyEngine\_tmp_state_summary.txt", "w", encoding="utf-8").write("\n".join(out))
print("OK")
