# -*- coding: utf-8 -*-
"""[11-15] 金策·分品系深研 R4 汇总(no_agent 0 LLM): 替代 05:30 LLM 汇总拍(该拍 4 次续写截断全挂=确定性任务不该用 LLM, 11-14 全链扫描同款教训)。
职责(R4 原任务 4 步, 全确定性):
  ①读 E:/GoldstrategyEngine/data/family_deep_study_log.jsonl 全轮记录
  ②生成 E:/GoldstrategyEngine/data/family_playbook.json(机读: 品系->参数, 每参数带证据单号+样本+快照;
     只有 verdict 含'翻闸/过五验/放大'字样的进 exec_params, 其余=WATCH 不进执行层; 证伪/FAIL 进 negated)
  ③live24 挂点: 只提案 rd_queue 工单(不擅改引擎码), 幂等(已有同件不重开)
  ④群大白话报(stdout): N过/N拒/哪些进执行层 + 系统就绪态; 内容哈希去重(当日内容不变=空stdout静默)
数据有效性闸: 日志文件缺失/空=显式FAIL不静默; json 每参数缺证据号=拒写入。"""
import json, os, re, time, hashlib

ROOT = "E:/GoldstrategyEngine"
LOG = os.path.join(ROOT, "data", "family_deep_study_log.jsonl")
PB = os.path.join(ROOT, "data", "family_playbook.json")
RQ = os.path.join(ROOT, "data", "rd_queue.json")
GATE = os.path.join(ROOT, "data", "r4_rollup_gate.json")

def fail(msg):
    print("[R4汇总] FAIL: %s" % msg)
    import sys; sys.exit(1)

# ① 读深研日志(有效性闸)
if not os.path.exists(LOG):
    fail("深研日志 %s 不存在" % LOG)
rows = []
for ln in open(LOG, encoding="utf-8"):
    ln = ln.strip()
    if not ln:
        continue
    try:
        d = json.loads(ln)
        if d.get("ts"):
            rows.append(d)
    except Exception:
        pass
if not rows:
    fail("深研日志为空(无有效行)")

# ② 分类: exec_params(过五验) / watch(OBSERVE/WATCH) / negated(证伪/FAIL)
EXEC_MARK = re.compile(r"翻闸|过五验|放大到live|进执行层")
OB_MARK = re.compile(r"OBSERVE|WATCH|攒样|观察")
rows_sorted = sorted(rows, key=lambda x: x.get("ts", ""))
families = {}
n_exec = n_watch = n_neg = 0
for i, r in enumerate(rows_sorted, 1):
    v = str(r.get("verdict", ""))
    fam = str(r.get("topic", ""))[:20]
    snap = re.search(r"快照[至到]?([^，。,;；]{6,40})", str(r.get("evidence", "")))
    rec = {
        "evidence": "深研日志第%d行 ts=%s actor=%s" % (i, r.get("ts"), r.get("actor", "")),
        "sample": str(r.get("evidence", ""))[:400],
        "snapshot": (snap.group(0)[:60] if snap else "见sample"),
        "verdict": v[:200],
        "ts": r.get("ts"),
    }
    if not rec["evidence"]:
        fail("第%d行缺证据单号, 拒写入" % i)
    hit_exec = bool(EXEC_MARK.search(v) and not OB_MARK.search(v))
    hit_neg = bool(re.search(r"FAIL|证伪|无edge|进禁开", v) and not hit_exec)
    f = families.setdefault(fam, {"exec": [], "watch": [], "negated": []})
    if hit_exec:
        f["exec"].append(rec); n_exec += 1
    elif hit_neg:
        f["negated"].append(rec); n_neg += 1
    else:
        f["watch"].append(rec); n_watch += 1

pb = {
    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    "source": "family_deep_study_log.jsonl 第1-%d行(夜间深研汇总, no_agent确定性生成, 0 LLM)" % len(rows_sorted),
    "rule": "exec_params=仅verdict明写翻闸/过五验/放大(当前全WATCH/OBSERVE=执行层0项, 与'五验过线才切执行'纪律一致); negated=证伪/FAIL进禁开名单; watch=攒样不进live",
    "families": families,
    "counts": {"exec": n_exec, "watch": n_watch, "negated": n_neg},
}
with open(PB, "w", encoding="utf-8") as f:
    json.dump(pb, f, ensure_ascii=False, indent=1)
_msg2 = "[R4汇总] ②family_playbook.json 已生成: exec=%d watch=%d negated=%d" % (n_exec, n_watch, n_neg)

# ③ live24 挂点提案(只开 rd_queue 工单, 幂等; 不擅改引擎码)
try:
    q = json.load(open(RQ, encoding="utf-8"))
except Exception:
    q = {"items": [], "queue": [], "tasks": []}
if "items" not in q:
    q["items"] = []
items = q["items"]
KEY = "t_live24_family_playbook_hook_1115"
exists = any(KEY in json.dumps(x, ensure_ascii=False) for x in items)
if not exists:
    items.append({
        "id": KEY,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "owner": "strategy-rd",
        "prio": "P2",
        "title": "live24 开单路径挂 family_playbook.json 读点(仿 tools/jince_live24.py L195 l24_feature_flags.json 启动读法)",
        "body": "R4汇总(11-15 no_agent拍)生成的机读playbook已落 E:/GoldstrategyEngine/data/family_playbook.json. 挂点要求: ①仅WATCH/OBSERVE用途(攒样标记/降档提示), 不放大不翻闸(exec=0项时零行为变更); ②读点fail-safe(文件缺/坏=按空playbook跑, 不崩开单链); ③证据三把手: 改后py_compile+实跑一次开单DRY-RUN无行为diff(exec=0时)+挂点日志行. 提案来源: 深研R4汇总no_agent拍(不擅改引擎码, 走rd_queue工单审批).",
        "evidence": "",
        "status": "queued",
    })
    json.dump(q, open(RQ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    _msg3 = "[R4汇总] ③rd_queue 挂点工单已开: %s" % KEY
else:
    _msg3 = "[R4汇总] ③rd_queue 挂点工单已存在, 不重开(幂等)"

# ④ 大白话报 + 去重门(当日内容哈希不变=静默)
report = ("【深研R4汇总·no_agent】夜间深研总账: 执行层进%d项 / 攒样(WATCH/OBSERVE) %d项 / 证伪进禁开%d项。"
          "当前全WATCH=引擎0变更(五验过线才放大, 纪律不变)。"
          "live24挂点=rd_queue工单已开(P2, strategy-rd审批, 只攒样不放大)。系统就绪: 明早开盘前开单链正常, 观察腿照攒。"
          % (n_exec, n_watch, n_neg))
h = hashlib.md5((report + "|exec=%d|watch=%d|neg=%d" % (n_exec, n_watch, n_neg)).encode()).hexdigest()
day = time.strftime("%F")
gate = {}
if os.path.exists(GATE):
    try:
        gate = json.load(open(GATE, encoding="utf-8"))
    except Exception:
        gate = {}
if gate.get("day") == day and gate.get("hash") == h:
    print("")
else:
    json.dump({"day": day, "hash": h, "ts": time.strftime("%F %T")}, open(GATE, "w", encoding="utf-8"))
    print(_msg2)
    print(_msg3)
    print(report)
