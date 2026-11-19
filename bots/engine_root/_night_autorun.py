# -*- coding: utf-8 -*-
"""夜间自动续跑循环: 每 10 分钟一轮, 做 3 件不重复的事
1) 按 _tf_m30.py 原版几何重测 fam4 (吊灯E1) → 若 P4 复现≈-0.813 过闸则出可信出场协议数字
2) 协调中枢 dept_hub 刷新
3) meta_evolver 实盘证据扫描 (30笔复验闸进度)
每轮结果追加 data/night_autorun.log; 全部完成后停止"""
import os, sys, json, time, datetime, subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = "C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
LOG = os.path.join(ROOT, "data", "night_autorun.log")
ENV = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    print(msg)


def run(cmd, tag):
    try:
        r = subprocess.run([PY, cmd], cwd=ROOT, env=ENV, capture_output=True,
                            text=True, timeout=1500)
        log(f"{tag}: exit={r.returncode} tail={r.stdout.strip()[-300:] or r.stderr.strip()[-300:]}")
        return r.returncode == 0
    except Exception as e:
        log(f"{tag}: EXCEPTION {e}")
        return False


if __name__ == "__main__":
    log("=== 夜间自动循环启动 ===")
    for round_ in range(1, 4):
        log(f"--- round {round_} ---")
        ok1 = run("_night_fam4_m30_exit_v2.py", "fam4重测(原版几何)")
        run("multi_agent/research/dept_hub.py", "dept_hub刷新")
        # meta_evolver 证据进度: 只读数据, 不改live
        led = json.load(open(os.path.join(ROOT, "data", "rd_ledger.json"), encoding="utf-8"))
        log(f"台账累计 {len(led.get('entries', []))} 条裁决")
        if ok1:
            log("fam4 重测过闸, 停循环")
            break
        time.sleep(600)
    log("=== 夜间自动循环结束 ===")
