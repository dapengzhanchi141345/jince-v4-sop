# -*- coding: utf-8 -*-
"""金策 通用 ATE 通道结算哨兵（2026-11-05 22:5x 重写版，根治 MetaTrader5 包缺失地雷）。

背景: 旧 no_overnight_close_*.py / kill_switch 全部 `import MetaTrader5` 但本机 (C 盘侧 python)
无该包 = cron 触发即 import 失败 = 静默不动作（22:15 批实测未触发+即便触发也会死）。
根治: 统一走 ATE python (C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe)
+ sys.path.insert(0, E:/GoldstrategyEngine) (该 venv 有 MetaTrader5, 今日 22:2x 实测平 2 仓 retcode 10009)。

用法 (cron no_agent 调 ATE python 直接跑本文件逻辑, 或本文件被 ATE python 执行):
    python jince_ate_close.py --magic 20261105 [--cutoff 1793960400] [--tag usbatch]

行为:
- 平掉 magic 匹配的全部未平仓 (IOC 市价, 重试 3 次/张, 2s 间隔)
- cutoff>0 时只平开仓时间 < cutoff 的仓 (批次区分)
- 全部已平/无仓 = 静默 (watchdog 模式)
- 写日志 E:/GoldstrategyEngine/data/ate_close_log.jsonl
历史回测≠未来收益。
"""
import argparse, json, os, sys, time

# 11-07 凌晨实踩: hermes cron runner 的 venv(numpy 裂) 直接跑本文件会 import 崩(静默无动作)
# 保护: 非 ATE venv 执行时, 自动用 ATE python 重跑自身(参数原样透传, env 剥净)
ATE_PY = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe"
# 11-10 事故修复: Windows 下 os.path.abspath 返回反斜杠, 旧代码用正斜杠 ATE_PY 做 `in` 子串判断
# 永远为 False -> 每次运行都再 spawn 一个子进程 -> 无限自繁殖(11-10 实测 1078 个 python.exe 链)。
# 现: 两侧统一转 os.sep + 小写后再比较; 另加重跑深度保险, 二次仍不匹配就 exit 1 绝不再 spawn。
def _normp(p):
    return p.replace("/", os.sep).lower()
if _normp(ATE_PY) not in _normp(os.path.abspath(sys.executable)):
    import subprocess
    _env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONNOUSERSITE")}
    if _env.get("JINCE_ATE_REEXEC") == "1":
        print("[ate_close] RED: 重跑深度保险触发(二次仍非ATE解释器), 拒绝再spawn, exit 1")
        sys.exit(1)
    _env["JINCE_ATE_REEXEC"] = "1"
    _p = subprocess.run([ATE_PY, os.path.abspath(__file__)] + sys.argv[1:], env=_env)
    sys.exit(_p.returncode)

sys.path.insert(0, r"E:/GoldstrategyEngine")
LOG = r"E:/GoldstrategyEngine/data/ate_close_log.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--magic", type=int, required=True)
    ap.add_argument("--cutoff", type=int, default=0)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    import MetaTrader5 as mt5
    if not mt5.initialize(timeout=15000):
        print("[ate_close] MT5 initialize 失败: %s" % (mt5.last_error(),))
        sys.exit(1)

    pos = mt5.positions_get() or []
    closed, skipped, fail = 0, 0, 0
    slippages = []  # CR-1106强平优化②回修: 滑点=成交价-请求价(bps, 逐单dict含ticket/symbol/volume), 供研发标定滑点上限闸
    failed_details = []  # CR-1106强平优化③: 失败明细(ticket/symbol), 便于人工介入
    for p in pos:
        if p.magic != args.magic:
            continue
        if args.cutoff and p.time >= args.cutoff:
            skipped += 1
            continue
        sym = p.symbol
        tick = mt5.symbol_info_tick(sym)
        # 平方向: 持仓 BUY → SELL, 持仓 SELL → BUY
        ot = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        px = tick.ask if ot == mt5.ORDER_TYPE_SELL else tick.bid
        ok = False
        for attempt in range(3):
            r = mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": p.volume,
                "type": ot, "position": p.ticket, "price": px,
                "deviation": 20, "magic": p.magic, "comment": "JINCE-ATECLOSE-" + args.tag,
                "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
            })
            if r and r.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_DONE_PARTIAL, mt5.TRADE_RETCODE_PLACED):
                closed += 1
                ok = True
                if r and r.price and px > 0:
                    slip = round(abs(r.price - px) / px * 10000, 1)
                else:
                    slip = None
                slippages.append({"ticket": p.ticket, "symbol": sym, "volume": p.volume, "slippage_bps": slip})
                break
            time.sleep(2)
        if not ok:
            fail += 1  # CR-1106强平优化③: 失败计数, 触发 exit1 让 cron 失败报警投群
            failed_details.append({"ticket": p.ticket, "symbol": sym})
            print("[ate_close] 平失败: %s t%s (3次重试后)" % (sym, p.ticket))
    mt5.shutdown()

    entry = {"ts": int(time.time()), "magic": args.magic, "cutoff": args.cutoff, "tag": args.tag,
             "closed": closed, "exempt": skipped, "failed": fail,
             "slippage_bps": slippages, "failed_details": failed_details}
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    if closed or skipped:
        print("[ate_close] magic=%d closed=%d exempt=%d" % (args.magic, closed, skipped))
    if fail:
        print("[ate_close] RED: magic=%d 强平失败 %d 张 (3次重试后仍失败, 需人工介入或等下一哨)" % (args.magic, fail))
        sys.exit(1)  # CR-1106强平优化③: 失败置非零退出码, cron 失败报警自动投群, 静默失败根治
    # 无仓/全豁免/全成功 = 静默 (watchdog)


if __name__ == "__main__":
    main()
