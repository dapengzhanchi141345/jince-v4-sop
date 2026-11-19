# -*- coding: utf-8 -*-
"""cron wrapper：转跑 金策MFE/MAE追踪（剥离 PYTHONHOME/PYTHONPATH 再 spawn，防 IPC 冻死族 env 污染）。
[11-14 瘦身] 内容闸: stdout 与上次投递内容一致 -> 静默(空输出), 变化才投群; 台账 mfe_last_delivered.json 留痕。
"""
import subprocess, sys, os, hashlib, json

LAST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mfe_last_delivered.json")

def main():
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")}
    r = subprocess.run(
        ["C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/python.exe",
         "E:/GoldstrategyEngine/data/_mfe_mae_track.py"],
        env=env, capture_output=True, text=True, timeout=300,
    )
    out = (r.stdout or "").strip()
    if not out:
        return  # 无持仓/无变化 -> 静默
    try:
        h = hashlib.md5(out.encode("utf-8")).hexdigest()
        last = json.load(open(LAST, encoding="utf-8")) if os.path.exists(LAST) else {}
        if last.get("hash") == h:
            return  # 内容没变 -> 静默(防同日重复刷屏, 台账留痕)
        json.dump({"hash": h, "out": out[:400]}, open(LAST, "w", encoding="utf-8"), ensure_ascii=False)
        sys.stdout.write(out)
    except Exception:
        sys.stdout.write(out)  # 闸自身异常 fail-open: 照投, 不吞消息
    if r.returncode != 0 and "errors.log" not in r.stdout:
        pass  # 失败也静默吞掉（数据在 jsonl，下 30min 快照自愈），不刷群

if __name__ == "__main__":
    main()
