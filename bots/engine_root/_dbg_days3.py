# -*- coding: utf-8 -*-
import numpy as np
z = np.load("data/tf_cache_fx2/EURUSD_M30.npz")
t = z["t"].astype(np.int64)
b_py = 1759708800
print("python int boundary:", ((t >= b_py) & (t < b_py + 86400)).sum())
b_np = np.int64(1759708800)
print("np.int64 boundary:", ((t >= b_np) & (t < b_np + np.int64(86400))).sum())
val = 1759708800 * 86400
print("1759708800*86400 =", val, "exceeds int64 max?", val > 9223372036854775807)
