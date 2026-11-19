# -*- coding: utf-8 -*-
r"""金策·一键 kill switch 执行器 (ATE 通道, 独立于主引擎)
顶配风控铁律(FIA 2024): 紧急开关必须独立于主交易逻辑, 主引擎挂死时仍可用。
动作: ①撤全部挂单(orders_get 全 magic 段) ②市价全平(positions_get 逐个 close)
      ③写 risk_state.halt=true ④30s 复核: 仍有挂单/持仓=红色报
用法: ATE python 直接跑; 由 jince_kill_switch_watch.py(每1min cron)在触发文件生效时调用。
"""
import json
import os
import sys
import time
import datetime

DATA = r"E:\GoldstrategyEngine\data"
KS = os.path.join(DATA, "kill_switch.json")
RISK = os.path.join(DATA, "risk_state.json")


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    import MetaTrader5 as mt5
    ok = mt5.initialize()
    if not ok:
        print("[KILL] FAIL: MT5 initialize 失败(%s), 重试待下一分钟" % mt5.last_error())
        sys.exit(2)
    time.sleep(3)
    # ①撤全挂单
    cancelled, fails = 0, []
    for o in (mt5.orders_get() or []):
        r = mt5.order_delete(o.ticket)
        cancelled += 1 if (r and r["retcode"] in (10009, 10010)) else 0
        if not (r and r["retcode"] in (10009, 10010)):
            fails.append("order%d rc=%s" % (o.ticket, r["retcode"] if r else "?"))
    # ②市价全平
    closed, fails2 = 0, []
    for p in (mt5.positions_get() or []):
        tick = mt5.symbol_info_tick(p.symbol)
        if tick is None:
            fails.append("pos%s tick None" % p.ticket)
            continue
        px = tick.bid if p.type == 0 else tick.ask
        r = mt5.trade_position_close(p.ticket, px, p.sl or 0, p.tp or 0)
        closed += 1 if (r and r["retcode"] in (10009, 10010)) else 0
        if not (r and r["retcode"] in (10009, 10010)):
            fails2.append("pos%s rc=%s" % (p.ticket, r["retcode"] if r else "?"))
    # ③halt 落盘(引擎侧下轮读 risk_state 制动; 各哨同读)
    rs = {}
    if os.path.exists(RISK):
        try:
            rs = json.load(open(RISK, encoding="utf-8"))
        except Exception:
            rs = {}
    rs["halt"] = True
    rs["halt_ts"] = now()
    rs["halt_by"] = "kill_switch"
    json.dump(rs, open(RISK, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # ④30s 复核
    time.sleep(30)
    remain_o = len(mt5.orders_get() or [])
    remain_p = len(mt5.positions_get() or [])
    lines = ["[KILL] 全平执行 %s: 撤挂单%d 平仓%d, 30s复核 剩挂单%d 剩持仓%d" % (now(), cancelled, closed, remain_o, remain_p)]
    if fails or fails2:
        lines.append("[KILL] 明细: " + "; ".join((fails + fails2)[:10]))
    if remain_o or remain_p:
        lines.append("⚠️ 红色: 仍有活单未平, 人工介入(再跑本脚本或终端手平)")
    else:
        lines.append("✅ 全平完成; 恢复=人工将 kill_switch.json state 翻回 ARMED + 主bot 翻 risk_state.halt=false + chief 留痕")
    print("\n".join(lines))
    mt5.shutdown()
    sys.exit(0 if not (remain_o or remain_p or fails or fails2) else 1)


if __name__ == "__main__":
    main()
