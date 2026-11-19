import csv, json, collections, re, os

DAYS = ("2026-11-10", "2026-11-11")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "data", "live24_trades.csv")
TRACK = os.path.join(ROOT, "data", "mfe_mae_track.jsonl")

rows = [r for r in csv.reader(open(CSV, encoding="utf-8")) if r and r[0].startswith(DAYS)]
print("台账事件总数(两日)=", len(rows))

# 真实1R：取每个 ticket 的 OPEN 行 entry/sl
open_map = {}
for r in rows:
    if r[1] == "OPEN" and len(r) > 6 and r[4] and r[5] and r[6]:
        try:
            t = r[4]; e = float(r[5]); s = float(r[6])
            if t not in open_map:
                open_map[t] = (r[2], int(r[3]), e, s, abs(e - s))
        except: pass
print("有真实1R的持仓数=", len(open_map))

ev = collections.defaultdict(list)
for r in rows:
    if len(r) > 4 and r[4] in open_map:
        ev[r[4]].append(r)

# 台账 mfe_R 口径检查：找写入函数
big = []
for t, (sym, dirn, e, s, R1) in open_map.items():
    sl_trails = [r for r in ev[t] if r[1] == "SL_TRAIL"]
    ends = [r for r in ev[t] if r[1] in ("CLOSE", "B0_EXIT", "LOSECUT斩亏", "MAXHOLD硬平", "MAGIC_DUP_EXIT")]
    succ = [float(r[6]) for r in sl_trails if len(r) > 6 and r[6] and "rc=10009" in (r[11] if len(r) > 11 else "")]
    rej = [r for r in sl_trails if "rc=10016" in (r[11] if len(r) > 11 else "")]
    peak_note = 0.0
    for r in sl_trails:
        m = re.search(r"浮盈([0-9.]+)R", r[11] if len(r) > 11 else "")
        if m: peak_note = max(peak_note, float(m.group(1)))
    locked_R = max(((x - e) / R1 if dirn == 1 else (e - x) / R1) for x in succ) if succ else None
    endtype = ends[0][1] if ends else "OPEN_ONLY"
    endnote = ends[0][11][:70] if ends and len(ends[0]) > 11 else ""
    big.append((peak_note, t, sym, dirn, R1, len(sl_trails), len(rej), locked_R, endtype, endnote))

big.sort(key=lambda z: (-(z[0] or 0),))
print("\n=== 两日持仓 浮盈峰值降序 Top25 ===")
print("peakR ticket sym dir TRUE1R nTrail nRej(10016) lockedR(成功) 终态")
for peak_note, t, sym, dirn, R1, nt, nr, locked_R, endtype, endnote in big[:25]:
    print("  %.2f %s %s d%d 1R=%.4f nT=%d nR=%d locked=%s %s" % (
        peak_note, t, sym, dirn, R1, nt, nr, ("%.2f" % locked_R if locked_R is not None else "无"), endtype))

print("\n=== 被10016拒单且从未成功锁利(完全裸奔)的持仓 ===")
stuck = [z for z in big if z[6] > 0 and z[7] is None]
print("共%d个:" % len(stuck))
for z in stuck:
    print("  ", z[1], z[2], "dir", z[3], "peak浮盈%.2fR" % z[0], "拒%d次" % z[6], z[8], "|", z[9][:40])

print("\n=== 全额/大浮盈但只锁到弱地板(0.5R)的持仓 ===")
weak = [z for z in big if (z[0] or 0) >= 0.9 and z[7] is not None and z[7] < 0.6]
print("共%d个:" % len(weak))
for z in weak[:15]:
    print("  ", z[1], z[2], "peak%.2fR" % z[0], "locked%.2fR" % z[7], z[8])

# MAXHOLD 大额
print("\n=== MAXHOLD硬平 事件(两日) ===")
for r in rows:
    if r[1] == "MAXHOLD硬平":
        print("  ", r[0], r[2], "dir", r[3], "entry", r[5], "sl", r[6], "exit", r[8], "note:", (r[11][:70] if len(r) > 11 else ""))
