# -*- coding: utf-8 -*-
"""[L5 2026-11-04 进化提速·码格] 币系 H4/D1 一次性回填 tf_cache (治 "无数据" 的根子).

背景:
  intraday_swing.build_df_from_mt5 每 tick 对每个品种 live 拉 2600 H4 + 900 D1 根
  (15 币系 tick 内 ~5.8万根 IPC 抢占) -> 币系 tick 撞上 runner 全量回测霸 IPC 的
  25-40min 窗口时, 全部品种 fetch 失败 -> 简报 15 行 "[!] 无数据", 例外腿(POLUSD
  攒样带腿)连带 continue -> OOS 攒样 0 笔/天.
  tf_cache 已有 7 品种 H4/D1 (BNB/BTC/ETH/EUR/GBP/KSM/LTC/SOL/XAG/XAU/XRP 部分),
  缺 9 个币系 (ADA/BCH/DOGE/DOT/POL/TAO/UNI/XLM/XTZ) 的 H4+D1.

本脚本只做一次性首拉 (每文件 2600 H4 + 900 D1, ~2-5s/品种), 写进 tf_cache:
  - 已存在且新鲜的文件跳过 (幂等);
  - 之后由 tf_refresh_incremental.py 每批增量保鲜 (自动纳入, targets 按目录 glob).

红线: 只写 data/tf_cache/*.npz (新增文件), 不碰闸源/挂单/持仓/风控.
跑法: "/d/workbuddy/binaries/python/versions/3.13.12/python.exe" tf_backfill_crypto_h4d1.py
"""
import os
import sys
import time
import json
import glob
import datetime

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TF = os.path.join(HERE, "data", "tf_cache")

# tf_cache 目前缺失 H4/D1 的币系 (已核对 11-04 09:5x 目录清单)
MISSING = ["ADAUSD", "BCHUSD", "DOGEUSD", "DOTUSD", "POLUSD",
           "TAOUSD", "UNIUSD", "XLMUSD", "XTZUSD"]

N_H4 = 2600
N_D1 = 900
FRESH_H4 = int(1.5 * 4 * 3600)     # H4 缓存保鲜线 (与 tf_refresh_incremental 同口径)
FRESH_D1 = int(1.5 * 86400)


def _fresh(path, cap_s):
    if not os.path.exists(path):
        return False
    z = np.load(path)
    try:
        last = int(z["t"][-1])
    except Exception:
        return False
    finally:
        z.close()
    return time.time() - last < cap_s


def main():
    import MetaTrader5 as mt5
    assert mt5.initialize(), "mt5 initialize failed"
    now = int(time.time())
    report = {}
    for sym in MISSING:
        for tf, n, cap in (("H4", N_H4, FRESH_H4), ("D1", N_D1, FRESH_D1)):
            path = os.path.join(TF, "%s_%s.npz" % (sym, tf))
            if _fresh(path, cap):
                report[sym + "_" + tf] = "SKIP_FRESH"
                continue
            t0 = time.time()
            arr = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4 if tf == "H4" else mt5.TIMEFRAME_D1, 0, n)
            if arr is None or len(arr) < 50:
                report[sym + "_" + tf] = "FETCH_FAILED(保留不写, 下批重试)"
                print("%-14s %-6s 拉取失败: %s" % (sym, tf, mt5.last_error()), flush=True)
                continue
            np.savez_compressed(
                path,
                t=arr["time"].astype(np.int64),
                o=arr["open"].astype(np.float64),
                h=arr["high"].astype(np.float64),
                l=arr["low"].astype(np.float64),
                c=arr["close"].astype(np.float64),
            )
            last = datetime.datetime.fromtimestamp(int(arr["time"][-1]), datetime.timezone.utc).strftime("%m-%d %H:%M")
            report[sym + "_" + tf] = "OK %d根 last=%s %.1fs" % (len(arr), last, time.time() - t0)
            print("%-14s %-6s %s" % (sym, tf, report[sym + "_" + tf]), flush=True)
    with open(os.path.join(HERE, "cache_scratch_backfill_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    n_ok = sum(1 for v in report.values() if str(v).startswith("OK"))
    print("回填完: %d OK / %d SKIP / %d FAIL (共 %d 目标)" % (
        n_ok,
        sum(1 for v in report.values() if v == "SKIP_FRESH"),
        sum(1 for v in report.values() if str(v).startswith("FETCH_FAILED")),
        len(report)))
    mt5.shutdown()


if __name__ == "__main__":
    main()
