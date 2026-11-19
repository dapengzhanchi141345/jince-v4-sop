# -*- coding: utf-8 -*-
"""tf_refresh_incremental.py — L5③ K线增量刷新 (进化提速 L3, 2026-11-04)

治 `_cache_tfs.py` / `_jevo_tf_refresh_*` 每批全量回填(最长 10 万根 M15 × 多品种,
单终端 IPC 独占 25-40min)的根因: 本脚本只补缓存最后一根 K 线之后的增量:

  - npz 已存在且 now - last_t < 1.5×TF_SEC  -> SKIP_FRESH (0 次 IPC)
  - 过期了 -> copy_rates_range(last_t, now) 小窗拉增量, 去重合并(时间戳重叠保留新读),
    原子写盘(同 ts 重叠取后段, 与 _jevo_tf_refresh 口径一致)
  - npz 缺失 -> 全量首拉(自 2025-07-01 UTC, 与 _jevo START 同口径), 仅此一次
  - 拉取失败/空卷(被霸 IPC) -> 3 次重试后保留旧缓存, 标 FETCH_FAILED(引擎 stale-fallback, 不崩)

红线: 只写 data/tf_cache (原子替换), 不碰闸源/挂单/持仓/风控. 历史 K 线缓存 != 未来收益.
schema: 沿用各 npz 现有键 (t + h/l/c [+o] 按旧文件有无), 旧键 dtype 不变, 不新增键、不裁剪历史.
账号铁律: 只连钦定 demo 60137964, 不新建/不切账号.

用法: <mt5-python> tf_refresh_incremental.py [SYM_TF ...]
      不带参数 = 刷新 data/tf_cache 下全部现有 SYM_TF
      例: <mt5-python> tf_refresh_incremental.py BTCUSD_M30 XAUUSD
报告: data/tf_cache/_incremental_report.json + stdout 逐行 (审计可 grep)
"""
import os
import sys
import time
import json
import glob
import datetime
import threading

import numpy as np

try:
    import MetaTrader5 as mt5
