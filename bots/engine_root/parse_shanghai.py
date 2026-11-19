# -*- coding: utf-8 -*-
"""解析 81223578 MT5 报告 HTML (UTF-16) -> 逐笔持仓/成交/官方统计 三块实数.
用户令(2026-10-08): 深度分析这个策略数据, 吸取精华. 只读, 零交易动作."""
import re, json, datetime, os, statistics

SRC = r"E:/资料/新建文件夹/上海策略/ReportHistory-81223578.html"
DATA = r"E:/GoldstrategyEngine/data"

raw = open(SRC, "rb").read()
text = raw.decode("utf-16")
rows = re.findall(r'<tr[^>]*>(.*?)</tr>', text, re.S)

def clean(t):
    return re.sub(r'<[^>]+>', '', t).replace('\u00a0', ' ').replace('&nbsp;', ' ').strip()

def fnum(s):
    s = re.sub(r'[^\d.\-]', '', s)
    try: return float(s)
    except: return 0.0

# ── 1. 持仓(已平仓)表: 含隐藏列 colspan=8! 实数: td[0]开时间 td[1]持仓号 td[2]品种 td[3]buy/sell
#    td[4]隐藏span8(手数/开价/SL/TP/关时间/关价/注释/注释, 渲染为"") td[5]手数 td[6]开价 td[7]SL td[8]TP
#    td[9]关时间 td[10]关价 td[11]佣金 td[12]库存费 td[13]盈利. 判定: td[3]为方向且无 in/out 列.
pos = []
for m in rows:
    tds = [clean(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', m, re.S)]
    if len(tds) < 14: continue
    is_deal_row = tds[3] in ("in", "out") or (len(tds) > 3 and tds[4] in ("in", "out"))
    if tds[2] in ("XAUUSD", "BTCUSD") and tds[3] in ("buy", "sell") and not is_deal_row \
            and re.match(r'^\d{4}\.\d\d\.\d\d \d\d:\d\d:\d\d$', tds[0] or '') \
            and re.match(r'^\d{4}\.\d\d\.\d\d \d\d:\d\d:\d\d$', tds[9] or ''):
        pos.append(dict(open_t=tds[0], deal=tds[1], sym=tds[2], side=tds[3],
                        vol=fnum(tds[5]), open_px=fnum(tds[6]), sl=fnum(tds[7]), tp=fnum(tds[8]),
                        close_t=tds[9], close_px=fnum(tds[10]), comm=fnum(tds[11]),
                        swap=fnum(tds[12]), profit=fnum(tds[13])))
print("持仓(已平仓)条数:", len(pos))

# ── 2. 成交明细: in/out 行 (列=时间/deal/品种/side/inout/vol/price/ref_deal/隐藏/佣金/库存费/净利/结余/注释)
deals = []
for m in rows:
    tds = [clean(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', m, re.S)]
    if len(tds) < 13: continue
    if tds[2] in ("XAUUSD", "BTCUSD") and tds[3] in ("buy", "sell") and tds[4] in ("in", "out"):
        deals.append(dict(t=tds[0], deal=tds[1], sym=tds[2], side=tds[3], inout=tds[4],
                          vol=fnum(tds[5]), price=fnum(tds[6]), net=fnum(tds[11]),
                          equity=fnum(tds[12]) if len(tds) > 12 else 0))
print("成交明细条数:", len(deals))

# ── 3. 官方统计(从"结果"段抓)
def stat(label, span=300):
    i = text.find(label)
    if i < 0: return None
    seg = text[i:i+span]
    m = re.search(r'<b>(.*?)</b>', seg, re.S)
    return clean(m.group(1)) if m else None
stats = {
    "总净盈利": stat("总净盈利"), "毛利": stat("毛利"), "毛损": stat("毛损"),
    "盈利因子": stat("盈利因子"), "预期收益": stat("预期收益"), "采收率": stat("采收率"),
    "夏普比率": stat("夏普比率"), "最大结余亏损": stat("最大结余亏损"),
    "交易总计": stat("交易总计"), "最大获利交易": stat("最大 获利交易"),
    "最大亏损交易": stat("最大 亏损交易"), "平均获利交易": stat("平均 获利交易"),
    "平均亏损交易": stat("平均 亏损交易"), "最大连胜": stat("最大值 连胜"),
}
print("官方统计:", json.dumps(stats, ensure_ascii=False))

# ── 4. 逐笔深度实数(持仓已平仓为主表, 同分母)
def dur_h(a, b):
    try:
        da = datetime.datetime.strptime(a, "%Y.%m.%d %H:%M:%S")
        db = datetime.datetime.strptime(b, "%Y.%m.%d %H:%M:%S")
        return (db - da).total_seconds() / 3600
    except: return None

recs = []
for p in pos:
    dh = dur_h(p["open_t"], p["close_t"])
    px = p["close_px"] if p["side"] == "sell" else -p["close_px"]
    recs.append({**p, "dur_h": dh, "px_delta": px})
win = [r for r in recs if r["profit"] > 0]
lose = [r for r in recs if r["profit"] < 0]
flat = [r for r in recs if r["profit"] == 0]
tot = sum(r["profit"] for r in recs)
print("\n=== 逐笔实数(同分母, 已平仓 %d 笔) ===" % len(recs))
print("总盈利: %.2f | 赢 %d / 输 %d / 平 %d | 胜率 %.1f%%" % (tot, len(win), len(lose), len(flat), 100 * len(win) / max(1, len(win) + len(lose))))
if win: print("赢单均值: %.2f | 输单均值: %.2f | 平均RR(赢/|输|): %.2f" % (
    statistics.mean(r["profit"] for r in win), statistics.mean(r["profit"] for r in lose) if lose else 0,
    statistics.mean(r["profit"] for r in win) / abs(statistics.mean(r["profit"] for r in lose)) if lose and statistics.mean(r["profit"] for r in lose) else float('inf')))
dh_sorted = sorted((r["dur_h"] for r in recs if r["dur_h"]), reverse=True)
if dh_sorted:
    n = len(dh_sorted); med = n // 2
    print("持仓时长(h): 中位 %.1f | P75 %.1f | 最长 %.1f | 最短 %.1f" % (dh_sorted[med], dh_sorted[int(n*0.75)], dh_sorted[0], dh_sorted[-1]))
by_sym = {}
for r in recs:
    d = by_sym.setdefault(r["sym"], dict(n=0, tot=0.0, w=0, l=0))
    d["n"] += 1; d["tot"] += r["profit"]
    if r["profit"] > 0: d["w"] += 1
    elif r["profit"] < 0: d["l"] += 1
print("分品种:", {k: {"n": v["n"], "tot": round(v["tot"], 2), "W": v["w"], "L": v["l"]} for k, v in by_sym.items()})
# 有无止损止盈(纪律实数)
with_sl = sum(1 for r in recs if r["sl"] > 0)
with_tp = sum(1 for r in recs if r["tp"] > 0)
print("挂SL %d/%d | 挂TP %d/%d (纪律实数)" % (with_sl, len(recs), with_tp, len(recs)))
# 时间分布(日内 vs 跨夜)
intra = sum(1 for r in recs if (r["dur_h"] or 0) < 12)
print("日内(<12h) %d | 跨夜(>=12h) %d" % (intra, len(recs) - intra))

json.dump({"pos": pos, "deals_n": len(deals), "stats": stats,
           "summary": {"n": len(recs), "tot": round(tot, 2), "win_n": len(win), "lose_n": len(lose),
                       "flat_n": len(flat), "by_sym": {k: {kk: vv for kk, vv in v.items()} for k, v in by_sym.items()},
                       "with_sl": with_sl, "with_tp": with_tp, "intra": intra}},
          open(os.path.join(DATA, "shanghai_parsed.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\n已存 data/shanghai_parsed.json")
