# 开单通道自修复链 (李彦明11-08铁律: 开不了单=我方问题, 立即检测修复优化, 不归因平台)
# 流程: 检测(tm/拒单) -> 强刷symbol -> 终端零参数重登 -> 重读 -> 重试开单 -> 全程留痕 repair_log.jsonl
# no_agent watchdog 用法: 输出=动作结果; 空输出=通道正常无需动作
import subprocess, os, sys, json, datetime, time
ATE = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe"
TERM = r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = "E:/GoldstrategyEngine/data/repair_log.jsonl"

def _log(step, detail):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "step": step, "detail": detail}, ensure_ascii=False) + "\n")
    except Exception:
        pass

def _term_alive():
    import subprocess as sp
    r = sp.run("tasklist /FI \"IMAGENAME eq terminal64.exe\" /NH", capture_output=True, text=True, timeout=20)
    return "terminal64" in (r.stdout or "")

def _relogin():
    # 终端零参数干净重启(铁律: 任何参数都会毁API握手=10013)
    import subprocess as sp
    sp.run("taskkill /F /IM terminal64.exe", capture_output=True, timeout=20, shell=True)
    time.sleep(5)
    sp.run('start "" "C:\\Program Files\\TMGM MT5 Terminal\\terminal64.exe"', shell=True, timeout=20)
    time.sleep(50)  # 等登录同步

def _inner_code(action):
    # action: "probe"=只读tm; "open4"=开4腿轮值池
    return r'''
import MetaTrader5 as mt5
if not mt5.initialize():
    print("RESULT:OFFLINE"); raise SystemExit
tm = [mt5.symbol_info(s).trade_mode for s in ["BTCUSD","ETHUSD","SOLUSD","ADAUSD"]]
pos = len([p for p in (mt5.positions_get() or []) if p.magic == 30261106])
if __import__("os").environ.get("SELFHEAL_ACTION") == "open4":
    if any(t == 1 for t in tm):
        POOL = [("BTCUSD", 2, 0.005, 0.015), ("ETHUSD", 2, 0.005, 0.015),
                ("SOLUSD", 1, 0.008, 0.020), ("ADAUSD", 1, 0.008, 0.020)]
        held = {p.symbol for p in (mt5.positions_get() or []) if p.magic == 30261106}
        import json, datetime
        LC = "E:/GoldstrategyEngine/data/order_lifecycle.jsonl"
        def _lc(rec):
            open(LC, "a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
        opened = []
        for sym, side, slp, tpp in POOL:
            if sym in held: continue
            si = mt5.symbol_info(sym)
            if not si or si.trade_mode != 1: continue
            px = si.bid if side == 2 else si.ask
            sl = round(px * (1 + slp), si.digits) if side == 2 else round(px * (1 - slp), si.digits)
            tp = round(px * (1 + tpp), si.digits) if side == 1 else round(px * (1 - tpp), si.digits)
            r = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": 0.01,
                                "type": mt5.ORDER_TYPE_SELL if side == 2 else mt5.ORDER_TYPE_BUY,
                                "price": px, "sl": sl, "tp": tp, "deviation": 20, "magic": 30261106,
                                "comment": "selfheal_%s" % sym[:3], "type_time": mt5.ORDER_TIME_GTC,
                                "type_filling": mt5.ORDER_FILLING_IOC})
            if r.retcode in (10008, 10009, 10010):
                opened.append(sym)
                _lc({"ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "sym": sym,
                     "side": "SELL" if side == 2 else "BUY", "vol": 0.01, "magic": 30261106,
                     "open_px": px, "sl": sl, "tp": tp, "retcode": r.retcode, "deal": r.deal,
                     "close_due": "开仓+12h(6h循环哨自动平+再轮换)", "sentinel": "selfheal链",
                     "status": "open", "note": "开单通道自修复链重登后开单(李11-08铁律: 拒单=我方问题立即修)"})
        if opened:
            print("RESULT:OPENED " + " ".join(opened)); mt5.shutdown(); raise SystemExit
        print("RESULT:TM1_NO_OPEN (tm=1但开单被拒, 需人工介入字段级检查)"); mt5.shutdown(); raise SystemExit
    print("RESULT:TM4 %s" % ",".join(str(t) for t in tm)); mt5.shutdown(); raise SystemExit
print("RESULT:PROBE tm=%s pos=%d" % (",".join(str(t) for t in tm), pos))
mt5.shutdown()
'''

def run_inner(action):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE")}
    env["SELFHEAL_ACTION"] = action
    r = subprocess.run([ATE, "-c", _inner_code(action)], capture_output=True, text=True,
                       timeout=120, env=env)
    for line in (r.stdout or "").strip().splitlines():
        if line.startswith("RESULT:"):
            return line.split("RESULT:")[1]
    return "EMPTY"

def main():
    # 已在仓: 无需动作
    probe = run_inner("probe")
    if probe.startswith("PROBE") and "pos=" in probe:
        pos = int(probe.split("pos=")[1])
        if pos > 0:
            return  # 静默: 已有腿
    if not _term_alive():
        _log("终端离线->零参数重启", "tasklist无terminal64")
        _relogin()
        probe = run_inner("probe")
    # tm=4: 强刷 -> 仍4则零参数重登 -> 重试开单 (李彦明令: 立即检测修复, 不干等)
    for attempt in (1, 2):
        if "TM4" in probe:
            _log("强刷symbol(第%d次)" % attempt, "tm=4 close-only, 主动刷新不等")
            for s in ("BTCUSD", "ETHUSD", "SOLUSD", "ADAUSD"):
                subprocess.run([ATE, "-c",
                                "import MetaTrader5 as mt5\nmt5.initialize()\n"
                                "mt5.symbol_select('%s', True)\nmt5.shutdown()" % s],
                               capture_output=True, timeout=45)
            probe = run_inner("probe")
            if "TM4" in probe and attempt == 1:
                _log("零参数重登终端", "强刷后仍tm=4, 重握手拿服务器最新状态")
                _relogin()
                probe = run_inner("probe")
        if "TM1" in probe or "PROBE" in probe:
            break
    # 可开单了: 执行4腿开单 (probe 含 TM4 = 仍关, 不开试, 直接通报)
    if "TM4" in probe:
        _log("仍close-only", "重登后博德服务器仍tm=4(状态已同步自服务器, 我方无堵点), 5min后自动再试")
        print("【开单通道自修复】我方通道全自检通过(强刷+零参重登+重读), 博德服务器仍对币系close-only, 5min自动再试, 不静默")
        return
    res = run_inner("open4")
    if res.startswith("OPENED"):
        _log("开单成功", res)
        print("【开单通道自修复】%s" % res)
        return
    if "OFFLINE" in res:
        _log("终端离线", "开单阶段初始化失败, 下轮5min哨重试")
    else:
        _log("开单被拒", res)
        print("【开单通道自修复】tm已=1但开单被拒: %s (已留痕, 下轮5min自动重试+若持续进23:00调试窗)" % res)

if __name__ == "__main__":
    main()
