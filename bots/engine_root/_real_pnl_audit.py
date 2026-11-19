
# -*- coding: utf-8 -*-
# 裁判: MT5 实盘(模拟盘)日内腿真实成交 P&L — 回放数字 vs 真钱
import json, datetime
import MetaTrader5 as mt5
mt5.initialize(); assert mt5.login(60137964, password="", server="TradeMaxGlobal-Demo")
magic = 20260903
now = int(datetime.datetime.now().timestamp())
# 全部历史成交 (按 magic 过滤, 不限时间)
deals = mt5.history_deals_get(now - 400*86400, now)
mine = [d for d in (deals or []) if d.magic == magic]
# 只取 成交/平仓 类
intra_pnl, trend_pnl, range_pnl = [], [], []
sym_intra = {}
for d in mine:
    is_close = d.entry == 2  # DEAL_ENTRY_OUT
    if not is_close: continue
    com = d.comment or ""
    # 归类: 用 comment 里的 tag (intra_stall / range_exit / rev_early / 止盈止损)
    pnl = d.profit + d.swap + d.commission
    if "intra" in com.lower() or d.comment and "intra" in str(d.comment).lower():
        intra_pnl.append(pnl)
    print(f"{d.symbol} {com!r} pnl={pnl:+.2f} ts={datetime.datetime.utcfromtimestamp(d.time)}")
print("---")
print(f"实盘成交平仓笔数(magic={magic}): {len([d for d in mine if d.entry==2])}")
mt5.shutdown()
