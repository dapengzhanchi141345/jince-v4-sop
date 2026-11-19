# SD-E3S1 全品种批 12h 禁隔夜强平哨-循环版 (no_agent, 30min tick)
# 逻辑: magic=20261104 的 SD 批持仓, 开仓+12h 到期未平 -> IOC 市价强平 + 留痕
# --until-hours N: 循环模式, 每30min tick, 直到 N 小时或本 magic 无持仓 (覆盖挂单成交窗口)
# --live 才真强平; 默认 dry 只报数
# 薄壳: hermes runner python subprocess 调 3.13.12 解释器执行 ATE 通道
import subprocess, json, time, datetime as dt, os, argparse

ATE = r"D:\workbuddy\binaries\python\versions\3.13.12\python.exe"
SCRIPT = r"""
import os, json, time, datetime as dt, argparse
os.environ.setdefault("MT5_TERMINAL", r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe")
os.environ.setdefault("MT5_LOGIN", "60137964")
import MetaTrader5 as mt5
MAGIC = 20261104
LOG = r"E:\GoldstrategyEngine\data\sd_e3s1_forceclose_log.jsonl"
ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
ap.add_argument("--until-hours", type=float, default=0.0)
args = ap.parse_args()
ok = mt5.initialize()
if not ok:
    print("INIT FAIL %s" % (mt5.last_error(),)); raise SystemExit(1)
acct = mt5.account_info()
if acct is None: raise SystemExit("account None")
LIVE = args.live

def tick_once():
    now = time.time()
    closed, skipped, n_pos = [], [], 0
    for p in (mt5.positions_get() or []):
        if p.magic != MAGIC: continue
        n_pos += 1
        age_h = (now - p.time) / 3600
        if age_h <= 12: continue
        tick = mt5.symbol_info_tick(p.symbol)
        if tick is None: continue
        if p.type == mt5.POSITION_TYPE_BUY:
            req = dict(action=mt5.TRADE_ACTION_DEAL, position=p.ticket, volume=p.volume,
                       type=mt5.ORDER_TYPE_SELL, price=tick.ask, deviation=10, magic=MAGIC,
                       comment="SD12H-X", type_filling=mt5.ORDER_FILLING_IOC)
        else:
            req = dict(action=mt5.TRADE_ACTION_DEAL, position=p.ticket, volume=p.volume,
                       type=mt5.ORDER_TYPE_BUY, price=tick.bid, deviation=10, magic=MAGIC,
                       comment="SD12H-X", type_filling=mt5.ORDER_FILLING_IOC)
        res = mt5.order_send(req)
        rc = getattr(res, "retcode", None)
        for _ in range(3):
            if rc in (10009, 10010): break
            time.sleep(2)
            res = mt5.order_send(req)
            rc = getattr(res, "retcode", None)
        if rc in (10009, 10010):
            closed.append(dict(ticket=p.ticket, symbol=p.symbol, age_h=round(age_h, 1)))
        else:
            skipped.append(dict(ticket=p.ticket, symbol=p.symbol, rc=rc))
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(ts=dt.datetime.now().isoformat(), ticket=p.ticket,
                                    symbol=p.symbol, age_h=round(age_h, 1), retcode=rc, live=LIVE)) + "\n")
    a = mt5.account_info()
    print("positions(magic)=%d 强平=%d 余=%d 净值=$%.2f (%s)" % (
        n_pos, len(closed), len(skipped), a.equity, "LIVE" if LIVE else "DRY"))
    return n_pos

if args.until_hours > 0:
    end = time.time() + args.until_hours * 3600
    while time.time() < end:
        if tick_once() == 0:
            print("本magic无持仓 -> 哨兵任务完成")
            break
        time.sleep(1800)
else:
    tick_once()
mt5.shutdown()
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="执行强平(默认dry)")
    ap.add_argument("--until-hours", type=float, default=0.0,
                    help="循环模式: 每30min检查直到N小时或本magic无持仓")
    args = ap.parse_args()
    cmd = [ATE, "-c", SCRIPT, "--until-hours", str(args.until_hours)]
    if args.live:
        cmd.append("--live")
    r = subprocess.run(cmd, capture_output=True,
                       timeout=max(180, int(args.until_hours * 3600) + 300),
                       env={k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")})
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    print(out.strip())
    raise SystemExit(r.returncode)

if __name__ == "__main__":
    main()
