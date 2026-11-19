# 临时计时探针: 逐个 probe 打点写文件, 定位 60s 到底吃在哪(用完即删)
import time, importlib.util, sys, os
spec = importlib.util.spec_from_file_location('rg', r'E:/GoldstrategyEngine/risk_network_gate.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
out = []
out.append("import_module=%.2fs" % (time.time()-time.time()))  # placeholder
def cap(label, fn, *a, **k):
    t0 = time.time(); r = fn(*a, **k); out.append("%s=%s %.1fs" % (label, r, time.time()-t0))
    return r
# 重新计时起点
t0 = time.time()
import importlib.util as _iu
spec2 = _iu.spec_from_file_location('rg2', r'E:/GoldstrategyEngine/risk_network_gate.py')
m = _iu.module_from_spec(spec2); spec2.loader.exec_module(m)
out.insert(0, "import_module=%.1fs" % (time.time()-t0))
cap("probe_mt5", m.probe_mt5, 10)
cap("probe_external", m.probe_external)
cap("probe_github", m.probe_github)
cap("probe_dst_freeze", m.probe_dst_freeze)
out.append("total=%.1fs" % (time.time()-(t0)))
open(r'E:/GoldstrategyEngine/data/_probe_timing.txt','w').write("\n".join(out))
print("\n".join(out))
os._exit(0)
