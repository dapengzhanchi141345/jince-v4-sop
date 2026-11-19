# -*- coding: utf-8 -*-
"""
只读反推朋友 Godking Apex 的【平仓/退出逻辑】。
拉 60129252 近 30 天 deal 历史, 按 position_id 聚合 entry/exit,
打印 开仓价/平仓价/SL/TP/盈亏/持仓时长 → 反推: 是否移动SL(追踪)、
TP 是否=0(趋势退出)、退出是 SL 命中还是反向信号。
只读, 不交易。隔离观测终端。
"""
import MetaTrader5 as mt5
import numpy as np, json, os, time

EXE = r"E:/mt5_friend_observer/terminal64.exe"
ACC = 60129252
PW = "Aa141345$"
SERVER = "TradeMaxGlobal-Demo"


def init():
    for path in (EXE, None):
        try:
            if path:
                if not mt5.initialize(path=path, timeout=60000):
                    continue
            else:
                if not mt5.initialize(timeout=60000):
                    continue
            if mt5.login(ACC, password=PW, server=SERVER):
                print(f"[init] 连接成功 via {'observer' if path else 'system'} terminal")
                return True
            else:
                print("[init] login 失败:", mt5.last_error())
        except Exception as e:
            print(f"[init] path={path} 异常: {e}")
    return False


def main():
    if not init():
        print("INIT_FAIL")
        return
    ai = mt5.account_info()
    print(f"账户: login={ai.login} server={ai.server} 权益={ai.equity:.2f}")

    now = int(time.time())
    deals = mt5.history_deals_get(now - 30 * 86400, now)
    if not deals:
        print("NO_DEALS")
        mt5.shutdown()
        return
    print(f"总 deal 数: {len(deals)}")

    # 按 position_id 聚合
    pos = {}
    for d in deals:
        pid = d.position_id
        if pid == 0:
            continue
        sym = d.symbol
        rec = pos.setdefault(pid, {"symbol": sym, "deals": [], "entry": None, "exit": None})
        rec["deals"].append(d)
        if d.entry == 0:  # ENTRY
            rec["entry"] = d
        elif d.entry == 1:  # EXIT (in/out)
            rec["exit"] = d

    print(f"独立持仓(position)数: {len(pos)}\n")
    out = []
    for pid, rec in sorted(pos.items(), key=lambda kv: (kv[1]['entry'].time if kv[1]['entry'] else 0)):
        e = rec["entry"]
        x = rec["exit"]
        sym = rec["symbol"]
        tick = mt5.symbol_info_tick(sym)
        # 取该持仓 entry/exit 的 SL/TP(从 deal 的 magic/comment 难拿, 用 positions 历史不可得)
        # 改用 deal 价格 + profit 反推
        if e is None or x is None:
            # 仍持仓(只有 entry 无 exit) 或 部分平仓
            vol = sum(d.volume for d in rec["deals"] if d.entry == 0)
            print(f"  [持仓中] pid={pid} {sym} vol={vol:.2f} deals={len(rec['deals'])}")
            out.append({"pid": pid, "symbol": sym, "state": "open", "n_deals": len(rec["deals"])})
            continue
        etime = time.strftime("%m-%d %H:%M", time.localtime(e.time))
        xtime = time.strftime("%m-%d %H:%M", time.localtime(x.time))
        direction = "BUY" if e.type == mt5.DEAL_TYPE_BUY else "SELL"
        dur_h = (x.time - e.time) / 3600.0
        profit = x.profit + (e.profit or 0)  # exit profit 已含; entry profit 通常0
        print(f"  [{sym} {direction}] pid={pid}")
        print(f"    开 {etime} px={e.price:.2f} vol={e.volume:.2f}")
        print(f"    平 {xtime} px={x.price:.2f} profit={x.profit:.2f} 时长={dur_h:.1f}h ({dur_h/24:.1f}d)")
        out.append({"pid": pid, "symbol": sym, "dir": direction,
                    "entry_px": e.price, "exit_px": x.price,
                    "profit": x.profit, "dur_h": round(dur_h, 1)})

    # 当前持仓(实时 SL/TP)
    print("\n=== 当前持仓 (实时 SL/TP) ===")
    positions = mt5.positions_get() or []
    fpos = [p for p in positions if p.symbol.startswith("XAU")]
    for p in fpos:
        print(f"  {p.symbol} {'BUY' if p.type==mt5.POSITION_TYPE_BUY else 'SELL'} "
              f"vol={p.volume:.2f} open={p.price_open:.2f} sl={p.sl:.2f} tp={p.tp:.2f} "
              f"cur={p.price_current:.2f}")
    out.append({"open_positions": len(fpos)})

    with open("E:/GoldstrategyEngine/friend_deal_history_probe.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print("\nSAVED friend_deal_history_probe.json")
    mt5.shutdown()


if __name__ == "__main__":
    main()
