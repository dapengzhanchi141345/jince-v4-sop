# -*- coding: utf-8 -*-
"""mt5_readonly_probe.py — [rd_mt5_init_hardening_20261021] python3.11 直连只读 MT5 探针
用途: daily_advisory 步 ATE 子代 MT5 握手冻死族(IPC 15s 封顶偶发)时, 由 daily_advisory 的
      _mt5_readonly_probe() 用 python3.11 解释器(独立 IPC 通道, 不经 ATE 冻结子代)直连账户读实数,
      证明账户活着 + 拿到 equity/持仓数/挂单数/XAU 参考 tick, 避免静默沿旧 tick 数据。
口径: 0 下单 0 撤单 0 挂单, 纯只读, 不碰交易链路任何写操作; 不碰币系闸/事件闸/平仓清单。
输出: stdout 最后一行是单行 JSON {ok, equity, balance, n_positions, n_orders, ref_symbol, ref_tick, ts, error}
      父进程(daily_advisory)取最后一行 JSON 解析; 读不到 fail-open 返 ok=False。
GBK 安全: stdout 只出 ASCII JSON, 无 emoji / 无汉字 tag。
用法: python(3.11) E:/GoldstrategyEngine/mt5_readonly_probe.py
"""
import os
import json
import time

ACCOUNT_ID = 60137964
SERVER = "TradeMaxGlobal-Demo"
# 密码走环境变量(与 mt5_snapshot_write.py 同惯例), 终端已登同账户时免登录直接读


def _f(obj, *keys):
    for k in keys:
        v = getattr(obj, k, None)
        if v is not None:
            return v
    return None


def main():
    out = {"ok": False, "equity": None, "balance": None, "n_positions": 0,
           "n_orders": 0, "ref_symbol": None, "ref_tick": None,
           "ts": int(time.time()), "error": None}
    try:
        import MetaTrader5 as mt5
    except Exception as e:
        out["error"] = "import: %s" % str(e)[:80]
        print(json.dumps(out))
        return
    try:
        if not mt5.initialize():
            out["error"] = "initialize: %s" % str(mt5.last_error())[:80]
            print(json.dumps(out))
            return
        cur = mt5.account_info()
        if cur is None or getattr(cur, "login", None) != ACCOUNT_ID:
            if not mt5.login(ACCOUNT_ID,
                             password=os.environ.get("MT5_PASS_60137964", ""),
                             server=SERVER):
                out["error"] = "login: %s" % str(mt5.last_error())[:80]
                print(json.dumps(out))
                mt5.shutdown()
                return
        a = mt5.account_info()
        out["ok"] = True
        out["equity"] = _f(a, "equity")
        out["balance"] = _f(a, "balance")
        out["n_positions"] = len(mt5.positions_get() or [])
        out["n_orders"] = len(mt5.orders_get() or [])
        # XAU 参考 tick (未 select 前 last=0, 先 select 再取; 取不到用 XAU 在位仓 price_current 兜底)
        try:
            s = mt5.symbols_get("*XAU*")
            if s:
                nm = s[0].name
                try:
                    mt5.symbol_select(nm, True)
                except Exception:
                    pass
                t = mt5.symbol_info_tick(nm)
                if t is not None and t.last:
                    out["ref_symbol"] = nm
                    out["ref_tick"] = t.last
        except Exception:
            pass
        if not out.get("ref_tick"):
            try:
                for p in (mt5.positions_get() or []):
                    if "XAU" in str(getattr(p, "symbol", "")):
                        out["ref_symbol"] = getattr(p, "symbol", None)
                        out["ref_tick"] = getattr(p, "price_current", None)
                        break
            except Exception:
                pass
    except Exception as e:
        out["error"] = "probe: %s" % str(e)[:80]
    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass
    print(json.dumps(out))


if __name__ == "__main__":
    main()
