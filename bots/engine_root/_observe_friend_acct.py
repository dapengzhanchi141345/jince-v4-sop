"""
只读观测朋友账户 60129252 (TradeMaxGlobal-Demo) 的波段EA策略。
使用 E:/mt5_friend_observer 隔离终端实例，绝不触碰用户自己的 60043976 实盘终端。
仅读取：账户信息 / 当前持仓 / 历史成交 / 历史订单。不交易、不修改。
"""
import MetaTrader5 as mt5
import json
import datetime
import os

EXE = "E:/mt5_friend_observer/terminal64.exe"
LOGIN = 60129252
PASSWORD = "Aa141345$"
SERVERS = ["TradeMaxGlobal-Demo", "123.56.129.232:443", "123.56.129.232:4433"]
OUT = "E:/GoldstrategyEngine/friend_acct_60129252_snapshot.json"

POS_FIELDS = ["ticket","time","type","volume","price_open","sl","tp","price_current",
              "profit","swap","comment","magic","symbol","time_msc"]
DEAL_FIELDS = ["ticket","order","time","type","entry","volume","price","profit","swap",
               "commission","symbol","comment","magic","reason"]
ORDER_FIELDS = ["ticket","time_setup","type","state","volume_initial","price_open","sl","tp",
                "symbol","comment","magic","reason"]

def nt_to_dict(nt, fields):
    d = {}
    for f in fields:
        v = getattr(nt, f, None)
        if isinstance(v, (datetime.datetime,)):
            v = v.strftime("%Y-%m-%d %H:%M:%S")
        d[f] = v
    return d

