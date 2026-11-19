# 网络换网自适应哨(李彦明11-08令: 我天天换网, 系统要自适应, 零人工)
# 每30min: ①读出口IP(换网检测) ②读BTC tm(桥状态) ③出口变=自动重登终端(桥LB重分配) ④tm=1=自动开4腿+报群 ⑤全留痕 bridge_adapt_log.jsonl
import subprocess, os, json, datetime, time, urllib.request
ATE = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe"
LOG = "E:/GoldstrategyEngine/data/bridge_adapt_log.jsonl"
ST = "E:/GoldstrategyEngine/data/bridge_adapt_state.json"

def log(rec):
    rec["ts"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def egress_ip():
    try:
        with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=8) as r:
            return json.loads(r.read()).get("ip", "")
    except Exception:
        return ""

def mt5_read():
    code = (
        "import MetaTrader5 as mt5\n"
        "if not mt5.initialize(): print('OFFLINE'); raise SystemExit\n"
        "tm=[mt5.symbol_info(s).trade_mode for s in ['BTCUSD','ETHUSD']]\n"
        "pos=len([p for p in (mt5.positions_get() or []) if p.magic==30261106])\n"
        "print('TM:', ','.join(str(t) for t in tm), 'POS:', pos)\n"
    )
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE")}
    r = subprocess.run([ATE, "-c", code], capture_output=True, text=True, timeout=45, env=env)
    line = (r.stdout or "").strip().splitlines()[-1] if r.stdout else ""
    if "OFFLINE" in line or not line:
        return "OFFLINE", 0
    tms = line.split("TM:")[1].split("POS:")[0].split(",") if "TM:" in line else []
    pos = int(line.split("POS:")[1]) if "POS:" in line else 0
    tm = min(int(t) for t in tms) if tms else -1
    return ("TM1" if any(int(t) == 1 for t in tms) else "TM4"), pos

def relogin_terminal():
    # 终端零参数干净重启(铁律: 任何参数=API握手毁)
    subprocess.run("taskkill /F /IM terminal64.exe", shell=True, capture_output=True, timeout=30)
    time.sleep(5)
    subprocess.run('start "" "C:\\Program Files\\TMGM MT5 Terminal\\terminal64.exe"', shell=True, timeout=30)
    time.sleep(55)

def open4legs():
    # 4腿0.01样本单(与 selfheal 链同口径)
    code = (
        "import MetaTrader5 as mt5, json, datetime\n"
        "if not mt5.initialize(): print('OPEN:OFFLINE'); raise SystemExit\n"
        "MAGIC=30261106; LC='E:/GoldstrategyEngine/data/order_lifecycle.jsonl'\n"
        "POOL=[('BTCUSD',2,0.005,0.015),('ETHUSD',2,0.005,0.015),('SOLUSD',1,0.008,0.020),('ADAUSD',1,0.008,0.020)]\n"
        "held={p.symbol for p in (mt5.positions_get() or []) if p.magic==MAGIC}\n"
        "opened=[]\n"
        "for sym,side,slp,tpp in POOL:\n"
        "    if sym in held: continue\n"
        "    si=mt5.symbol_info(sym)\n"
        "    if not si or si.trade_mode!=1: continue\n"
        "    px=si.bid if side==2 else si.ask\n"
        "    sl=round(px*(1+slp),si.digits) if side==2 else round(px*(1-slp),si.digits)\n"
        "    tp=round(px*(1+tpp),si.digits) if side==1 else round(px*(1-tpp),si.digits)\n"
        "    r=mt5.order_send({'action':mt5.TRADE_ACTION_DEAL,'symbol':sym,'volume':0.01,\n"
        "        'type':mt5.ORDER_TYPE_SELL if side==2 else mt5.ORDER_TYPE_BUY,'price':px,'sl':sl,'tp':tp,\n"
        "        'deviation':20,'magic':MAGIC,'comment':'adapt4_%s'%sym[:3],'type_time':mt5.ORDER_TIME_GTC,'type_filling':mt5.ORDER_FILLING_IOC})\n"
        "    if r.retcode in (10008,10009,10010):\n"
        "        opened.append(sym)\n"
        "        open(LC,'a',encoding='utf-8').write(json.dumps({'ts':datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),'sym':sym,\n"
        "            'side':'SELL' if side==2 else 'BUY','vol':0.01,'magic':MAGIC,'open_px':px,'sl':sl,'tp':tp,'retcode':r.retcode,\n"
        "            'deal':r.deal,'close_due':'开仓+12h(6h循环哨自动平+再轮换)','sentinel':'bridge_adapt(换网自适应)','status':'open',\n"
        "            'note':'换网自适应闭环: 出口变化->重登->活桥命中->自动开4腿'},ensure_ascii=False)+'\\n')\n"
        "print('OPEN:', ','.join(opened) if opened else 'NONE')\n"
    )
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE")}
    r = subprocess.run([ATE, "-c", code], capture_output=True, text=True, timeout=90, env=env)
    out = (r.stdout or "").strip().splitlines()
    return out[-1] if out else "OPEN:EMPTY"

def main():
    st = {}
    if os.path.exists(ST):
        try: st = json.load(open(ST, encoding="utf-8"))
        except Exception: st = {}
    eip = egress_ip()
    state, pos = mt5_read()
    out = []
    # 1) 换网检测: 出口IP变了 -> 自动重登(桥LB按新出口重分配) -> 再读tm
    if st.get("egress") and eip and st["egress"] != eip:
        log({"event": "EGRESS_CHANGED", "old": st["egress"], "new": eip, "note": "换网检测: 自动重登终端, 桥LB将按新出口重分配"})
        relogin_terminal()
        state, pos = mt5_read()
    # 2) tm=1 且 0在仓 -> 自动开4腿
    if state == "TM1" and pos == 0:
        out.append("【换网自适应】桥已活(tm=1), 0在仓 -> 自动开4腿0.01样本单:")
        res = open4legs()
        out.append(res)
        log({"event": "OPENED_4LEGS", "detail": res, "egress": eip})
    # 3) 仍 tm=4 -> 留痕, 不刷屏(等下次换网/博德放开; 5min selfheal链并行盯着)
    elif state == "TM4" and not out:
        pass  # 静默(watchdog 模式)
    # 4) 状态落盘
    st["egress"] = eip
    st["state"] = state
    json.dump(st, open(ST, "w", encoding="utf-8"))
    if out:
        print("\n".join(out))
    # 全静默 = 出口未变且桥仍关/已在仓 -> 无输出(不刷屏)

if __name__ == "__main__":
    main()
