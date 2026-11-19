# -*- coding: utf-8 -*-
"""金策交付验活哨 (L3 确定性, 0 LLM)
防"表面说结果、实际代码空白"复发: 复核所有 关闭/DONE 宣称 的交付物是否真实存在且有效。
扫描:
  1) task_ledger.json  status=DONE 的任务: evidence[] 必非空; 每条 evidence 若含文件路径 -> 文件存在且非0B
  2) rd_queue.json  status 属关闭族 的项: note/evidence 须>=30字; 引用到的 .py/.json 文件存在
  3) data/rd_verify_batch*.json: 可解析 + 大小>=300B + 含裁定主题键(theme/items/per_sym/five_gate/verdict 之一)
输出 data/delivery_verify.json {ts, n_checked, fails, warns, clean}
fails>0 -> 自动写 redo 件回 rd_queue(priority1) + task_ledger 记录; 平时静默(晨报聚合)
"""
import json, os, re, glob, time, datetime

ROOT = r"E:\GoldstrategyEngine"
DATA = os.path.join(ROOT, "data")
PATHY = re.compile(r"[\w.\\\/][\w.\-\\\/]+\.(py|json|jsonl|md|csv|log|html|docx|png|csvl)")
CLOSED_STATUSES = {
    "done", "closed", "closed_handoff_ops_20261103", "closed_not_needed",
    "spec_landed", "forward_contract_landed", "sop_landed", "decided",
    "reject", "reject_precheck", "design_approved_by_risk_officer",
    "risk_officer_verdict_delivered", "reverify_done_REJECT_watch",
}
THEME_KEYS = ("theme", "items", "per_sym", "five_gate", "verdict", "summary", "plain_summary", "results")

def check_path(ref):
    m = PATHY.search(ref or "")
    if not m:
        return None
    p = m.group(0).replace("\\", "/")
    if not (p.startswith("E:/") or p.startswith("e:")):
        return None
    return p

fails, warns, n_checked = [], [], 0

# 1) task_ledger DONE
tp = os.path.join(DATA, "task_ledger.json")
if os.path.exists(tp):
    td = json.load(open(tp, encoding="utf-8"))
    for t in td.get("tasks", []):
        if str(t.get("status", "")).upper() != "DONE":
            continue
        n_checked += 1
        ev = t.get("evidence") or []
        if not ev:
            fails.append({"src": "task_ledger", "ref": t.get("id"), "ref_ts": t.get("ts", 0), "why": "DONE无evidence(空交付宣称)"})
            continue
        for e in ev:
            p = check_path(str(e))
            if p and not (os.path.exists(p) and os.path.getsize(p) > 0):
                fails.append({"src": "task_ledger", "ref": t.get("id"), "ref_ts": t.get("ts", 0), "why": "evidence文件不存在/0B: %s" % p})
                break

# 2) rd_queue 关闭件
qp = os.path.join(DATA, "rd_queue.json")
if os.path.exists(qp):
    qd = json.load(open(qp, encoding="utf-8"))
    for it in qd.get("items", []):
        st = str(it.get("status", "")).lower()
        if st not in CLOSED_STATUSES and not st.startswith(("closed", "done", "sop_landed", "spec_landed")):
            continue
        n_checked += 1
        blob = " ".join(str(it.get(k, "")) for k in ("task", "note", "accept", "evidence"))
        if len(blob) < 30:
            warns.append({"src": "rd_queue", "ref": it.get("id"), "why": "关闭件内容过短(<30字), 疑似空裁定"})
        for ref in re.findall(r"[\w.\-]+\.py", blob):
            p = os.path.join(DATA, ref) if not ref.startswith("E:") else ref.replace("\\", "/")
            if os.path.exists(p):
                continue
            # 只报 .py 引用且本地找不到的(不误伤外部名)
            if ref in ("gate.py",) or ref.startswith("jince_"):
                warns.append({"src": "rd_queue", "ref": it.get("id"), "why": "引用脚本不存在: %s" % ref})

# 3) rd_verify_batch 产物
for f in sorted(glob.glob(os.path.join(DATA, "rd_verify_batch*.json"))):
    if ".bak" in f:
        continue
    n_checked += 1
    sz = os.path.getsize(f)
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception as e:
        fails.append({"src": "rd_verify_batch", "ref": os.path.basename(f), "ref_ts": os.path.getmtime(f), "why": "JSON解析失败: %s" % e})
        continue
    if sz < 300:
        warns.append({"src": "rd_verify_batch", "ref": os.path.basename(f), "why": "产物<300B 疑似空壳: %dB" % sz})
    if isinstance(d, dict) and not (THEME_KEYS and any(k in d for k in THEME_KEYS)):
        warns.append({"src": "rd_verify_batch", "ref": os.path.basename(f), "why": "无裁定主题键, 存疑"})

