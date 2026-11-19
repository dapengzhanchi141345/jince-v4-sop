# -*- coding: utf-8 -*-
"""落盘 s5s6_obs_tag_oos_20261115 学习进化 429 补跑三账 + rd_queue 销账 + rd_watchlist 指针.
红线: 只写研究/台账, 不碰挂单/撤单/交易闸/实盘. rd_queue 先备份再整文件 json.dump."""
import json, shutil, os, time

DATA = "E:/GoldstrategyEngine/data"
NOW_ISO = "2026-11-16T10:20:00"

# --- now epoch: 对齐系统真值 live_state.ts_unix (与既有台账同纪元), 缺则回退 time.time() ---
try:
    NOW_EPOCH = int(json.load(open("E:/AgentCommons/shared/live_state.json", encoding="utf-8"))["ts_unix"])
except Exception:
    try:
        NOW_EPOCH = int(time.time())
    except Exception:
        NOW_EPOCH = 0

# ---------- 1) rd_ledger.jsonl 追加 1 条 WATCH ----------
led = os.path.join(DATA, "rd_ledger.jsonl")
entry = {
    "ts": NOW_EPOCH,
    "leg": "s5s6_fwd_oos_relay_20261115",
    "verdict": "WATCH",
    "reason_人话": ("11-15 学习进化21:30被429限流未成, 11-16凌晨429补跑代跑: 领题 s5s6_obs_tag_oos_20261115, "
                    "5 WATCH品种(XAU/EUR/BTC/ETH/BNB) 用前向K线(M30至11-16 10:00/M15至11-16 04:00)同分母五验. "
                    "结果全维持WATCH 0放大: 无一过⑥净期望线1.0(逐笔均R 0.03~0.11). 最强=XAU S5(家时段窗闸) 5/5 T1-T5, "
                    "均R0.110 net79.3(>base76.3)=前向OOS攒样头号候选; 但⑥未过=不翻闸. 翻闸权属chief R11双裁, 我出结论不动闸. "
                    "0翻闸=纪律正常, 历史回测≠未来收益."),
    "data_fields": {
        "data_file": "data/rd_verify_batch_s5s6_obs_tag_oos_20261115.json",
        "kline": "M30/D1=tf_cache .tmp前向(11-16 10:00) + M15 tv=net20261115_m15(11-16 04:00)",
        "per_sym": {
            "XAUUSD": {"s5": {"pass": "5/5", "avg": 0.110, "net": 79.3}, "s6": {"pass": "4/5", "avg": 0.099, "net": 64.6}},
            "EURUSD": {"s5": {"pass": "3/5", "avg": 0.040, "net": 32.6}, "s6": {"pass": "3/5", "avg": 0.029, "net": 20.8}},
            "BTCUSD": {"s5": {"pass": "4/5", "avg": 0.078, "net": 80.4}, "s6": {"pass": "4/5", "avg": 0.092, "net": 84.2}},
            "ETHUSD": {"s5": {"pass": "4/5", "avg": 0.068, "net": 69.4}, "s6": {"pass": "3/5", "avg": 0.068, "net": 59.6}},
            "BNBUSD": {"s5": {"pass": "4/5", "avg": 0.044, "net": 43.1}, "s6": {"pass": "4/5", "avg": 0.049, "net": 42.4}},
        },
        "strongest": "XAUUSD S5 (家时段窗闸) 5/5 前向OOS攒样头号",
    },
    "five_test_pass": "0/5 APPROVE; 5/5 WATCH (均未过⑥净期望线1.0)",
    "live_flag": False,
}
with open(led, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("rd_ledger.jsonl appended")

# ---------- 2) rd_ledger_24h.json 追加 1 条(4键齐全) ----------
h24 = os.path.join(DATA, "rd_ledger_24h.json")
d24 = json.load(open(h24, encoding="utf-8"))
d24["entries"].append({
    "ts": NOW_ISO, "bot": "strategy-rd",
    "theme": "s5s6_fwd_oos_relay", "theme_cn": "灵魂S5/S6家窗口·定位 前向OOS接力(429补跑)",
    "brief": "领题s5s6_obs_tag_oos_20261115, 5WATCH品种前向K线同分母五验全维持WATCH 0放大(无一过⑥线1.0); 最强XAU S5(5/5,均R0.110)=前向OOS攒样头号; 翻闸权属chief R11双裁不动.",
    "learn_files": ["data/rd_verify_batch_s5s6_obs_tag_oos_20261115.json", "research/net20261115_m15/"],
    "candidate": "s5s6_fwd_oos_20261115", "verdict": "WATCH(5/5未过⑥)",
    "p4_gap": "⑥净期望线1.0未过=不放大; XAU S5攒满30笔前向OOS+⑥达标才进R11双裁",
    "next_theme": "XAU S5家窗闸前向OOS攒样(轮转)", "heartbeat": "alive",
})
d24["ts"] = NOW_ISO
with open(h24, "w", encoding="utf-8") as f:
    json.dump(d24, f, ensure_ascii=False, indent=1)
print("rd_ledger_24h.json appended")

# ---------- 3) rd_watchlist.json 刷新 S5/S6 前向OOS指针 ----------
wl = os.path.join(DATA, "rd_watchlist.json")
w = json.load(open(wl, encoding="utf-8"))
items = w.setdefault("items", [])
# 幂等: 已有同 data_file 则更新, 否则追加
matched = False
for it in items:
    if it.get("data_file") == "data/rd_verify_batch_s5s6_obs_tag_oos_20261115.json":
        it.update({"status": "WATCH_FORWARD", "exp_R": 0.110,
                   "status_note": "11-15学习进化429补跑: 前向OOS五验XAU S5 5/5均R0.110, ⑥未过维持WATCH攒样; 逐品种5 WATCH",
                   "added": NOW_ISO})
        matched = True
if not matched:
    items.append({"hypo": "S5家时段窗闸·S6定位图闸 前向OOS接力(5WATCH: XAU/EUR/BTC/ETH/BNB)",
                  "data_file": "data/rd_verify_batch_s5s6_obs_tag_oos_20261115.json",
                  "added": NOW_ISO, "exp_R": 0.110, "wf3": None, "per_sym_pos": "XAU S5最强(5/5,0.110)/BTC S6(4/5,0.092)",
                  "status": "WATCH_FORWARD", "flip_gate": "chief R11双裁: 攒满30笔前向OOS+⑥净期望>=1.0才翻True",
                  "status_note": "11-15学习进化429补跑, 前向K线同分母五验全维持WATCH 0放大"})
with open(wl, "w", encoding="utf-8") as f:
    json.dump(w, f, ensure_ascii=False, indent=1)
print("rd_watchlist.json refreshed")

# ---------- 4) rd_queue.json 销账 s5s6 项 (先备份) ----------
q = os.path.join(DATA, "rd_queue.json")
shutil.copy(q, q + ".bak_s5s6_fwd_1116")
qd = json.load(open(q, encoding="utf-8"))
target = None
for it in qd.get("items", []):
    if it.get("id") == "s5s6_obs_tag_oos_20261115":
        target = it
        break
if target is not None:
    target["status"] = "watch_forward"
    target["note"] = ("11-15学习进化429补跑(strategy-rd代): 前向K线同分母五验5品种全维持WATCH, 0翻闸; "
                      "最强XAU S5(5/5,均R0.110)前向OOS攒样; 销账=watch_forward, 轮转指针=下批XAU S5攒样")
    with open(q, "w", encoding="utf-8") as f:
        json.dump(qd, f, ensure_ascii=False, indent=1)
    print("rd_queue.json: s5s6_obs_tag_oos_20261115 -> watch_forward (backup .bak_s5s6_fwd_1116)")
else:
    print("rd_queue.json: s5s6 item NOT FOUND (skip)")

print("ALL_LEDGER_WRITTEN now_epoch=", NOW_EPOCH)
