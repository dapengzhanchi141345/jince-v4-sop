# -*- coding: utf-8 -*-
"""拉 TAOUSD/XTZUSD 的 M30/D1/H1/H4 全深度 K线 -> 存 fam4.load 期望的 npz (t,o,h,l,c).
tf_cache 现无这两品种, 补上才能跑 _rd_tao_xtz_momgate.py 同分母复验.
[并发铁律] 引擎锁/IPC: 只能单枪拉, 且须确认无活体回测引擎霸 MT5 IPC (Phase B 出件后退才拉).
纯数据落盘, 不碰交易配置."""
import sys, os, time
import numpy as np
import MetaTrader5 as mt5

ROOT = r"E:\GoldstrategyEngine"
CF = os.path.join(ROOT, "data", "tf_cache")
SYMS = ["TAOUSD", "XTZUSD"]
TFS = [("M30", mt5.TIMEFRAME_M30), ("H1", mt5.TIMEFRAME_H1),
       ("H4", mt5.TIMEFRAME_H4), ("D1", mt5.TIMEFRAME_D1)]
PAGE = 10000
GUARD_S = 300  # 单 tf 拉取限时, 到点 fail-open(防 IPC 卡死白磨)


def pull(sym, tf):
    """循环分页拉满该品种该周期历史, 返回 (time, o, h, l, c) int64/float 数组或 None."""
    frames = []
    pos = 0
    t0 = time.time()
    while True:
        if time.time() - t0 > GUARD_S:
            return None
        chunk = mt5.copy_rates_from_pos(sym, tf, pos, PAGE)
        if chunk is None or len(chunk) == 0:
            break
        frames.append(chunk)
        if len(chunk) < PAGE:
            break
        pos += PAGE
    if not frames:
        return None
    import pandas as pd
    df = pd.concat([pd.DataFrame(f) for f in frames], ignore_index=True)
    # 去重 + 升序
    df = df.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)
    return {
        "t": df["time"].to_numpy(dtype=np.int64),
        "o": df["open"].to_numpy(dtype=float),
        "h": df["high"].to_numpy(dtype=float),
        "l": df["low"].to_numpy(dtype=float),
        "c": df["close"].to_numpy(dtype=float),
    }


def main():
    if not mt5.initialize():
        print("MT5 init fail, abort (IPC 可能被活体引擎霸着, 别双发)")
        sys.exit(2)
    for sym in SYMS:
        try:
            mt5.symbol_select(sym, True)
        except Exception:
            pass
        for label, tf in TFS:
            r = pull(sym, tf)
            p = os.path.join(CF, f"{sym}_{label}.npz")
            if r is None:
                print(f"{sym} {label}: 拉取失败/限时, 跳过")
                continue
            np.savez(p, **r)
            print(f"{sym} {label}: n={len(r['t'])} saved -> {os.path.basename(p)}")
    mt5.shutdown()
    print("npz 拉取完成, 可跑 _rd_tao_xtz_momgate.py")


if __name__ == "__main__":
    main()
