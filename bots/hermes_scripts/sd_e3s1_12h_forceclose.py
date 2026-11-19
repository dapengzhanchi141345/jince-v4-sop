# SD-E3S1 全品种批 12h 禁隔夜强平哨 (no_agent, 30min 轮)
# 逻辑: magic=20261104 的 SD-E3S1 批持仓, 开仓+12h 到期未平 -> IOC 市价强平 + 留痕
# 薄壳: hermes runner python subprocess 调 3.13.12 解释器执行 ATE 通道
import subprocess, json, time, datetime as dt, os

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
LIVE = ap.parse_args().live
# 11-16即时启动机制(李令): INIT 失败 5min 重试 x3, 不干等 30min 下拍
ok = False
import time as _time
for _i in range(3):
    ok = mt5.initialize()
    if ok:
        break
    print("INIT FAIL(第%d次) %s -> 5min 后零参重登重试" % (_i + 1, mt5.last_error()), flush=True)
    _time.sleep(300)
if not ok:
    print("INIT FAIL 3次仍败 %s" % (mt5.last_error(),)); raise SystemExit(1)
acct = mt5.account_info()
if acct is None: raise SystemExit("account None")
now = time.time()
closed, skipped, n_pos = [], [], 0
for p in (mt5.positions_get() or []):
    if p.magic != MAGIC: continue
    n_pos += 1
    age_h = (now - p.time) / 3600.0
    # 分级强平 11-15优化: 锁利单(SL已被棘轮推进开仓价另一侧=利润锁死)豁免12h, 24h二道闸
    # 未锁利单(SL仍在原始止损位, 浮亏可扩大) -> 12h照砍(隔夜缺口防护)
    locked = (p.type == mt5.POSITION_TYPE_BUY and p.sl > p.price_open) or \
             (p.type == mt5.POSITION_TYPE_SELL and p.sl < p.price_open)
    due = (age_h > 24.0) or (age_h > 12.0 and not locked)
    if not due:
        continue
    # P0-1修复(11-15三方审查): 平仓逻辑原缩进在 if not due: 块内 continue 之后=死代码.
    # 现 dedent 到 for 循环体; 平BUY=SELL@bid, 平SELL=BUY@ask (M3: 原 bid/ask 用反);
    # 成功码收口 (10008挂单受理/10009完成/10010已挂), 10019=NO_MONEY 不算成功.
    tick = mt5.symbol_info_tick(p.symbol)
    if tick is None: continue
    if p.type == mt5.POSITION_TYPE_BUY:
        req = dict(action=mt5.TRADE_ACTION_DEAL, position=p.ticket, volume=p.volume,
                   type=mt5.ORDER_TYPE_SELL, price=tick.bid, deviation=10, magic=MAGIC,
                   comment="SD12H-X", type_filling=mt5.ORDER_FILLING_IOC)
    else:
        req = dict(action=mt5.TRADE_ACTION_DEAL, position=p.ticket, volume=p.volume,
                   type=mt5.ORDER_TYPE_BUY, price=tick.ask, deviation=10, magic=MAGIC,
                   comment="SD12H-X", type_filling=mt5.ORDER_FILLING_IOC)
    if LIVE:
        res = mt5.order_send(req)
        rc = getattr(res, "retcode", None)
        for _ in range(3):
            if rc == 10009: break  # P2修(11-15御史): DEAL平仓只认10009完成; 10008(受理未成)/10010不算已平, 走重试
            time.sleep(2)
            tick2 = mt5.symbol_info_tick(p.symbol)
            if tick2 is not None:
                px = tick2.bid if p.type == mt5.POSITION_TYPE_BUY else tick2.ask
                req = dict(req)
                req["price"] = px
            res = mt5.order_send(req)
            rc = getattr(res, "retcode", None)
    else:
        rc = 0  # dry: 只计数不下单
    if LIVE and rc == 10009:  # P2修(11-15御史): 只认10009
        closed.append(dict(ticket=p.ticket, symbol=p.symbol, age_h=round(age_h, 1)))
    elif not LIVE:
        closed.append(dict(ticket=p.ticket, symbol=p.symbol, age_h=round(age_h, 1)))
    else:
        skipped.append(dict(ticket=p.ticket, symbol=p.symbol, rc=rc))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(ts=dt.datetime.now().isoformat(), ticket=p.ticket, symbol=p.symbol,
                                rc=rc, live=LIVE)) + "\n")
# P2修(11-15御史/进化营余项c): GTC挂单超龄撤销 — magic 20261104 挂单龄>30h撤销, 防跨日旧价在新区间触发(周一新区批次前清旧腿)
cancelled, n_ord = [], 0
for o in (mt5.orders_get() or []):
    if o.magic != MAGIC: continue
    n_ord += 1
    oage_h = (now - o.time_setup) / 3600.0
    if oage_h > 30.0:
        if LIVE:
            req2 = dict(action=mt5.TRADE_ACTION_REMOVE, order=o.ticket, symbol=o.symbol,
                        magic=MAGIC, type_time=mt5.ORDER_TIME_GTC, comment="SD-AGING-X")
            res2 = mt5.order_send(req2)
            rc2 = getattr(res2, "retcode", None)
            if rc2 == 10009:
                cancelled.append(dict(ticket=o.ticket, symbol=o.symbol, age_h=round(oage_h, 1)))
        else:
            cancelled.append(dict(ticket=o.ticket, symbol=o.symbol, age_h=round(oage_h, 1)))
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(ts=dt.datetime.now().isoformat(), ticket=o.ticket, symbol=o.symbol,
                                    op="cancel_aging", rc=(rc2 if LIVE else 0), live=LIVE)) + "\n")
mt5.shutdown()
if n_pos == 0 and not closed and not cancelled and not skipped:
    pass  # watchdog: 无持仓不打扰
else:
    print("forceclose: positions=%d closed=%d skipped=%d cancel_aging=%d" % (n_pos, len(closed), len(skipped), len(cancelled)))
"""
r = subprocess.run([ATE, "-c", SCRIPT] + (["--live"] if os.environ.get("SD_FORCE_LIVE") else []),
                   capture_output=True, timeout=180,
                   env={k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")})
out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
print(out.strip())
raise SystemExit(r.returncode)
