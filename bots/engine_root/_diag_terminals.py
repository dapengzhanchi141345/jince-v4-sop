# -*- coding: utf-8 -*-
"""只读全景诊断: 不 spawn 不 kill, 把 3 类终端(引擎默认/friend_observer/guest)
各自的 IPC 状态、登的账号、引擎健康一次看清。所有 initialize 带短超时, 绝不 hang。
输出全部 flush, 绝不静默。
"""
import MetaTrader5 as mt5, os, subprocess, time, datetime

def flush_print(*a):
    print(*a, flush=True)

def try_attach(datafolder, label, timeout=12000):
    """带超时 attach, 明确报 IPC 状态。绝不 hang。"""
    args = {"timeout": timeout}
    if datafolder:
        args["data_folder"] = datafolder
    r = mt5.initialize(**args)
    err = mt5.last_error()
    if not r:
        flush_print(f"  [{label}] initialize=False (IPC 未通) err={err}")
        mt5.shutdown()
        return None
    a = mt5.account_info()
    if a is None:
        flush_print(f"  [{label}] initialize=True 但 account_info=None (终端在忙/登录中) err={err}")
        mt5.shutdown()
        return {"connected": True, "login": None}
    mt5.shutdown()
    return {"connected": True, "login": a.login, "server": a.server,
            "balance": a.balance, "equity": a.equity, "leverage": a.leverage}

flush_print("═══ ① 所有 terminal64 实例(启动时间+datafolder, 判断谁是我起的) ═══")
try:
    out = subprocess.run(
        ["wmic", "process", "where", "name='terminal64.exe'", "get", "ProcessId,CommandLine,CreationDate"],
        capture_output=True, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    for line in out.splitlines():
        if "terminal64.exe" in line:
            flush_print("  " + line.strip()[:150])
except Exception as e:
    flush_print(f"  wmic 读失败: {e}")

flush_print("")
flush_print("═══ ② 各数据目录 最近日志(判断哪个终端真连了 EC Markets) ═══")
for df in [r"C:\Program Files\TMGM MT5 Terminal", r"E:\mt5_friend_observer", r"E:\GoldstrategyEngine\_guest_mt5"]:
    logdir = os.path.join(df, "logs")
    try:
        logs = sorted([f for f in os.listdir(logdir) if f.endswith(".log")])
        recent = [f for f in logs if f.startswith("2026")]
        # 找最新的交易日志
        daylogs = [f for f in logs if f[:4].isdigit() and len(f) == 10]
        newest = daylogs[-1] if daylogs else (logs[-1] if logs else "无")
        size = os.path.getsize(os.path.join(logdir, newest)) if newest != "无" else 0
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(logdir, newest))) if newest != "无" else None
        flush_print(f"  {df}: 最新日志={newest} {size}B 更新于{mtime}")
    except Exception as e:
        flush_print(f"  {df}: 无日志目录 ({str(e)[:30]})")

flush_print("")
flush_print("═══ ③ 各终端 IPC 实测(带 12s 超时, 绝不 hang) ═══")
flush_print("  [引擎默认 C:\\Program Files\\TMGM]")
print_try = try_attach(None, "引擎默认")
if print_try and print_try.get("login"):
    flush_print(f"    已连: {print_try['login']} / {print_try['server']} | 余额 {print_try['balance']}")
flush_print("  [friend_observer E:\\mt5_friend_observer]")
print_try2 = try_attach(r"E:\mt5_friend_observer", "friend_observer")
if print_try2 and print_try2.get("login"):
    flush_print(f"    已连: {print_try2['login']} / {print_try2['server']} | 余额 {print_try2['balance']}")

flush_print("")
flush_print("═══ ④ 引擎全链健康(引擎靠默认终端跑) ═══")
log = r"E:\GoldstrategyEngine\data\auto_cycle.log"
try:
    with open(log, encoding="utf-8", errors="replace") as f:
        lines = [l for l in f.readlines() if "[全链自动运行完成]" in l]
    flush_print(f"  最近全链完成: {lines[-1].strip()[:40] if lines else '读不出'}")
    flush_print(f"  现在: {datetime.datetime.now().strftime('%H:%M')}")
except Exception as e:
    flush_print(f"  读日志失败: {e}")
flush_print("诊断完成")
