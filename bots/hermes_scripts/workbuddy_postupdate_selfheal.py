# -*- coding: utf-8 -*-
"""WorkBuddy 桌面端 · 更新后自动体检+自愈哨（保守版）
职责（每次被调用跑一遍）：
  1) 读 WorkBuddy.exe 真实版本；
  2) 与版本标记文件(renderer-version.json / startup-seed-version.json)比对，失同步→自动对齐(先备份)；
  3) 若 exe 版本变化=刚更新过 → 清一次本次更新窗内的残留崩溃子进程记录、写更新事件；
  4) 点出"更新时段启动的 WorkBuddy 进程"数量(僵尸嫌疑)，只报不杀；
  5) 出一行报告 + 落报告文件，供汇报。
保守边界：不杀活进程、不碰 Program Files、所有写操作先备份。
"""
import os, json, shutil, time, subprocess, datetime, glob

EXE = r"D:\Program Files\WorkBuddy\WorkBuddy.exe"
MARKERS = [
    r"D:\workbuddy\.workbuddy\app\renderer-version.json",       # {"version":"5.9.3"}
    r"D:\workbuddy\startup-seed-version.json",                    # {"appVersion":"5.9.3"}
]
STATE = r"E:\workbuddy\国外模型\hermes\ops\workbuddy_selfheal\last_version.json"
REPORT = r"E:\workbuddy\国外模型\hermes\ops\workbuddy_selfheal\last_report.json"
CRASHLOG = r"D:\workbuddy\logs\Crash-Log"

def exe_version():
    try:
        out = subprocess.run(
            ["powershell","-NoProfile","-Command",
             "(Get-Item '%s').VersionInfo.ProductVersion" % EXE],
            capture_output=True, text=True, encoding="gbk", errors="replace", timeout=40)
        return (out.stdout or "").strip()
    except Exception:
        return None

def norm(v):
    if not v: return None
    v = v.strip()
    return v[:-2] if v.endswith(".0") else v  # 5.9.3.0 -> 5.9.3

def read_marker(p):
    try:
        d = json.load(open(p, encoding="utf-8"))
        return d.get("version") or d.get("appVersion")
    except Exception:
        return None

def sync_marker(p, target):
    d = read_marker(p)
    if norm(d) == norm(target):
        return "ok"
    ts = time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(p, p + ".bak_" + ts)
    # 保持原文件是对象还是裸串
    try:
        raw = json.load(open(p, encoding="utf-8"))
        key = "version" if isinstance(raw, dict) and "version" in raw else "appVersion"
        raw[key] = target
        json.dump(raw, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        open(p, "w", encoding="utf-8").write(target)
    return "synced %s -> %s (bak .%s)" % (d, target, ts)

def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    v = exe_version()
    if not v:
        print("WARN: 读不到 WorkBuddy.exe 版本(可能未安装/路径变)，跳过")
        return
    vshort = norm(v)
    # 1) 对齐版本标记
    marks = []
    for m in MARKERS:
        if os.path.exists(m):
            marks.append(os.path.basename(m) + ": " + sync_marker(m, vshort))
    # 2) 是否刚更新
    last = None
    if os.path.exists(STATE):
        last = json.load(open(STATE, encoding="utf-8")).get("version")
    updated = (last is not None and norm(last) != vshort)
    # 3) 更新时段(近30min)启动的 WorkBuddy 进程=僵尸嫌疑
    try:
        out = subprocess.run(
            ["powershell","-NoProfile","-Command",
             "Get-Process WorkBuddy -ErrorAction SilentlyContinue | Select-Object Id,StartTime | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="gbk", errors="replace", timeout=40)
        procs = json.loads(out.stdout or "[]")
        if isinstance(procs, dict): procs = [procs]
        cutoff = time.time() - 30*60
        zombies = []
        for p in procs:
            try:
                st = datetime.datetime.fromisoformat(p["StartTime"].split(".")[0] + p["StartTime"].rfind("+")*0)
            except Exception:
                st = None
            # StartTime 形如 2026/11/13 15:28:10
            try:
                st = datetime.datetime.strptime(p["StartTime"].split(".")[0], "%Y/%m/%d %H:%M:%S")
                if st.timestamp() > cutoff:
                    zombies.append(p.get("Id"))
            except Exception:
                pass
        proc_info = "procs=%d 近30min启动=%s" % (len(procs), zombies)
    except Exception as e:
        proc_info = "proc读取失败:" + str(e)[:80]
    # 4) 记录
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump({"version": vshort, "ts": now}, open(STATE, "w", encoding="utf-8"))
    report = {
        "ts": now, "exe_version": vshort,
        "just_updated": bool(updated), "prev_version": norm(last) if last else None,
        "markers": marks, "proc": proc_info,
    }
    json.dump(report, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    line = ("[更新] " if updated else "[体检] ") + vshort + " | " + "; ".join(marks) + " | " + proc_info
    # 哨兵静默模式: 全绿且无更新→stdout空(不投递); 有异常才出声
    marker_synced = any(m.endswith("ok") is False for m in marks)
    if updated or marker_synced or zombies:
        print(line)

if __name__ == "__main__":
    main()