def main():
    if not mt5.initialize(path=EXE, timeout=90000):
        print("INIT_FAIL", mt5.last_error()); return
    authorized = False
    for srv in SERVERS:
        if mt5.login(LOGIN, password=PASSWORD, server=srv):
            authorized = True
            print("LOGIN_OK server=", srv)
            break
        else:
            print("LOGIN_FAIL server=", srv, mt5.last_error())
    if not authorized:
        print("ALL_LOGIN_FAILED"); mt5.shutdown(); return

    ai = mt5.account_info()
    acc = {k: getattr(ai, k, None) for k in
           ['login','server','balance','equity','profit','margin','margin_free',
            'margin_level','leverage','currency','company','trade_mode','limit_orders',
            'name','credit','filling_mode']}
    print("ACCOUNT:", acc)

    # 当前持仓
    positions = mt5.positions_get() or []
    pos_list = [nt_to_dict(p, POS_FIELDS) for p in positions]
    print(f"POSITIONS: {len(pos_list)}")

    # 历史成交（近 365 天）
    now = datetime.datetime.now()
    from_d = now - datetime.timedelta(days=365)
    deals = mt5.history_deals_get(from_d, now) or []
    deal_list = [nt_to_dict(d, DEAL_FIELDS) for d in deals]
    print(f"DEALS: {len(deal_list)}")

    # 历史订单
    orders = mt5.history_orders_get(from_d, now) or []
    order_list = [nt_to_dict(o, ORDER_FIELDS) for o in orders]
    print(f"ORDERS: {len(order_list)}")

    snapshot = {
        "captured_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "account": acc,
        "positions": pos_list,
        "deals": deal_list,
        "orders": order_list,
    }
    # 先把上一次快照备份为 .prev.json，供下次运行做 SL / 持仓 差分对比
    if os.path.exists(OUT):
        import shutil
        shutil.copyfile(OUT, OUT.replace(".json", ".prev.json"))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
    print("SAVED:", OUT, "size=", os.path.getsize(OUT))

    # ── 历史累积(时间序列, 供"盯着看"积累样本) ──
    hist_csv = "E:/GoldstrategyEngine/friend_acct_history.csv"
    floating = round(equity - balance, 2) if (balance := acc.get('balance')) is not None and (equity := acc.get('equity')) is not None else None
    # 持仓摘要: 按品种聚合 笔数@均价
    from collections import defaultdict
    sym_agg = defaultdict(lambda: [0, 0.0, 0.0])  # [n, vol_sum, profit_sum]
    for p in pos_list:
        s = p.get('symbol', '?')
        sym_agg[s][0] += 1
        sym_agg[s][1] += float(p.get('volume') or 0)
        sym_agg[s][2] += float(p.get('profit') or 0)
    pos_summary = "; ".join(f"{s}:{v[0]}笔@{v[1]:.2f}手盈{v[2]:.1f}" for s, v in sorted(sym_agg.items()))
    # SL / 均价 追踪 —— 反推「跟随下移」参数的核心线索
    sls = [float(p.get('sl') or 0) for p in pos_list if p.get('sl')]
    opens = [float(p.get('price_open') or 0) for p in pos_list]
    curs = [float(p.get('price_current') or 0) for p in pos_list if p.get('price_current')]
    sl_min = min(sls) if sls else None
    sl_max = max(sls) if sls else None
    avg_entry = round(sum(opens) / len(opens), 2) if opens else None
    price_now = round(sum(curs) / len(curs), 2) if curs else None
    # 持仓方向 (0=BUY/多, 1=SELL/空)。EA 会翻转方向, 必须记录, 否则 SL 侧别语义会反过来读错
    types = set(int(p.get('type') or 0) for p in pos_list)
    if not types:
        pos_side = "FLAT"
    elif types == {0}:
        pos_side = "LONG"
    elif types == {1}:
        pos_side = "SHORT"
    else:
        pos_side = "MIXED"
    # sl_vs_entry: SL 相对均价的符号距离(SL-均价)
    # sl_side 明确判定该 SL 位于亏损侧还是盈利侧, 与方向无关地可读
    sl_vs_entry = round(sl_min - avg_entry, 2) if (sl_min is not None and avg_entry) else None
    sl_dist_now = round(sl_min - price_now, 2) if (sl_min is not None and price_now) else None
    if sl_vs_entry is None or pos_side not in ("LONG", "SHORT"):
        sl_side = None
    elif pos_side == "SHORT":
        sl_side = "亏损侧" if sl_vs_entry > 0 else ("保本" if sl_vs_entry == 0 else "盈利侧")
    else:
        sl_side = "亏损侧" if sl_vs_entry < 0 else ("保本" if sl_vs_entry == 0 else "盈利侧")
    # 篮子止损命中的美元风险 (XAUUSD: 0.01手 每 $1 价格变动 = $1)
    sl_risk_usd = None
    if sl_min is not None:
        r = 0.0
        for p in pos_list:
            po, vol, ty = p.get('price_open'), p.get('volume'), int(p.get('type') or 0)
            s = p.get('sl')
            if po and vol and s:
                r += (float(s) - float(po)) * (1 if ty == 0 else -1) * float(vol) * 100
        sl_risk_usd = round(r, 2)
    row = {
        "captured_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "balance": acc.get('balance'),
        "equity": acc.get('equity'),
        "floating_profit": floating,
        "n_positions": len(pos_list),
        "n_deals": len(deal_list),
        "n_orders": len(order_list),
        "positions_summary": pos_summary,
        "sl_min": sl_min,
        "sl_max": sl_max,
        "avg_entry": avg_entry,
        "price_now": price_now,
        "sl_vs_entry": sl_vs_entry,
        "sl_dist_now": sl_dist_now,
        "pos_side": pos_side,
        "sl_side": sl_side,
        "sl_risk_usd": sl_risk_usd,
    }
    import csv
    fields = list(row.keys())
    # 表头迁移: 若已有 CSV 列数较少, 补齐表头并给旧行填空, 避免列错位
    if os.path.exists(hist_csv):
        with open(hist_csv, "r", encoding="utf-8", newline="") as f:
            old_rows = list(csv.reader(f))
        if old_rows and old_rows[0] != fields:
            with open(hist_csv, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(fields)
                pad = len(fields) - len(old_rows[0])
                for r in old_rows[1:]:
                    if r:
                        w.writerow(r + [""] * pad)
            print("HISTORY_HEADER_MIGRATED: +", pad, "cols")
        write_header = False
    else:
        write_header = True
    with open(hist_csv, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            w.writeheader()
        w.writerow(row)
    print("HISTORY_APPENDED:", hist_csv)
    mt5.shutdown()

if __name__ == "__main__":
    main()