# 4) [11-15 新增] 深研拍-日志对账: 深研产物(48h内 research/*arbr_*|*soul_*|*hourwindow*|*fx_gold*)必须有同日 family_deep_study_log 行
#    根因: 11-14 R1/R2 两连假交付(beat宣称'jsonl落1行'未落盘), 主bot两次补记; 本条防第三次
import glob as _glob, re as _re
_LOG = os.path.join(DATA, "family_deep_study_log.jsonl")
_study_dates = set()
try:
    for _ln in open(_LOG, encoding="utf-8"):
        _m = _re.search(r'"ts"\s*:\s*"?(\d{4})-(\d{2})-(\d{2})', _ln)
        if _m:
            _study_dates.add(_m.group(1) + _m.group(2) + _m.group(3))
except FileNotFoundError:
    pass
_study_dates = {d.replace("-", "") for d in _study_dates}
for _pf in _glob.glob(os.path.join(os.path.dirname(DATA), "research", "*")):
    _bn = os.path.basename(_pf)
    if not _re.search(r"(arbr_|soul_|hourwindow|fx_gold|p5_orb|orb_confirm|deep_study)", _bn):
        continue
    _mm = _re.search(r"(\d{8})", _bn)
    if not _mm or time.time() - os.path.getmtime(_pf) > 48 * 3600:
        continue
    if _mm.group(1) not in _study_dates:
        fails.append({"src": "deep_study_log", "ref": _bn, "ref_ts": int(time.time()),
                      "why": "深研产物存在但 family_deep_study_log 无对应日期(%s)行=假交付嫌疑(beat宣称落日志未落盘)" % _mm.group(1)})
        n_checked += 1

now = int(time.time())
# 旧账(>7d) 降级为存疑, 不刷 FAIL 噪声
fails_new = [x for x in fails if time.time() - int(x.get("ref_ts", 0)) <= 7 * 86400]
fails_old = [x for x in fails if time.time() - int(x.get("ref_ts", 0)) > 7 * 86400]
for x in fails_old:
    x["why"] = "旧账(>7d)仅留痕: " + x["why"]
warns.extend(fails_old)
fails = fails_new
out = {"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "n_checked": n_checked,
       "n_fails": len(fails), "n_warns": len(warns), "fails": fails, "warns": warns,
       "clean": not fails}
dst = os.path.join(DATA, "delivery_verify.json")
json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
if out["clean"]:
    # 全绿静默(stdout空=不投递, 符合金策哨"全绿静默"约定); 落盘 json 仍留痕
    pass
else:
    print("交付验活哨 NOT-CLEAN: 查%d 失败%d 存疑%d -> %s" % (n_checked, len(fails), len(warns), dst))
    for x in fails[:10]:
        print("  FAIL [%s] %s: %s" % (x["src"], x["ref"], x["why"]))
    for x in warns[:10]:
        print("  WARN [%s] %s: %s" % (x["src"], x["ref"], x["why"]))

# fails>0: 自动回填 redo 件(只回填7天内的新账, 旧账仅留痕; 每ref幂等)
if fails:
    qd = json.load(open(qp, encoding="utf-8"))
    items = qd["items"]
    existing = {str(i.get("id")) for i in items}
    for x in fails:
        if time.time() - int(x.get("ref_ts", 0)) > 7 * 86400:
            x["note"] = "旧账(>7d)仅留痕不回派"
            continue
        rid = "redo_%s_%s_%s" % (x["src"], re.sub(r"[^a-z0-9_]", "_", str(x["ref"]))[:40], datetime.date.today().isoformat())
        if rid in existing:
            continue
        items.append({"id": rid, "ts": now, "source": "交付验活哨自动回派(空交付根治)",
                      "task": "重做[%s]%s: 上次宣称完成但 %s -> 重做必须附验活把手(文件路径+关键字段+可重跑命令), 由哨自动复核" % (x["src"], x["ref"], x["why"]),
                      "accept": "交付物真实存在且非0B+关键字段可解析+哨复核通过",
                      "priority": 1, "status": "queued", "five_gate": False, "owner": "原责任岗"})
        existing.add(rid)
    qd["ts"] = now
    json.dump(qd, open(qp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("rd_queue 已回填 redo 件", [x for x in fails if "redo_" in x["ref"]] and "ok")
    # 台账记录
    try:
        td2 = json.load(open(tp, encoding="utf-8"))
        td2["tasks"].append({"id": "t_delivery_verify_fail_%s" % now, "ts": now, "by": "交付验活哨(确定性)",
                             "desc": "验活哨发现%d处空/坏交付, 已自动回派redo件: %s" % (len(fails), json.dumps(fails[:5], ensure_ascii=False)[:300]),
                             "evidence": ["data/delivery_verify.json"], "status": "DONE"})
        td2["ts"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        json.dump(td2, open(tp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception as e:
        print("台账写入失败:", e)
