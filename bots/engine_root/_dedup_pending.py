# -*- coding: utf-8 -*-
# 只清"同价堆叠挂单"(方案1): 同品种同单型, 触发价接近 AND SL距离接近 → 保留最早1张, 撤重复的
# 安全闸: 价格接近但SL差很远(不同layer)的不撤. DRY默认, --live 才撤.
import sys, os, json, time
from collections import defaultdict
import MetaTrader5 as mt5

LIVE = "--live" in sys.argv
PRICE_TOL = 0.003      # 触发价相对差 < 0.3% 视为同点位
SL_TOL = 0.35          # SL距离相对差 < 35% 视为同层 (防误伤不同layer同价单)

# 挂单 ticket → state 映射 (撤单后同步删 state.pending, 防 reevaluate 重挂)
STATE_FILES = {
    20260902: "E:/GoldstrategyEngine/data/pending_orders_state.json",
    20260903: "E:/GoldstrategyEngine/data/crypto_pending_state.json",
    20260904: "E:/GoldstrategyEngine/data/equity_pending_state.json",
}
TYPE_NAMES = {2: "SELL_LIMIT", 3: "BUY_LIMIT", 4: "SELL_STOP", 5: "BUY_STOP"}


def px_of(o):
    return float(getattr(o, "price_open", 0) or 0)


def sl_dist(o):
    e = px_of(o); sl = float(getattr(o, "sl", 0) or 0)
    return abs(e - sl) if sl > 0 else 9e9


def main():
    ok = mt5.initialize()
    mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
    orders = [o for o in (mt5.orders_get() or [])]
    print(f"init={ok} 净值=${mt5.account_info().equity:.2f} 挂单总数={len(orders)} mode={'LIVE' if LIVE else 'DRY'}")

    # 按 (sym, ptype) 分组
    groups = defaultdict(list)
    for o in orders:
        groups[(o.symbol, o.type)].append(o)

    to_cancel = []   # (ticket, sym, ptype, price, why, kept_ticket)
    for (sym, ptype), lst in sorted(groups.items()):
        if len(lst) < 2:
            continue
        lst.sort(key=lambda o: o.ticket)   # 最早在前
        kept = lst[0]
        for o in lst[1:]:
            dprice = abs(px_of(o) - px_of(kept)) / max(px_of(kept), 1e-9)
            ds = min(abs(sl_dist(o) - sl_dist(kept)) / max(sl_dist(kept), 1e-9),
                     abs(sl_dist(o) - sl_dist(kept)) / max(sl_dist(o), 1e-9))
            if dprice < PRICE_TOL and ds < SL_TOL:
                to_cancel.append((o.ticket, sym, ptype, px_of(o), px_of(kept), kept.ticket))
                print(f"  [撤] #{o.ticket} {sym} {TYPE_NAMES[ptype]} @{px_of(o):.6g} "
                      f"SL距{sl_dist(o):.4g} (与保留#{kept.ticket}价近/同层) 价距{dprice*100:.2f}% SL距{ds*100:.0f}%")
        # 非堆叠的同ptype多单 (价或SL差太远) 提示但不撤
        n_distinct = len(lst) - sum(1 for t in to_cancel if t[1] == sym and t[2] == ptype)
        if n_distinct >= 2 and any(d >= SL_TOL for d in [min(abs(sl_dist(a)-sl_dist(b))/max(sl_dist(a),sl_dist(b),1e-9),
                                                               abs(sl_dist(a)-sl_dist(b))/max(sl_dist(b),1e-9))
                                                       for i,a in enumerate(lst[1:]) for b in [lst[0]]]) :
            pass

    print(f"\n待撤堆叠挂单 {len(to_cancel)} 张 (保留各点位最早1张, 撤 {len(to_cancel)})")
    if not to_cancel:
        print("无同价堆叠, 无需清理"); mt5.shutdown(); return

    if not LIVE:
        print("DRY 模式: 未下单. 加 --live 真撤")
        mt5.shutdown(); return

    # 真撤
    cancelled = failed = 0
    for ticket, sym, ptype, e, kpx, kept in to_cancel:
        r = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": int(ticket)})
        if r and r.retcode == mt5.TRADE_RETCODE_DONE:
            cancelled += 1
            print(f"  ✓ 撤 #{ticket} {sym} @{e:.6g} (保留#{kept})")
            # 同步删 state.pending
            for magic, sf in STATE_FILES.items():
                if os.path.exists(sf):
                    st = json.load(open(sf, encoding="utf-8"))
                    if str(ticket) in st.get("pending", {}):
                        st["pending"].pop(str(ticket))
                        json.dump(st, open(sf, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        else:
            failed += 1
            print(f"  ✗ 撤 #{ticket} {sym} retcode={getattr(r,'retcode',None)} {getattr(r,'comment','')}")
    print(f"\n撤 {cancelled} 张, 失败 {failed} 张. 剩余挂单 {len(orders)-cancelled}")
    mt5.shutdown()


main()
