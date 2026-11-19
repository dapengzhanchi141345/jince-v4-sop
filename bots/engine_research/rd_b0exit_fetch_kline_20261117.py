# -*- coding: utf-8 -*-
"""rd_b0exit_fetch_kline_20261117.py — MT5 只读取K线: M30增量/全量 + M15 30d窗 + 20261105 4单实读
红线: 纯只读(0 order_send / 0 改设置 / 0 动引擎). 产物落 data/tf_cache + data/ 报告.
M30: 已有 npz 品种=增量追加(老npz+MT5新bar去重合并, 覆盖回原文件); GBPUSD/US30=全量新存.
M15: 8主流+4美股, 全量新存 data/tf_cache/{SYM}_M15.npz (30d窗+45天buffer).
M30 D1 不动(1114口径M30+D1, 本任务不需要D1增量).
"""
import os, json, time, datetime as dt
import numpy as np

ROOT = "E:/GoldstrategyEngine"
CACHE = os.path.join(ROOT, "data", "tf_cache")
os.environ['MT5_TERMINAL'] = r'C:\Program Files\TMGM MT5 Terminal\terminal64.exe'
os.environ['MT5_LOGIN'] = '60137964'
import MetaTrader5 as mt5

TF = {'M30': 30, 'M15': 15, 'D1': 1440}
MAINS = ["XAUUSD", "EURUSD", "GBPUSD", "US30", "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"]
STOCKS = ["BLK.NYS", "KLAC.NAS", "AVGO.NAS", "TSLA.NAS"]
WIN_START = dt.datetime(2026, 10, 1, 0, 0, 0).timestamp()  # 45d buffer, 30d窗=10-18起
REPORT = {"ts": dt.datetime.now().strftime("%F %T"), "per_sym": {}, "ok": True}


def safe_init(max_wait=300):
    """终端2h自重启窗: 初始化失败等5min重试(红线: 读失败重试, 仍失败=BLOCKED_DATA挂账)."""
    for i in range(4):
        try:
            if mt5.initialize(timeout=15000):
                return True
        except Exception:
            pass
        if i < 3:
            time.sleep(60)
    return False


def fetch(sym, tf, start, end):
    mt5.symbol_select(sym, True)
    for attempt in range(3):
        rr = mt5.copy_rates_range(sym, TF[tf], start, end)
        if rr is not None and len(rr) > 0:
            a = rr
            return {'t': a['time'].astype(np.int64), 'o': a['open'].astype(np.float64),
                    'h': a['high'].astype(np.float64), 'l': a['low'].astype(np.float64),
                    'c': a['close'].astype(np.float64)}
        time.sleep(8)
    return None


