import os
os.environ["OPENBLAS_NUM_THREADS"]="1"
import numpy as np, importlib.util
spec=importlib.util.spec_from_file_location("f2","E:/GoldstrategyEngine/_night_族2区间反转.py")
f2=importlib.util.module_from_spec(spec); spec.loader.exec_module(f2)
d=np.load('E:/GoldstrategyEngine/data/tf_cache/BTCUSD_M30.npz')
h=d['h'].astype(float);l=d['l'].astype(float);c=d['c'].astype(float)
print(f2.adx14.__doc__[:40] if f2.adx14.__doc__ else 'no doc')
import inspect
print(inspect.getsource(f2.adx14)[:800])
print('pdm[:30]', f2.pdm[:30] if hasattr(f2,'pdm') else 'n/a')
AD=f2.adx14(h,l,c)
v=AD[~np.isnan(AD)]
print('n_adx',len(v))
