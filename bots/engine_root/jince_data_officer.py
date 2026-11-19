# -*- coding: utf-8 -*-
"""金策·数据官(jince_data_officer.py) —— K线数据新鲜度/有效性 专职哨兵(确定性0-LLM, 30min)
================================================================
职责切分(交叉引用不复制):
  * 数据官 = 唯一刷 tf_cache npz 的一方 (读MT5历史K线, 只读历史, 绝不下单/不动live参数)
  * 验尸官yushi = 唯一写 live_state.json (数据官只读校验其30min效期, 不写)
  * strategy-rd 消费K线前必须读 data_validity.json 效期戳, >48h 的裁定自动FAIL
  * 07:30 日班(refresh_csv_fresh)管 research CSV, 数据官管 tf_cache npz, 两线不交叉
哨兵模式(全绿静默):
  * 全绿: stdout 只打 "[数据官OK] scan=N stale=R fail=F ts=...", 投递层静默
  * 红件: 刷新成功但此前陈旧 / 坏件修复 / MT5连接失败 = 一行红报(bot-chat) + task_ledger
  * MT5 全挂 = exit 1 (故障即补跑哨 cd863fdae55c 每30min接手重跑)
新鲜度闸(按mtime, npz只在刷新时改写, mtime=上次刷新时刻):
  M15/M30 ≤8h | H1 ≤26h | H4 ≤26h | D1 ≤26h | 周末非24h品种 x3 容忍
  超闸 = 拉最新全量重存(原子写 .npz.tmp -> os.replace, 失败不动现役)
"""
import os, sys, time, json, glob, shutil, datetime

ROOT = "E:/GoldstrategyEngine"
CACHE = os.path.join(ROOT, "data", "tf_cache")
VALID = os.path.join(ROOT, "data", "data_officer_last.json")
LEDGER = os.path.join(ROOT, "data", "task_ledger.json")
CRYPTO = {"BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD", "BNBUSD", "ADAUSD",
          "DOGEUSD", "DOTUSD", "BCHUSD", "KSMUSD", "GLMUSD", "POLUSD", "AVXUSD",
          "XLMUSD", "XTZUSD", "TAOUSD", "LNKUSD", "UNIUSD", "CHCUSD"}
TF_MAX_H = {"M15": 8, "M30": 2, "H1": 26, "H4": 26, "D1": 26}
# 11-19 P0收紧: M30 8h->2h (旧8h闸下"mtime全绿但数据尾停6h"实锤: 币系7件尾停05:30, 21:35自动开仓会用陈旧M30判位移; 2h闸=数据末端与尾停红线2h对齐; M15/H1/H4/D1不动)
WANT = {"D1": 3000, "H4": 15000, "H1": 30000, "M30": 30000, "M15": 50000}
# 11-17根修: M15 100000/H4 30000 超终端可服务深度(实测M15上限=50000, 超限报-2 Invalid params全件失败), 收敛到终端实顶
THrottle = {"per_pass_max": 12}  # 单次最多刷12件, 余下下拍(防MT5拉取风暴)

import MetaTrader5 as mt5

# 品种名解析: 终端真实名带点(AVGO.NAS/BLK.NYS), 缓存旧名带下划线(AVGO_NAS); 先原样后别名再通配
def resolve_sym(sym):
    try:
        if mt5.symbol_info(sym):
            return sym
    except Exception:
        pass
    alias = sym.replace("_", ".")
    try:
        if mt5.symbol_info(alias):
            return alias
    except Exception:
        pass
    stem = sym.split("_")[0]
    try:
        lst = mt5.symbols_get(stem)
        if lst:
            return lst[0].name
    except Exception:
        pass
    return None


def weekend_lenient(sym, base_h):
    wd = datetime.datetime.now().weekday()
    if wd >= 5 and sym not in CRYPTO:
        return base_h * 3
    return base_h


