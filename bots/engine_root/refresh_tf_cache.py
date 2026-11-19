# -*- coding: utf-8 -*-
"""refresh_tf_cache.py — L5 ① K线缓存刷新 (治双引擎霸 IPC 空卷根因)
双引擎(Live Runner PID584 + 回测引擎)共享 MT5 终端 8736 -> 并发 copy_rates 谁抢谁空卷.
本刷新器: 竞态容错(contention-tolerant) 单枪拉 6 腿池 PO6 的 H1/H4/D1 落 npz;
   - 终端静默窗口拉得到 -> 落缓存(供 00:10 回测引擎 cache-first 读, 零并发);
   - 被霸空卷 -> 该符号 3 次重试后标 skip(不崩), 保留旧 npz, 引擎 stale-fallback 仍出实数.
红线: 只写 data/tf_cache, 不碰实盘挂单/持仓/风控闸. 历史 K 线缓存 != 未来收益.
用法: ATE-python refresh_tf_cache.py [SYM1,SYM2,...]   (默认 PO6 6腿池)
"""
import os, sys, time, datetime
import numpy as np
try:
    import MetaTrader5 as mt5
except Exception as e:
    print("FATAL: MetaTrader5 import 失败(%s)" % e); sys.exit(12)

TF_MAP = {"D1": getattr(mt5, "TIMEFRAME_D1"),
          "H4": getattr(mt5, "TIMEFRAME_H4"),
          "H1": getattr(mt5, "TIMEFRAME_H1")}
WANT = {"D1": 3000, "H4": 30000, "H1": 60000}
MIN_OK = {"D1": 500, "H4": 500, "H1": 500}   # 至少 500 根才算"拉到了", 否则当空卷
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tf_cache")
PO6 = ["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "EURUSD", "GBPUSD"]


def _init():
    if mt5.initialize():
        return True
    # [账号铁律] 只操作钦定 demo 60137964, 不新建/切换; 登录失败=终端未起, 返回 False(不崩)
    try:
        ok = mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
    except Exception:
        ok = False
    return ok


def _probe(sym, tfname):
    """单次拉取尝试; 拉到 >=MIN_OK 返回 ndarray, 否则 None(空卷/被霸)."""
    try:
        mt5.symbol_select(sym, True)
    except Exception:
        pass
    r = mt5.copy_rates_from_pos(sym, TF_MAP[tfname], 0, WANT[tfname])
    if r is not None and len(r) >= MIN_OK[tfname]:
        return r
    return None


def refresh(syms):
    os.makedirs(OUT, exist_ok=True)
    if not _init():
        print("MT5 终端不可用(initialize+login 60137964 均失败), 无法拉 K 线; 保留旧缓存, 引擎 stale-fallback.")
        return {"ok": False, "reason": "mt5_unavailable"}
    now_iso = datetime.datetime.now().isoformat()
    per_sym = {}
    for sym in syms:
        sym_ok = 0
        for tfname in ("D1", "H4", "H1"):
            got = None
            for _try in range(3):                 # 竞态容错: 3 次, 2s 间隔
                got = _probe(sym, tfname)
                if got is not None:
                    break
                time.sleep(2)
            if got is not None:
                p = os.path.join(OUT, "%s_%s.npz" % (sym, tfname))
                np.savez_compressed(p, t=got["time"].astype(np.int64),
                                    o=got["open"].astype(np.float32),
                                    h=got["high"].astype(np.float32),
                                    l=got["low"].astype(np.float32),
                                    c=got["close"].astype(np.float32))
                sym_ok += 1
            else:
                print("  [%s %s] 空卷/被霸(3次重试仍0), skip 保留旧缓存" % (sym, tfname))
        per_sym[sym] = sym_ok
    report = {"ok": True, "ts": now_iso,
              "per_symbol_ok_tfs": per_sym,
              "full_ok": all(v == 3 for v in per_sym.values())}
    print("缓存刷新: " + ", ".join("%s=%d/3" % (s, v) for s, v in per_sym.items()))
    print("全 6 腿 H1/H4/D1 齐 = %s" % report["full_ok"])
    return report


if __name__ == "__main__":
    args = sys.argv[1].split(",") if len(sys.argv) > 1 and sys.argv[1] else PO6
    args = [a for a in args if a]
    rep = refresh(args)
    json_out = os.path.join(OUT, "refresh_report.json")
    try:
        import json as _json
        with open(json_out, "w", encoding="utf-8") as f:
            _json.dump(rep, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    # 退出码: 0=全齐, 1=部分, 12=MT5不可用 (供 00:10 wrapper 判"缓存刷没刷上")
    if not rep.get("ok"):
        sys.exit(12)
    sys.exit(0 if rep.get("full_ok") else 1)