except Exception as e:
    print("FATAL: MetaTrader5 import 失败(%s) — 换带 MT5 库的解释器 (D:/workbuddy/binaries/python/versions/3.13.12/python.exe)" % e)
    sys.exit(12)

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "tf_cache")
ACCOUNT = 60137964
SERVER = "TradeMaxGlobal-Demo"
FIRST_TS = int(datetime.datetime(2025, 7, 1, tzinfo=datetime.timezone.utc).timestamp())
FRESH_FACTOR = 1.5          # now - last_t < 1.5×TF_SEC 判新鲜, 0 IPC
TF_SEC = {"M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
TF_CONST_FALLBACK = {"M15": 15, "M30": 30, "H1": 16384, "H4": 16385, "D1": 16386}
MIN_OK = 1                  # 增量窗口哪怕 1 根新 K 线也算拉到; 0 根=空卷


def _atomic_replace(tmp, path):
    """Windows 并发持有者(回测引擎/影子采集 np.load 间歇读窗口)会拒 os.replace; 6×4s 抖动重试, 全失败保留旧文件(占卷容错同 refresh_tf_cache).
    [11-06 根治] 原 5×2s 固定窗口: 间歇持有者(读窗口几秒)易与重试节奏同步碰撞(实测 3 文件连 3 LOCKED 后 ABORT_WALL,
    但 handle64 同时刻查无持有者 = 间歇非常驻); 改 6×4s + 随机 0-2s 抖动 + replace 前清只读属性, 避开同步碰撞."""
    import random
    for _i in range(6):
        try:
            if os.name == "nt":
                try:
                    import stat
                    st = os.stat(path).st_file_attributes
                    if st & stat.FILE_ATTRIBUTE_READONLY:
                        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
                except Exception:
                    pass
            os.replace(tmp, path)
            return True
        except (PermissionError, OSError):
            time.sleep(4 + random.random() * 2)
    return False


def tf_const(name):
    v = getattr(mt5, "TIMEFRAME_" + name, None)
    return v if v is not None else TF_CONST_FALLBACK[name]


def targets(args):
    """解析 CLI: SYM_TF 精确 / SYM 全 TF / 无参=全量现有 npz."""
    existing = {}
    for p in glob.glob(os.path.join(OUT, "*.npz")):
        base = os.path.basename(p)[:-4]
        sym, _, tf = base.rpartition("_")
        existing[base] = os.path.join(OUT, base + ".npz")
    if not args:
        return list(existing.items())
    out = []
    for a in args:
        if "_" in a and a.split("_", 1)[1] in TF_SEC:
            out.append((a, os.path.join(OUT, a + ".npz")))
        else:
            for base in sorted(existing):
                if base.startswith(a + "_"):
                    out.append((base, existing[base]))
            if not any(b[0].startswith(a + "_") for b in out):
                out.append((a + "_M30", os.path.join(OUT, a + "_M30.npz")))
    return out


def _fetch(sym, tfname, from_ts, to_ts, keys):
    """小窗拉取, 3 次重试容错. 返回 dict(key->ndarray) 或 None."""
    try:
        mt5.symbol_select(sym, True)
    except Exception:
        pass
    tf = tf_const(tfname)
    struct_key = {"o": "open", "h": "high", "l": "low", "c": "close"}
    for _try in range(3):
        r = mt5.copy_rates_range(sym, tf, from_ts, to_ts)
        if r is not None and len(r) > 0:
            out = {"t": r["time"].astype(np.int64)}
            for k in keys:
                out[k] = r[struct_key[k]]
            return out
        time.sleep(2)
    return None


def merge(old, new, dtypes):
    """时间戳重叠保留后段(新读), 键/dtype 与旧文件一致, 不裁剪历史."""
    m = {}
    for k in old:
        a = old[k]
        b = new.get(k)
        if b is not None and len(b) > 0:
            m[k] = np.concatenate([a, b.astype(dtypes[k])])
        else:
            m[k] = a
    if "t" in m:
        o = np.argsort(m["t"], kind="stable")
        keep = np.concatenate(([True], np.diff(m["t"][o]) > 0))
        m = {k: v[o][keep] for k, v in m.items()}
    return m


_last_fetch_thread = None   # MT5 C 层单线程约束: 上一发 IPC 未回来前不并发下一发


def _fetch_bounded(sym, tfname, from_ts, to_ts, keys, timeout=45.0):
    """"拉增量"包一层线程+超时: 单终端 IPC 被别人的全量回填霸住时, 45s 不回来=当空卷(保留旧缓存), 不陪跑.
    MT5 绑定 C 层单线程约束: 上一发未 join 完成(>5s 还活着) -> 直接返回 None(争用容错), 绝不并发两发 C 调用."""
    global _last_fetch_thread
    if _last_fetch_thread is not None and _last_fetch_thread.is_alive():
        age = time.time() - _last_fetch_thread._start_ts
        if age > 5:
            return None
    res = {}

    def run():
        res["r"] = _fetch(sym, tfname, from_ts, to_ts, keys)

    th = threading.Thread(target=run, daemon=True)
    th._start_ts = time.time()
    _last_fetch_thread = th
    th.start()
    th.join(timeout)
    if "r" not in res:
        return None          # IPC 超时: 保留旧缓存(stale-fallback), 下批再补
    return res["r"]


def refresh_one(base, path, now_ts):
    sym, tfname = base.rsplit("_", 1)
    tfsec = TF_SEC[tfname]
    fresh_line = FRESH_FACTOR * tfsec
    status = "NO_CACHE"
    detail = ""

    old = None
    old_keys, dtypes = [], {}
    if os.path.exists(path):
        z = np.load(path)
        old_keys = [k for k in z.files if k in ("t", "o", "h", "l", "c")]
        dtypes = {k: z[k].dtype for k in old_keys}
        old = {k: z[k] for k in old_keys}
        last_t = int(old["t"][-1])
        if now_ts - last_t < fresh_line:
            try:
                os.remove(path + ".tmp")   # 上一批 LOCKED 留盘的过期增量载荷, 生产缓存已新鲜, 清掉
            except OSError:
                pass
            return {base: "SKIP_FRESH", "last_utc": datetime.datetime.fromtimestamp(last_t, datetime.timezone.utc).strftime("%m-%d %H:%M"), "bars": int(len(old["t"]))}
        fetch_keys = [k for k in ("o", "h", "l", "c") if k in old_keys]
        t0 = time.time()
        new = _fetch_bounded(sym, tfname, last_t, now_ts, fetch_keys)
        dt_ipc = time.time() - t0
        if new is None or len(new["t"]) == 0:
            status = "FETCH_FAILED"
            busy = _last_fetch_thread is not None and _last_fetch_thread.is_alive()
            detail = "保留旧缓存, 原因=%s" % ("IPC 45s 超时/被霸(下批补)" if busy else "空卷(下批补)")
            return {base: status, "detail": detail, "old_bars": int(len(old["t"]))}
        m = merge(old, new, dtypes)
        added = int(len(m["t"]) - len(old["t"]))
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:   # 文件句柄写, 避开 np.savez 对 .npz 后缀的自动追加
            np.savez(fh, **m)
        if _atomic_replace(tmp, path):
            status = "INCREMENTAL"
            detail = "+%d bars, IPC %.2fs" % (added, dt_ipc)
        else:
            status = "LOCKED"
            detail = "并发持有者拒 replace, 保留旧缓存(tmp 留盘下批重试)"
        return {base: status, "detail": detail, "bars": int(len(m["t"])), "last_utc": datetime.datetime.fromtimestamp(int(m["t"][-1]), datetime.timezone.utc).strftime("%m-%d %H:%M")}

    # 无缓存: 全量首拉(自 FIRST_TS), 仅此一次重活
    fetch_keys = ["o", "h", "l", "c"]
    t0 = time.time()
    new = _fetch_bounded(sym, tfname, FIRST_TS, now_ts, fetch_keys)
    dt_ipc = time.time() - t0
    if new is None or len(new["t"]) < 50:
        status = "FETCH_FAILED"
        detail = "首拉失败/空卷, 下批重试"
        return {base: status, "detail": detail}
    o = np.argsort(new["t"], kind="stable")
    new = {k: v[o] for k, v in new.items()}
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        np.savez(fh, **new)
    if _atomic_replace(tmp, path):
        status = "FULL_FIRST"
        detail = "%d bars 首拉, IPC %.1fs" % (len(new["t"]), dt_ipc)
    else:
        status = "LOCKED"
        detail = "并发持有者拒 replace, 首拉结果留 tmp 下批重试"
    return {base: status, "detail": detail, "bars": int(len(new["t"])), "last_utc": datetime.datetime.fromtimestamp(int(new["t"][-1]), datetime.timezone.utc).strftime("%m-%d %H:%M")}


def main():
    argv = sys.argv[1:]
    os.makedirs(OUT, exist_ok=True)
    if not mt5.initialize():
        ok = False
        try:
            ok = mt5.login(ACCOUNT, password="", server=SERVER)
        except Exception:
            ok = False
        if not ok:
            print("MT5 终端不可用, 全部保留旧缓存 (stale-fallback), 0 覆写")
            return
    now_ts = int(time.time())
    reps = []
    t_start = time.time()
    WALL_CAP = 120.0      # 全局墙钟护栏: 单终端 IPC 被霸(别人全量回填)时不陪跑, 剩余文件保留旧缓存下批补
    consecutive_lock = 0
    for base, path in targets(argv):
        if time.time() - t_start > WALL_CAP:
            reps.append({base: "ABORT_WALL", "detail": "全局 120s 护栏, 跳过(保留旧缓存, 下批补)"})
            print("%-16s %-13s %s" % (base, "ABORT_WALL", "全局 120s 护栏, 保留旧缓存"), flush=True)
            continue
        r = refresh_one(base, path, now_ts)
        reps.append(r)
        status = r[base]
        if status == "LOCKED":
            consecutive_lock += 1
            if consecutive_lock >= 3:
                # 系统性持有者(如回测循环整场 np.load 不关): 连 3 把后剩余文件直接快通道 ABORT, 不再陪 10s 重试
                print("%-16s %-13s %s" % (base, status, r.get("detail", "")), flush=True)
                for b2, p2 in targets(argv)[len(reps):]:
                    reps.append({b2: "ABORT_WALL", "detail": "连 3 LOCKED 快通道: 持有者系统性, 保留旧缓存(静默窗下批补)"})
                    print("%-16s %-13s %s" % (b2, "ABORT_WALL", "连 3 LOCKED, 保留旧缓存"), flush=True)
                break
        else:
            consecutive_lock = 0
        print("%-16s %-13s %s" % (base, status, r.get("detail", "")), flush=True)
    total_ipc = time.time() - t_start
    report = {"ts": now_ts, "wall_seconds": round(total_ipc, 1), "results": reps}
    with open(os.path.join(OUT, "_incremental_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    n_skip = sum(1 for r in reps if list(r.values())[0] == "SKIP_FRESH")
    n_inc = sum(1 for r in reps if list(r.values())[0] == "INCREMENTAL")
    n_fail = sum(1 for r in reps if list(r.values())[0] == "FETCH_FAILED")
    n_lock = sum(1 for r in reps if list(r.values())[0] == "LOCKED")
    print("增量刷新完: %d 文件 | SKIP_FRESH %d / INCREMENTAL %d / FETCH_FAILED %d / LOCKED %d | 墙钟 %.1fs (全量回填原 25-40min)" % (len(reps), n_skip, n_inc, n_fail, n_lock, total_ipc))
    mt5.shutdown()


if __name__ == "__main__":
    main()
