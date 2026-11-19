# -*- coding: utf-8 -*-
# 只读: 验 magic 过滤行为 + mt5_live_read.live_read() 返回结构
import MetaTrader5 as mt5, json, sys
PATH=r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
ok=mt5.initialize(PATH)
a=len(mt5.positions_get(magic=20260902) or [])
b=len(mt5.positions_get(magic=99999999) or [])   # 不存在的magic
c=len(mt5.positions_get() or [])
print("magic=20260902 -> %d | magic=99999999 -> %d | 无过滤 -> %d" % (a,b,c))
print("=> 过滤生效" if (b==0 and c==5) else "=> 过滤未生效(全量返回, magic参数被忽略)!")
mt5.shutdown()
