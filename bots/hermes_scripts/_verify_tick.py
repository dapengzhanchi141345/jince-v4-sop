
print("[2] 实跑 rc =", r.returncode)
if r.stdout.strip():
    print(r.stdout.strip()[:500])
if r.stderr.strip():
    print("stderr:", r.stderr.strip()[:300])

print("[3] 远端 tick_live 最新喂时间:")
rr = subprocess.run(["gh", "api", "-H", "User-Agent: tv",
                     "repos/dapengzhanchi141345/jince-trading-dashboard/contents/tick_live.json",
                     "--jq", ".content"], capture_output=True, text=True, timeout=60, creationflags=0x08000000)
if rr.returncode == 0:
    txt = base64.b64decode(rr.stdout).decode()
    import json
    d = json.loads(txt)
    print("   远端 feed =", d.get("beijing"), "| n =", d.get("n"))
else:
    print("   读不到:", rr.stderr[:150])

# 本地对照
lp = r"E:\GoldstrategyEngine\data\tick_live.json"
d2 = json.load(open(lp, encoding="utf-8"))
print("[4] 本地 feed =", d2.get("beijing"), "| n =", d2.get("n"))
