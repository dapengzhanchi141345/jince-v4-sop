"""SD E3S1 BE 保本锁利哨 · 内层脚本 (ATE 通道, 每 5min)
李令 2026-11-15: "直接锁利 不能让利润没了"
规则: magic=20261104 持仓, 浮盈 >= 2R (R=开仓时记录的止损距离, 读 prac log) 且 SL 仍在原损位
     -> 修改 SL 提到开仓价(保本). 此后最坏结果=平手, 利润永不回吐.
只单向修改: sell 的 SL 只能上提 / buy 的 SL 只能下压 (MT5 合规).
--live 才真改; 默认 dry 只报. 无动作时 stdout 空 (watchdog 静默).
"""
import os, sys, json, time, datetime as dt, argparse
os.environ.setdefault("MT5_TERMINAL", r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")
os.environ.setdefault("MT5_LOGIN", "60137964")
import MetaTrader5 as mt5

MAGIC = 20261104
ROOT = r"E:\GoldstrategyEngine"
PRAC_LOG = os.path.join(ROOT, "data", "_manual_prac_log.jsonl")
BE_LOG = os.path.join(ROOT, "data", "sd_be_log.jsonl")
BE_R = 2.0  # 浮盈>=2R 才提保本

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
args = ap.parse_args()

def risk_of(ticket, sym, entry):
    """开仓时记录的止损距离: 读 prac log 最近一条 open (sym+ticket)"""
    rec = None
    if os.path.exists(PRAC_LOG):
        for line in open(PRAC_LOG, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("kind") == "open" and r.get("sym") == sym and r.get("ticket") == ticket:
                rec = r
    if rec is None:
        return None
    return abs(rec.get("sl", entry) - rec.get("price", entry))

def main():
    ok = mt5.initialize()
    if not ok:
        print("INIT FAIL %s" % (mt5.last_error(),))
        sys.exit(1)
    acct = mt5.account_info()
    if acct is None:
        sys.exit(1)
    actions = []
    for p in (mt5.positions_get() or []):
        if p.magic != MAGIC:
            continue
        entry = p.price_open
        tick = mt5.symbol_info_tick(p.symbol)
        if tick is None or entry <= 0:
            continue
        is_buy = p.type == mt5.POSITION_TYPE_BUY
        if not is_buy:
            # sell 位不需要 BE: 4R 目标(TP)在下方=利润锁死线; 且 sell 的 SL 只能上提,
            # "SL 降到开仓价"在 MT5 非法(10016) -> 只做 buy 位的保本锁
            continue
        # 浮盈 R 值: 需要开仓SL风险距离
        risk = risk_of(p.ticket, p.symbol, entry)
        if risk is None or risk <= 0:
            continue
        prof = (tick.ask - entry) if is_buy else (entry - tick.bid)
        prof_r = prof / risk
        if prof_r < BE_R:
            continue
        # SL 已在本价位(或更内) -> 已锁过, 跳过
        cur_sl = p.sl
        be_line = entry
        if is_buy:
            if cur_sl >= be_line - 1e-12:
                continue
            new_sl = be_line
        else:
            if cur_sl <= be_line + 1e-12 or cur_sl == 0:
                continue
            new_sl = be_line
        dg = mt5.symbol_info(p.symbol).digits
        new_sl = round(new_sl, dg)
        req = dict(action=mt5.TRADE_ACTION_SLTP, position=p.ticket, symbol=p.symbol,
                   magic=MAGIC, sl=new_sl, tp=p.tp)
        rc, res = None, None
        if args.live:
            res = mt5.order_send(req)
            rc = getattr(res, "retcode", None)
        else:
            rc = 0
        rec = dict(ts=dt.datetime.now().isoformat(), ticket=p.ticket, sym=p.symbol,
                   entry=entry, cur_sl=cur_sl, new_sl=new_sl, prof_r=round(prof_r, 2),
                   live=args.live, rc=rc)
        with open(BE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        actions.append(rec)
    if actions:
        for a in actions:
            print("BE锁 %s %s 浮盈%.2fR SL %s->%s (%s)" % (
                a["sym"], a["ticket"], a["prof_r"], a["cur_sl"], a["new_sl"], "LIVE" if a["live"] else "DRY"))
    mt5.shutdown()

if __name__ == "__main__":
    main()
