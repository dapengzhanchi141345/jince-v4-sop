
import json, os, time, glob, datetime
now = time.time()
base = r"E:\\GoldstrategyEngine\\data"
def age_h(ts): return round((now-ts)/3600,1) if isinstance(ts,(int,float)) else ts

# 1) edge_tracker 是否比上轮 1100 笔前进
et = json.load(open(os.path.join(base,"edge_tracker.json"), encoding="utf-8"))
syms = et["symbols"]
tot_n = sum((v.get("n",0) or 0) for v in syms.values())
tot_gw = sum((v.get("gross_w",0) or 0) for v in syms.values())
tot_gl = sum((v.get("gross_l",0) or 0) for v in syms.values())
pf = round(tot_gw/tot_gl,4) if tot_gl>0 else None
print("edge_tracker: 品种=%d 事件=%d PF=%s updated_age_h=%s" % (len(syms), tot_n, pf, age_h(et.get("updated",0))))

# 2) leg_polish / 新裁决 是否新增（近 3 天 mtime）
cutoff = now - 3*86400
new_polish = []
for f in glob.glob(os.path.join(base,"leg_*_polish.json")):
    if os.path.getmtime(f) >= cutoff: new_polish.append((os.path.basename(f), age_h(os.path.getmtime(f))))
print("近3天新增 leg_polish:", new_polish or "无")

# 3) 4 条 BLOCKED 现状（extnet 探活 + 批次状态）
def probe_extnet():
    import urllib.request, socket
    socket.setdefaulttimeout(4)
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=4) as r:
            return "UP " + r.read().decode().strip()
    except Exception as e:
        return "DOWN (%s)" % type(e).__name__
print("extnet:", probe_extnet())
for fn in ["rd_verify_batch_metatrader_study_20261005.json","rd_verify_batch_exness_study_20261005.json"]:
    p = os.path.join(base, fn)
    if os.path.exists(p):
        b = json.load(open(p, encoding="utf-8"))
        print(fn, "->", [(i.get("id"), i.get("status")) for i in b.get("items",[])])

# 4) rd_decisions 条数 + 最近一条
rd = json.load(open(os.path.join(base,"rd_decisions.json"), encoding="utf-8"))
ds = rd.get("decisions",[])
print("rd_decisions 条数:", len(ds), "| 最后一条:", ds[-1].get("id") if ds else None)

# 5) R 回填：新批次带 SL 单到底有几笔（这是门2能否开跑的真前置）
import MetaTrader5 as mt5
if mt5.initialize():
    o = mt5.history_orders_get(now-30*86400, now) or ()
    d = mt5.history_deals_get(now-30*86400, now) or ()
    sl_orders = [x for x in o if x.sl and x.sl>0]
    print("30d 开仓单带SL笔数:", len(sl_orders), "| 30d 平仓deals:", len(d), "| 可算R分母(带SL)=", len(sl_orders))
    mt5.shutdown()
