# -*- coding: utf-8 -*-
import os, json, time, glob
DATA = r"E:\GoldstrategyEngine\data"
# 找今早 10:05 附近生成的 midday 产物
now = time.time()
pats = [os.path.join(DATA,"jince_midday*.json"), os.path.join(DATA,"midday*.json"),
        os.path.join(DATA,"*asia*"), os.path.join(DATA,"discussion_log*.json"),
        os.path.join(DATA,"discussion_log*.md")]
files=[]
for pat in pats:
    files += glob.glob(pat)
for f in files:
    if os.path.exists(f):
        print("存在:", os.path.basename(f), "| 大小=%d | mtime=%s" % (os.path.getsize(f), time.strftime("%H:%M", time.localtime(os.path.getmtime(f)))))
# discussion_log 最新条目 (节点投群留痕)
dl = os.path.join(DATA,"discussion_log.json")
if os.path.exists(dl):
    d=json.load(open(dl,encoding="utf-8"))
    rows = d.get("entries", d) if isinstance(d,dict) else d
    if isinstance(rows,list):
        for r in rows[-5:]:
            print("  log:", str(r)[:150])
