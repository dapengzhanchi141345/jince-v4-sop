# -*- coding: utf-8 -*-
"""jince_sentinel_health.py — 执行哨预发射体检(李令11-17'怎么没有执行, 建预防措施'): 30min哨, watchdog静默
查: ①执行层解释器基准=3.13.12(含MT5, 实证); jince venv(numpy断)=禁止执行层用 ②三哨脚本py_compile
③MT5 import冒烟 ④tick feed活性(5s双采样) ⑤包装器解释器grep. 全过=静默; 任一败=出声+P1工单幂等.
"""
import os, re, sys, json, datetime as dt, subprocess, time

P313 = r"D:/workbuddy/binaries/python/versions/3.13.12/python.exe"
ROOT = "E:/GoldstrategyEngine"
WRAP = r"E:/workbuddy/国外模型/hermes/scripts"
SENTINELS = {
    "BTC": f"{ROOT}/soul_wave_market_in_1117.py",
    "ETH": f"{ROOT}/slv2_eth_market_in_1117.py",
    "SOL": f"{ROOT}/slv2_sol_market_in_1117.py",
}
Q = f"{ROOT}/data/rd_queue.json"


def _resolve(path):
    # 11-17 三哨被有意停用(改名 data/disabled_*.py.disabled): 原路径失时落 disabled 变体, 皆无=None(跳过编译)
    if os.path.exists(path):
        return path
    alt = f"{ROOT}/data/disabled_{os.path.basename(path)}.disabled"
    return alt if os.path.exists(alt) else None

def main():
    issues = []
    # ② py_compile (停用的哨=编译其disabled变体, 原路径失+无变体=跳过不计败)
    targets = [_resolve(p) for p in SENTINELS.values()]
    targets = [t for t in targets if t]
    if len(targets) < len(SENTINELS):
        print(f"[执行哨体检] 提示: {len(SENTINELS)-len(targets)}个哨脚本停用/缺失(有意停用不计败, 留痕于参数官const_state)")
    if targets:
        r = subprocess.run([P313, "-m", "py_compile", *targets], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            issues.append(f"哨脚本编译败: {r.stderr[-200:]}")
    # ①③ 解释器基准: 3.13.12 含 MT5 + import 冒烟
    r = subprocess.run([P313, "-c", "import MetaTrader5 as m; assert m.initialize(); m.shutdown()"],
                       capture_output=True, text=True, timeout=90)
    if r.returncode != 0:
        issues.append(f"3.13.12 MT5冒烟败: {r.stderr[-150:]}")
    # ⑤ 包装器解释器 grep (禁 jince venv)
    for f in os.listdir(WRAP):
        if f.endswith("_wrapper.py") and re.search(r"soul|slv2", f):
            txt = open(os.path.join(WRAP, f), encoding="utf-8").read()
            if "jince_sass" in txt:
                issues.append(f"包装器{f}用了jince venv(numpy断), 须=3.13.12")
    # ④ feed活性
    try:
        r = subprocess.run([P313, "-c",
            "import MetaTrader5 as m,time,sys\nm.initialize()\nt=m.symbol_info_tick('BTCUSD');a=t.time if t else 0\ntime.sleep(5)\nt2=m.symbol_info_tick('BTCUSD')\nprint('ok' if (t2 and t2.time>a) else 'stale')\nm.shutdown()"],
            capture_output=True, text=True, timeout=120)
        if "ok" not in r.stdout:
            issues.append(f"BTC feed不活({r.stdout.strip() or r.stderr[-100:]})")
    except Exception as e:
        issues.append(f"feed体检异常 {e}")
    # 工单幂等
    if issues:
        q = json.load(open(Q, encoding="utf-8"))
        tid = "sentinel_health_" + dt.datetime.now().strftime("%Y%m%d%H")
        if tid not in q:
            q[tid] = {"id": tid, "sev": "P1", "status": "queued", "by": "sentinel-health", "ts": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                      "task": " | ".join(issues[:4]), "owner_matrix": "解释器基准/脚本=执行岗; venv修复=数据岗; 裁定=chief"}
            json.dump(q, open(Q, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"[执行哨体检] 败{len(issues)}项: " + " | ".join(issues[:5]))
    # 全过=静默(watchdog)


if __name__ == "__main__":
    main()