def main():
    if not safe_init():
        REPORT.update(ok=False, err="initialize 3次x60s 全败=终端重启窗/断连, 全部品种 BLOCKED_DATA 挂账")
        json.dump(REPORT, open(os.path.join(ROOT, "data", "rd_b0exit_fetch_report_20261117.json"), "w"), ensure_ascii=False, indent=1)
        print(json.dumps(REPORT, ensure_ascii=False)); return

    acc = mt5.account_info()
    orders0 = mt5.history_orders_get(dt.datetime.now() - dt.timedelta(days=60), dt.datetime.now()) or []
    REPORT['equity'] = float(acc.equity) if acc else None
    REPORT['history_orders_n_before'] = len(orders0)

    end = time.time() + 86400
    now_ms = int(time.time())

    # ── M30: 6老品种增量 + GBP/US30 全量 ──
    for sym in MAINS:
        tfn = os.path.join(CACHE, f"{sym}_M30.npz")
        old = None
        if os.path.exists(tfn):
            z = np.load(tfn); old = {k: z[k] for k in ('t', 'h', 'l', 'c') if k in z.files}; z.close()
        f = fetch(sym, 'M30', WIN_START, end)
        if f is None:
            REPORT['per_sym'][sym + '_M30'] = 'BLOCKED_DATA(copy_rates_range 3次None)'
            continue
        rec = {'n_new': len(f['t']), 'last': dt.datetime.utcfromtimestamp(float(f['t'][-1])).strftime('%F %H:%M UTC')}
        if old is not None:
            # 增量合并: 老 npz + 新 bar, 按 t 去重, 仅当新数据末端>老末端才写
            t_old = old['t']
            t_new = f['t']
            mask = (t_new > t_old[-1]) | (t_new < t_old[0])
            if not mask.any():
                rec['merge'] = 'no_new_bars(缓存末端已>=MT5末端), 原npz不动'
                REPORT['per_sym'][sym + '_M30'] = rec
                continue
            newpart = {k: f[k][mask] for k in ('t', 'h', 'l', 'c')}
            t_all = np.concatenate([t_old, newpart['t']])
            order = np.argsort(t_all, kind='stable')
            uniq, keepmask = np.unique(t_all[order], return_index=True)
            keep = order[keepmask]
            merged = {k: np.concatenate([old[k], newpart[k]])[keep] for k in ('t', 'h', 'l', 'c')}
            extra = {k: v for k, v in old.items() if k not in merged}  # 保留原 npz 其余列(如o)
            tmp = tfn + '.rdnew_tmp.npz'
            np.savez(tmp, **merged, **extra)
            os.replace(tmp, tfn)  # 原子替换, 防引擎并发读半写
            rec['n_after'] = len(merged['t'])
            rec['merge'] = f"incremental append {len(newpart)} bars -> {tfn} (rd合并, 非引擎数据, 保留原列{list(extra)})"
        else:
            np.savez(tfn, t=f['t'], o=f['o'], h=f['h'], l=f['l'], c=f['c'])
            rec['n_after'] = len(f['t'])
            rec['merge'] = f"全量新建 {tfn}"
        REPORT['per_sym'][sym + '_M30'] = rec

    # ── M15: 8主流 + 4美股 ──
    for sym in MAINS + STOCKS:
        f = fetch(sym, 'M15', WIN_START, end)
        if f is None:
            REPORT['per_sym'][sym + '_M15'] = 'BLOCKED_DATA'
            continue
        npz = os.path.join(CACHE, f"{sym.replace('.', '_')}_M15.npz")
        np.savez(npz, t=f['t'], o=f['o'], h=f['h'], l=f['l'], c=f['c'])
        REPORT['per_sym'][sym + '_M15'] = {
            'n': len(f['t']),
            'first': dt.datetime.utcfromtimestamp(float(f['t'][0])).strftime('%F %H:%M UTC'),
            'last': dt.datetime.utcfromtimestamp(float(f['t'][-1])).strftime('%F %H:%M UTC'),
            'path': npz}

    # ── 20261105 4单实读(只读 deals, 不下单) ──
    now = dt.datetime.now()
    deals = mt5.history_deals_get(now - dt.timedelta(days=45), now + dt.timedelta(hours=1)) or []
    m1105 = [d for d in deals if d.magic == 20261105]
    REPORT['deals_20261105_n'] = len(m1105)
    opens, closes = [], []
    for d in m1105:
        rec = {'ticket': int(d.ticket), 'deal_type': int(d.type), 'entry': int(d.entry),
               'time': int(d.time), 'price': float(d.price), 'profit': float(d.profit),
               'volume': float(d.volume), 'comment': str(d.comment)}
        if d.entry == 0:
            opens.append(rec)
        elif d.entry == 1:
            closes.append(rec)
    REPORT['deals_20261105_opens'] = opens
    REPORT['deals_20261105_closes'] = closes

    # 红线后置: 订单数不变
    orders1 = mt5.history_orders_get(now - dt.timedelta(days=60), now) or []
    REPORT['history_orders_n_after'] = len(orders1)
    REPORT['mt5_zero_orders_delta'] = len(orders1) - len(orders0)

    mt5.shutdown()
    json.dump(REPORT, open(os.path.join(ROOT, "data", "rd_b0exit_fetch_report_20261117.json"), "w"),
              ensure_ascii=False, indent=1, default=float)
    print("FETCH_DONE", json.dumps({k: v for k, v in REPORT.items() if k != 'per_sym'}, ensure_ascii=False), flush=True)
    for k, v in REPORT['per_sym'].items():
        print(' ', k, json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v, flush=True)


if __name__ == '__main__':
    main()