def main():
    os.environ.setdefault("MT5_TERMINAL", r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")
    if not mt5.initialize():
        mt5.initialize(r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")
    files = [f for f in glob.glob(os.path.join(CACHE, "*.npz")) if ".tmp" not in os.path.basename(f)]
    # P2修复(11-19): 孤儿件清扫(.npz.<pid>.npz 崩溃残留 / .npz.rdnew.npz 研究层改名残留, 超1h才清)
    import re as _re
    for f in glob.glob(os.path.join(CACHE, "*.npz.*.npz")):
        if time.time() - os.path.getmtime(f) > 3600:
            try:
                os.remove(f)
            except OSError:
                pass
    now = time.time()
    plan = []
    for f in files:
        base = os.path.basename(f)
        tf = base.rsplit("_", 1)[-1].replace(".npz", "")
        sym = base[: -(len(tf) + 5)]
        if tf not in TF_MAX_H:
            continue
        try:
            age_h = (now - os.path.getmtime(f)) / 3600
        except OSError:
            age_h = 999
        lim = weekend_lenient(sym, TF_MAX_H[tf])
        if age_h > lim or os.path.getsize(f) < 1000:
            plan.append((sym, tf, round(age_h, 1)))
    plan.sort(key=lambda x: (x[0] not in ("BTCUSD", "ETHUSD", "XAUUSD", "EURUSD"), -x[2]))
    plan = plan[: THrottle["per_pass_max"]]
    stale_total = len(files) and len([p for p in plan])  # 本拍计划件
    if not mt5.terminal_info():
        print("[数据官红] MT5终端不可达, 全量闸停摆, 等补跑哨: 计划%s" % ",".join("%s_%s" % (p[0], p[1]) for p in plan[:6]))
        json.dump({"ts": int(now), "mt5": "DOWN", "plan": plan, "refreshed": 0, "fail": len(plan)},
                  open(VALID, "w", encoding="utf-8"))
        return 1
    refreshed, failed = 0, []
    for sym, tf, age in plan:
        t_const = {"D1": mt5.TIMEFRAME_D1, "H4": mt5.TIMEFRAME_H4, "H1": mt5.TIMEFRAME_H1,
                   "M30": mt5.TIMEFRAME_M30, "M15": mt5.TIMEFRAME_M15}[tf]
        rname = resolve_sym(sym)
        got = 0
        if rname is None:
            failed.append("%s_%s(名不可解析)" % (sym, tf))
            continue
        for _ in range(3):
            try:
                mt5.symbol_select(rname, True)
            except Exception:
                pass
            r = mt5.copy_rates_from_pos(rname, t_const, 0, WANT[tf])
            if r is not None and len(r) >= 50:
                import numpy as np
                dst = os.path.join(CACHE, "%s_%s.npz" % (sym, tf))
                tmp = dst[:-4] + ".%d.npz" % os.getpid()
                np.savez_compressed(tmp,
                                     t=r["time"].astype("int64"),
                                     o=r["open"].astype("float32"),
                                     h=r["high"].astype("float32"),
                                     l=r["low"].astype("float32"),
                                     c=r["close"].astype("float32"))
                os.replace(tmp, dst)
                got = len(r)
                break
            time.sleep(2)
        if got:
            refreshed += 1
        else:
            failed.append("%s_%s" % (sym, tf))
    # 效期戳(供strategy-rd五验引用): P0修复(11-19) mtime=写文件时刻≠数据末端时刻,
    # 终端停摆时mtime每拍被刷但K线尾停=假新鲜; 现双记 mtime + 数据末端ts, 消费方(五验)以kline_end为准
    last = {}
    import numpy as np
    kline_end, kline_stale = {}, []
    for f in glob.glob(os.path.join(CACHE, "*_M30.npz")):
        if ".tmp" not in f and ".npz." not in os.path.basename(f):
            sym = os.path.basename(f)[:-8]
            last[sym] = int(os.path.getmtime(f))
            try:
                zz = np.load(f); end_ts = int(zz["t"][-1]); zz.close()
                kline_end[sym] = end_ts
                lag_h = (now - end_ts) / 3600
                if sym in CRYPTO:
                    if lag_h > 2:
                        kline_stale.append("%s(尾停%.1fh)" % (sym, lag_h))
                elif lag_h > 34:
                    kline_stale.append("%s(尾停%.1fh,周末)" % (sym, lag_h))
            except Exception:
                kline_stale.append("%s(读尾失败)" % sym)
    out = {"ts": int(now), "mt5": "UP", "scan": len(files), "stale_plan": stale_total,
           "refreshed": refreshed, "fail": failed, "m30_mtime": last,
           "m30_kline_end": kline_end, "m30_kline_stale": kline_stale,
           "note": "数据官30min哨: npz新鲜度闸+原子刷新; 五验消费m30_kline_end(数据末端)而非mtime, 尾停>2h(币)/34h(非币)=FAIL"}
    json.dump(out, open(VALID, "w", encoding="utf-8"))
    if kline_stale:
        print("[数据官红] K线尾停: %s" % ", ".join(kline_stale))
    if refreshed or failed:
        msg = "[数据官红] 陈旧%d件 已刷%d 失败%d(%s)" % (stale_total, refreshed, len(failed), ",".join(failed[:4]))
        print(msg)
        try:
            T = json.load(open(LEDGER, encoding="utf-8"))
            T.setdefault("tasks", []).append({"id": "officer_%s" % time.strftime("%m%d%H%M"), "ts": int(now), "by": "数据官(哨)",
                               "desc": msg, "evidence": [VALID], "status": "DONE" if not failed else "PENDING_RERUN"})
            json.dump(T, open(LEDGER, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception as ex:
            print("[数据官红] 台账写失败: %s" % str(ex)[:80])  # 11-19: 静默吞掉=红件失明, 改发声
        if failed:
            return 1
    print("[数据官OK] scan=%d stale=%d refreshed=%d fail=%d" % (len(files), stale_total, refreshed, len(failed)))
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
