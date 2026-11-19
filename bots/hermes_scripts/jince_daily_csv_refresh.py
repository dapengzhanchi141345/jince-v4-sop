# -*- coding: utf-8 -*-
"""金策·高流动性品种K线每日刷新(防断更) —— 07:30 日班
================================================================
背景(2026-11-12 数据地基事故): 现役 data/<SYM>_D1/H4/H1/M15.csv 曾停在 6-30,
且老 M15 比高周期偏 8h(时区错位)。workbuddy 已交付 tools/refresh_csv_fresh.py
(纯只读MT5拉取, 合并旧史+新鲜bar, 写 data/fresh/, 绝不覆盖现役)。
本脚本 = 每日 07:30: ①跑 refresh_csv_fresh.py ②REFRESH_REPORT 全 ok 才自动换入现役
(换前 md5 备份到 data/backup_csv_YYYYMMDD/) ③一行 stdout 汇报(异常才发声)。
红线: 只碰研究侧 CSV, 不碰 jince_live24.py / 实盘参数 / 账户。
"""
import os, sys, json, shutil, subprocess, datetime, hashlib, glob

ROOT = "E:/GoldstrategyEngine"
PY31312 = "D:/workbuddy/binaries/python/versions/3.13.12/python.exe"
REFRESH = os.path.join(ROOT, "tools", "refresh_csv_fresh.py")
FRESH = os.path.join(ROOT, "data", "fresh")
DATA = os.path.join(ROOT, "data")

def main():
    r = subprocess.run([PY31312, REFRESH], capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        print("金策CSV日刷: 失败 rc=%d stderr=%s" % (r.returncode, (r.stderr or r.stdout or "").strip()[-200:]))
        return
    rep = json.load(open(os.path.join(FRESH, "REFRESH_REPORT.json"), encoding="utf-8"))
    rows = rep.get("rows", [])
    bad = [x for x in rows if not x.get("ok")]
    if bad:
        print("金策CSV日刷: %d 项失败 %s (不换入)" % (len(bad), ",".join("%s_%s" % (x.get("sym"), x.get("tf")) for x in bad[:6])))
        return
    # 全 ok: md5 换入(跳过无变化)
    day = datetime.datetime.now().strftime("%Y%m%d")
    moved, skipped = 0, 0
    for f in sorted(glob.glob(os.path.join(FRESH, "*.csv"))):
        name = os.path.basename(f)
        dst = os.path.join(DATA, name)
        hm = hashlib.md5(open(f, "rb").read()).hexdigest()
        hd = hashlib.md5(open(dst, "rb").read()).hexdigest() if os.path.exists(dst) else ""
        if hm == hd:
            skipped += 1
            continue
        if os.path.exists(dst) and not os.path.exists(os.path.join(DATA, "backup_csv_%s" % day)):
            os.makedirs(os.path.join(DATA, "backup_csv_%s" % day))
        if os.path.exists(dst):
            shutil.move(dst, os.path.join(DATA, "backup_csv_%s" % day, name))
        shutil.copy2(f, dst)
        moved += 1
    print("金策CSV日刷: ok %d品种x4TF | 换入 %d 无变化 %d | 现役已追至 %s" % (len(rows), moved, skipped, rep.get("ts", "?")[:16]))

if __name__ == "__main__":
    main()
