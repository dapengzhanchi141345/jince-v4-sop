#!/usr/bin/env python
# 248 冒烟测试: 只跑前 5 个品种, 验证 对象->名字 bug 修复 + gen_pasd 出信号 + 3 桶出数
import os, sys, json, datetime
os.chdir(r"E:\GoldstrategyEngine"); sys.path.insert(0, r"E:\GoldstrategyEngine")
import MetaTrader5 as mt5, symbol_universe as su, backtest_engine as BE, pasd_fusion as PF
import importlib.util
spec=importlib.util.spec_from_file_location('a248','E:/GoldstrategyEngine/all248_3bucket.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
mt5.initialize(); import mt5_login; ok,w=mt5_login.ensure_login(60137964)
print('login =',ok,w)
all_syms=[s for s in mt5.symbols_get('*') if s.select]
test=[s.name for s in all_syms[:5]]
print('冒烟 5 品种 =',test)
MAXH=BE.MAX_HOLD_H1
for sym in test:
    info=mt5.symbol_info(sym)
    if info is None:print(f'  {sym}: symbol_info None');continue
    sp=info.spread or 0;pt=info.point or 1e-5;swl=info.swap_long or 0;swh=info.swap_short or 0
    h1=m.rates(sym,mt5.TIMEFRAME_H1,mins=200)
    if h1 is None:print(f'  {sym}: H1 短');continue
    h4=m.rates(sym,mt5.TIMEFRAME_H4,mins=60)
    d1=m.rates(sym,mt5.TIMEFRAME_D1,d=365,mins=30)
    cfg=su.UNIVERSE.get(sym,{'spread':sp});pvp=m.pipval(sym,cfg,info)
    try: sigs=PF.gen_pasd(h1,h4,d1,cfg)
    except Exception as e: print(f'  {sym}: gen_pasd 崩 {e}');continue
    for s in sigs: s['tp']=s['entry']+s['side']*m.RR*abs(s['entry']-s['sl'])
    sips=[abs(s['entry']-s['sl'])/pt for s in sigs]
    kept=[s for s,d in zip(sigs,sips) if m.GUARD_PIP_MIN<=d<=m.GUARD_PIP_MAX]
    print(f'  {sym}: H1={len(h1)} 总信号={len(sigs)} 护栏后={len(kept)} pvp={pvp}')
print('冒烟完成')
mt5.shutdown()
