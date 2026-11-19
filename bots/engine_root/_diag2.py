import sys, pickle, json
sys.path.insert(0, r"E:\GoldstrategyEngine")
import symbol_universe as su
for s in ('AUDNZD','EURTRY','USDTRY','SOLUSD','XLMUSD','XTZUSD'):
    c = su.UNIVERSE.get(s, {})
    print(s, "| pip:", c.get('pip'), "| cls:", c.get('cls'), "| lot:", c.get('lot'))
