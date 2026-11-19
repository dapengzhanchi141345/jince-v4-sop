# -*- coding: utf-8 -*-
"""
account_capacity.py — 账户可承受度诊断

回答一个决定性问题: 这个 $961.54 的模拟账户, 到底"开得起"哪些品种?

对每个可交易品种:
  1. 从真实 CSV 算 H4 ATR 中位数 -> 典型 SL 距离 (sl_mult × ATR)
  2. 用真实 pip_usd + 券商最小手 volume_min -> 最小手单笔风险 $
  3. 风险占账户净值 % -> 判定 OK / 偏大 / 开不起

判定:
  OK        最小手风险 ≤ 1% 净值      -> 可正常按风险定手
  TIGHT     1% < 风险 ≤ 2%           -> 只能勉强开最小手, 无仓位调节空间
  TOO_BIG   风险 > 2%                -> 真实账户不该交易 (一笔亏掉 2%+)
"""
import os, sys, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import symbol_universe as su

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def atr(df, n=14):
    h, l, c = df['high'].values, df['low'].values, df['close'].values
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    s = pd.Series(tr).rolling(n).mean().values
    return s


def main():
    su.calibrate_forex_pip_usd(DATA_DIR)
    n_sp, _ = su.apply_account_specs(DATA_DIR)
    if not n_sp:
        print("!! 缺少 account_specs.json, 先跑 account_calibrate.py")
        return 1
    eq = float(su.ACCOUNT.get('balance') or 0)
    print(f"\n{'='*100}")
    print(f"  账户可承受度诊断 | {su.ACCOUNT.get('login')} @ {su.ACCOUNT.get('server')} "
          f"| 净值 ${eq:.2f} | 杠杆 1:{su.ACCOUNT.get('leverage')}")
    print(f"  判定: 最小手单笔风险 ≤1%=OK, ≤2%=TIGHT(勉强), >2%=TOO_BIG(开不起)")
    print(f"{'='*100}")

    rows = []
    for sym, cfg in su.UNIVERSE.items():
        if not cfg.get('tradable'):
            continue
        f4 = os.path.join(DATA_DIR, f"{sym}_H4.csv")
        if not os.path.exists(f4):
            continue
        try:
            d4 = pd.read_csv(f4)
        except Exception:
            continue
        if len(d4) < 60:
            continue
        a = atr(d4)
        a = a[~np.isnan(a)]
        if len(a) == 0:
            continue
        atr_med = float(np.median(a))                      # 价格单位
        pip = cfg['pip']
        sl_price = atr_med * cfg.get('sl_mult', 0.5)
        sl_pips = sl_price / pip
        pip_usd = cfg.get('pip_usd') or 0.0
        v_min = cfg.get('vol_min', 0.01)
        risk_min = sl_pips * pip_usd * v_min               # 最小手风险 $
        pct = risk_min / eq * 100 if eq else 999
        # 理想手数 (1% 风险) 与最小手对比
        ideal = (eq * 0.01) / (sl_pips * pip_usd) if sl_pips * pip_usd > 0 else 0
        verdict = "OK" if pct <= 1.0 else ("TIGHT" if pct <= 2.0 else "TOO_BIG")
        # 需要多少本金才能把它降到 1% 风险
        need_cap = risk_min * 100
        rows.append({
            'sym': sym, 'cls': cfg['cls'], 'name': cfg['name'],
            'atr_h4': atr_med, 'sl_pips': sl_pips, 'pip_usd': pip_usd,
            'v_min': v_min, 'risk_min': risk_min, 'pct': pct,
            'ideal_lot': ideal, 'verdict': verdict, 'need_capital': need_cap,
            'margin_min': cfg.get('margin_min'),
        })

    rows.sort(key=lambda r: r['pct'])
    hdr = (f"{'品种':<10} {'类别':<13} {'H4_ATR':>10} {'SL(pips)':>9} {'每pip$':>9} "
           f"{'最小手':>7} {'最小手风险$':>11} {'占净值%':>8} {'理想手':>8} {'需本金$':>9} 判定")
    print(hdr)
    print("-"*len(hdr.encode('gbk', 'ignore')))
    for r in rows:
        print(f"{r['sym']:<10} {r['cls']:<13} {r['atr_h4']:>10.4f} {r['sl_pips']:>9.1f} "
              f"{r['pip_usd']:>9.3f} {r['v_min']:>7} {r['risk_min']:>11.2f} {r['pct']:>8.2f} "
              f"{r['ideal_lot']:>8.4f} {r['need_capital']:>9.0f} {r['verdict']}")

    ok = [r for r in rows if r['verdict'] == 'OK']
    tight = [r for r in rows if r['verdict'] == 'TIGHT']
    big = [r for r in rows if r['verdict'] == 'TOO_BIG']
    print(f"\n{'='*100}")
    print(f"  汇总 (共 {len(rows)} 个有数据可交易品种):")
    print(f"  OK      可正常按风险定手 : {len(ok):>3}  {', '.join(r['sym'] for r in ok)}")
    print(f"  TIGHT   只能开最小手     : {len(tight):>3}  {', '.join(r['sym'] for r in tight)}")
    print(f"  TOO_BIG 本金不足, 开不起 : {len(big):>3}  {', '.join(r['sym'] for r in big)}")
    if big:
        need = max(r['need_capital'] for r in big)
        print(f"\n  ! 要让全部品种都能按 1% 风险交易, 需本金 ≈ ${need:,.0f}")
        print(f"  ! 当前 ${eq:.0f} 本金下, 建议只交易 OK+TIGHT 的 {len(ok)+len(tight)} 个品种")

    with open(os.path.join(DATA_DIR, "account_capacity.json"), "w", encoding="utf-8") as f:
        json.dump({'account': su.ACCOUNT, 'rows': rows}, f, ensure_ascii=False, indent=1)
    print(f"\n  saved -> data/account_capacity.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
