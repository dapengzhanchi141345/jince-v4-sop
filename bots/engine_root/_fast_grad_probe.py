
import json, os, time, glob
now = time.time()
base = r"E:\\GoldstrategyEngine\\data"

# 1) ORB60 相关产物：leg_polish / rd_decisions / edge_tracker
hits = [f for f in os.listdir(base) if "orb" in f.lower()]
print("盘上 ORB 相关文件:", hits or "无")
rd = json.load(open(os.path.join(base,"rd_decisions.json"), encoding="utf-8"))
for d in rd.get("decisions",[]):
    s = json.dumps(d, ensure_ascii=False)
    if "orb" in s.lower() or "ORB" in s:
        print("rd_decision 命中:", s[:300])
et = json.load(open(os.path.join(base,"edge_tracker.json"), encoding="utf-8"))
orb_syms = {k:v for k,v in et.get("symbols",{}).items() if "orb" in json.dumps(v).lower()}
print("edge_tracker 含 orb 键的品种:", len(orb_syms))
# legs 层（若有）
legs = et.get("legs") or {}
print("edge_tracker.legs 顶层:", list(legs.keys())[:20])
for k,v in legs.items():
    if "orb" in k.lower() or "orb" in json.dumps(v).lower():
        print("LEG:", k, json.dumps(v, ensure_ascii=False)[:300])

# 2) DST / 币系冻结 / 开单闸实拉
for fn in ["risk_state.json","pending_orders_state.json","dst_freeze_state.json","crypto_cooldown.json","risk_freeze_state.json"]:
    p = os.path.join(base, fn)
    if os.path.exists(p):
        t = open(p, encoding="utf-8").read()[:600]
        print("----", fn, ":", t.replace("\\n"," ")[:400])

# 3) 本地 FX 数据量（T2 攒样本原料在不在盘上）
mroot = r"E:\\GoldstrategyEngine"
import subprocess
cnt = subprocess.run(["powershell","-NoProfile","-Command",
  r"Get-ChildItem -Path 'E:\GoldstrategyEngine\data\history','E:\GoldstrategyEngine\cache\history' -Recurse -File -ErrorAction SilentlyContinue | Measure-Object | Select -Expand Count"],
  capture_output=True, text=True, creationflags=0x08000000).stdout.strip()
print("本地 history 文件数:", cnt)
