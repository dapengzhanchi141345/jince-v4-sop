# -*- coding: utf-8 -*-
"""Hermes 26 bot 弹药库升级规划 · 月扫脚本（确定性层，不烧 LLM）
用法: python bot_sota_scan.py [--force]
  默认: 列出所有 *-sota / *-skills 技能中【上次刷新(日期戳或mtime)距今 >90天】的待升级清单 + 建议批次(每批≤4个防429)
  --force: 输出全量清单(不过滤周期)
输出: 人读 markdown + 机读 JSON(E:/GoldstrategyEngine/data/bot_sota_scan_last.json)
升级动作由 Hermes cron(每月1日/15日 03:30) 触发 LLM 会话执行; 本脚本只做扫描排班。
"""
import os, re, json, time, datetime, argparse, sys

PROFILES = r"E:/workbuddy/国外模型/hermes/profiles"
OUT_JSON = r"E:/GoldstrategyEngine/data/bot_sota_scan_last.json"
AGE_DAYS = 90
BATCH = 4          # 每批最多4个sota，防429免费池连崩
SKIP_PREFIXES = ("skill-", "teaching-", "calc-", "model-", "yuanbao", "doc-", "golden-")

def refresh_date(path):
    """技能里最近一个'检索日/刷新日 YYYY-MM-DD'戳，没有则用文件mtime。"""
    txt = open(path, encoding="utf-8", errors="replace").read()
    dates = re.findall(r"(20\d\d)-(\d\d)-(\d\d)", txt)
    best = None
    for y, m, d in dates:
        try:
            dt = datetime.date(int(y), int(m), int(d))
            if dt.year <= datetime.date.today().year + 1:  # 排除未来/远古干扰
                if best is None or dt > best:
                    best = dt
        except ValueError:
            pass
    if best:
        return best.isoformat() + " (戳)"
    return time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(path))) + " (mtime)"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    rows, due = [], []
    today = datetime.date.today()
    for p in sorted(os.listdir(PROFILES)):
        sd = os.path.join(PROFILES, p, "skills")
        if not os.path.isdir(sd):
            continue
        for sk in sorted(os.listdir(sd)):
            if sk.startswith(SKIP_PREFIXES):
                continue
            f = os.path.join(sd, sk, "SKILL.md")
            if not os.path.exists(f):
                continue
            rd = refresh_date(f)
            rd_date = datetime.date.fromisoformat(rd[:10])
            age = (today - rd_date).days
            row = {"profile": p, "skill": sk, "last_refresh": rd, "age_days": age, "bytes": os.path.getsize(f)}
            rows.append(row)
            if args.force or age > AGE_DAYS:
                due.append(row)
    due.sort(key=lambda r: -r["age_days"])
    batches = [due[i:i + BATCH] for i in range(0, len(due), BATCH)]
    now = time.strftime("%Y-%m-%d %H:%M")
    lines = [f"# bot SOTA 弹药库升级扫描 ({now})",
             f"周期铁律: 刷新日距今 >{AGE_DAYS} 天 才进升级队列; 每批 ≤{BATCH} 个防429; 没到期=不动, 如实报'无到期项'。",
             ""]
    if due:
        for i, b in enumerate(batches, 1):
            lines.append(f"## 批次{i} (待升级 {len(b)}个)")
            for r in b:
                lines.append(f"- {r['profile']}/{r['skill']}  距上次刷新 {r['age_days']}天 (最后 {r['last_refresh']})")
            lines.append("")
    else:
        lines.append("## 无到期项 — 全部技能均在周期内，本轮不升级（静默跳过，不烧LLM）。")
    lines.append(f"\n总计 {len(rows)} 个弹药库技能, 到期 {len(due)} 个, 分 {len(batches)} 批。")
    out_md = "\n".join(lines)
    print(out_md)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump({"scan_time": now, "age_days": AGE_DAYS, "batch_size": BATCH,
               "all": rows, "due": due, "batches": batches},
              open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n[OK] 机读清单已落盘 {OUT_JSON}")
    # 退出码: 有到期项=1(提醒cron LLM去做), 无=0
    sys.exit(1 if due else 0)

if __name__ == "__main__":
    main()
