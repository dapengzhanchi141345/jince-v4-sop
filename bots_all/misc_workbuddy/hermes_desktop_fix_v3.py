# -*- coding: utf-8 -*-
"""
Hermes 桌面修复启动器 v4
相比 v3 的关键升级：启动前连**孤儿网关**一起杀掉，确保桌面拉起的是自己拥有的新网关
（boot ID 匹配 -> native-http 票据永不失效 -> 根除反复 401）。

流程：
1. 杀掉所有 Hermes.exe（桌面）
2. 杀掉孤儿网关（读 gateway_state.json 的 pid；并用 wmic 兜底查杀所有跑 'gateway run' 的 python）
3. 备份并完整清空 Electron 前端 userData (Roaming\hermes)，仅保留登录态与偏好
4. 从规范路径 E:/hb 启动桌面（asar 硬编码 E:/hb，桌面快捷方式亦指向此）
5. 常驻父进程 keepalive：每 20s 自检，Hermes 掉线即重拉（解决命令行 Popen 父退子死）
"""
import os, sys, time, subprocess, shutil, datetime, json, glob

EXE = r'E:/hb/hermes-agent/apps/desktop/release/win-unpacked/Hermes.exe'
CWD = r'E:/hb/hermes-agent/apps/desktop/release/win-unpacked'
FRONTEND = r'C:\Users\Administrator\AppData\Roaming\hermes'
KEEP = {'Preferences', 'secure-token-storage.json'}
KEEP_PREFIX = ('en-US',)

STATE_CANDIDATES = [
    r'E:/hb/gateway_state.json',
    r'E:\workbuddy\国外模型\hermes\gateway_state.json',
]

def log(msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, encoding='gbk', errors='ignore', timeout=30)
    except Exception as e:
        return None

def kill_hermes():
    _run(['taskkill.exe', '/F', '/IM', 'Hermes.exe'])
    log("已 taskkill Hermes.exe")

def kill_orphan_gateway():
    pids = set()
    # 1) 从 gateway_state.json 读 pid
    for c in STATE_CANDIDATES:
        try:
            d = json.load(open(c, encoding='utf-8', errors='ignore'))
            pid = d.get('pid')
            if isinstance(pid, int) and pid > 0:
                pids.add(pid)
        except Exception:
            pass
    # 2) wmic 兜底：查所有 python 进程中命令行含 'gateway run' 的
    try:
        r = _run(['wmic.exe', 'process', 'where',
                  "name='python.exe' and commandline like '%gateway run%'",
                  'get', 'processid', '/format:csv'])
        if r and r.stdout:
            for line in r.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.add(int(line))
    except Exception:
        pass
    # 3) 也查 pythonw
    try:
        r = _run(['wmic.exe', 'process', 'where',
                  "name='pythonw.exe' and commandline like '%gateway run%'",
                  'get', 'processid', '/format:csv'])
        if r and r.stdout:
            for line in r.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.add(int(line))
    except Exception:
        pass
    if not pids:
        log("未发现孤儿网关 pid")
        return
    for pid in pids:
        _run(['taskkill.exe', '/F', '/PID', str(pid)])
        log(f"已 taskkill 网关 pid {pid}")
    time.sleep(2)

def clear_frontend():
    if not os.path.isdir(FRONTEND):
        log("Roaming\\hermes 不存在，跳过清理")
        return
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = FRONTEND + f'.bak-frontend-{stamp}'
    try:
        shutil.move(FRONTEND, backup)
        log(f"前端整体已备份 -> {backup}")
    except Exception as e:
        log(f"备份移动失败(尝试直接清理): {e}")
        backup = None
    os.makedirs(FRONTEND, exist_ok=True)
    if backup:
        for name in KEEP:
            src = os.path.join(backup, name)
            if os.path.exists(src):
                if os.path.isdir(src):
                    shutil.copytree(src, os.path.join(FRONTEND, name))
                else:
                    shutil.copy2(src, os.path.join(FRONTEND, name))
                log(f"  保留: {name}")
        for name in os.listdir(backup):
            if name.startswith(KEEP_PREFIX) and name.endswith('.bdic'):
                shutil.copy2(os.path.join(backup, name), os.path.join(FRONTEND, name))

def count_hermes():
    r = _run(['tasklist.exe', '/FI', 'IMAGENAME eq Hermes.exe'])
    if not r:
        return 0
    return len([l for l in r.stdout.splitlines() if 'Hermes.exe' in l])

def launch():
    try:
        subprocess.Popen([EXE], cwd=CWD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("已 Popen 启动 Hermes.exe (CWD=E:/hb/...)")
    except Exception as e:
        log(f"启动失败: {e}")

def main():
    log("=== Hermes 桌面修复启动器 v4 开始（根除 401：杀孤儿网关 + 清前端 + 规范路径启动）===")
    kill_hermes()
    time.sleep(2)
    kill_orphan_gateway()
    clear_frontend()
    launch()
    log("进入 keepalive 循环（每 20s 自检）...")
    while True:
        time.sleep(20)
        n = count_hermes()
        if n <= 0:
            log("检测到 Hermes 掉线，重新拉起...")
            kill_orphan_gateway()  # 保险：重拉前也清孤儿网关
            clear_frontend()
            launch()
        else:
            if int(time.time()) % 300 < 20:
                log(f"存活进程数: {n}")

if __name__ == '__main__':
    main()
