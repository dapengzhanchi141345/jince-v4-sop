# -*- coding: utf-8 -*-
"""
Hermes 统一监督脚本 v5.1（网关 + 桌面，常驻后台）
- 网关：好 venv (e5c564) + --external-supervisor --replace 启动。
  --replace 接管并清除陈旧"主机所有权"(幽灵网关 31680) -> 根除反复拒启动；
  --external-supervisor 不注册 schtasks(沙箱拦截) -> 由本脚本监督。
- 桌面：规范 E:/hb 路径启动，避免错副本与 401。
- 防狂刷：距上次拉起 >40s 且仍无活 state 才重拉网关。
- 网关重拉后等其注册再重启桌面刷新 native-http 票据(根除 401)。
"""
import os, sys, time, subprocess, shutil, datetime, json

LOG = r'E:/workbuddy/hermes_supervisor.log'

DESKTOP_EXE = r'E:/hb/hermes-agent/apps/desktop/release/win-unpacked/Hermes.exe'
DESKTOP_CWD = r'E:/hb/hermes-agent/apps/desktop/release/win-unpacked'
FRONTEND = r'C:\Users\Administrator\AppData\Roaming\hermes'
KEEP = {'Preferences', 'secure-token-storage.json'}

GW_VENV = r'E:/hb/installs/4ea489dd943be455/environments/e5c564bcc6c6450e926a327c3e00991c/venv/Scripts/python.exe'
GW_MAIN = r'E:\workbuddy\国外模型\hermes\hermes-agent\hermes_cli\main.py'
GW_CWD = r'E:\workbuddy\国外模型\hermes\hermes-agent'
GW_HOME = r'E:\workbuddy\国外模型\hermes'
STATE = r'E:/hb/gateway_state.json'
LOCK = r'E:/hb/gateway.lock'

GW_LAUNCH_LOG = r'E:/workbuddy/gateway_launch.log'
LAST_GW_LAUNCH = 0.0


def log(msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}\n"
    sys.stdout.write(line); sys.stdout.flush()
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, encoding='gbk', errors='ignore', timeout=30)
    except Exception:
        return None


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def state_pid():
    try:
        d = json.load(open(STATE, encoding='utf-8', errors='ignore'))
        pid = d.get('pid')
        return pid if isinstance(pid, int) and pid > 0 else None
    except Exception:
        return None


def kill_hermes():
    run(['taskkill.exe', '/F', '/IM', 'Hermes.exe'])
    log("taskkill Hermes.exe")


def kill_gateway():
    pid = state_pid()
    if pid and pid_alive(pid):
        run(['taskkill.exe', '/F', '/PID', str(pid)])
        log(f"taskkill 网关 pid {pid}")
    else:
        log("网关 pid 不可见/已死，跳过杀")


def clear_frontend():
    if not os.path.isdir(FRONTEND):
        return
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = FRONTEND + f'.bak-frontend-{stamp}'
    try:
        shutil.move(FRONTEND, bak)
        log(f"前端备份 -> {bak}")
    except Exception as e:
        log(f"前端备份失败: {e}")
        bak = None
    os.makedirs(FRONTEND, exist_ok=True)
    if bak:
        for name in KEEP:
            src = os.path.join(bak, name)
            if os.path.exists(src):
                if os.path.isdir(src):
                    shutil.copytree(src, os.path.join(FRONTEND, name))
                else:
                    shutil.copy2(src, os.path.join(FRONTEND, name))
                log(f"  保留: {name}")


def launch_gateway():
    global LAST_GW_LAUNCH
    if not (os.path.exists(GW_VENV) and os.path.exists(GW_MAIN)):
        log("网关 venv/main 缺失，无法启动"); return
    env = dict(os.environ)
    env['HERMES_HOME'] = GW_HOME
    env['PYTHONIOENCODING'] = 'utf-8'
    f = open(GW_LAUNCH_LOG, 'ab', 0)
    try:
        p = subprocess.Popen(
            [GW_VENV, GW_MAIN, 'gateway', 'run', '--quiet', '--external-supervisor', '--replace'],
            cwd=GW_CWD, env=env, stdout=f, stderr=f,
            creationflags=0x00000200 | 0x00000800)
        log(f"Popen 网关 pid={p.pid} (--replace)")
        LAST_GW_LAUNCH = time.time()
    except Exception as e:
        log(f"网关启动失败: {e}")
    finally:
        try:
            f.close()
        except Exception:
            pass


def launch_desktop():
    try:
        subprocess.Popen([DESKTOP_EXE], cwd=DESKTOP_CWD,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=0x00000200 | 0x00000800)
        log("Popen 桌面 Hermes.exe")
    except Exception as e:
        log(f"桌面启动失败: {e}")


def count_hermes():
    r = run(['tasklist.exe', '/FI', 'IMAGENAME eq Hermes.exe'])
    if not r:
        return 0
    return len([l for l in r.stdout.splitlines() if 'Hermes.exe' in l])


def main():
    global LAST_GW_LAUNCH
    log("=== Hermes 统一监督 v5.1 启动 ===")
    kill_hermes()
    time.sleep(2)
    launch_gateway()
    time.sleep(20)  # 等网关接管网关所有权并注册
    clear_frontend()
    launch_desktop()
    log("进入 keepalive 循环（每 20s）...")
    while True:
        time.sleep(20)
        sp = state_pid()
        gw_ok = bool(sp) and pid_alive(sp)
        if not gw_ok:
            if time.time() - LAST_GW_LAUNCH > 40:
                log("网关仍不在/已死(>40s) -> 重拉(--replace)")
                kill_gateway()
                launch_gateway()
                time.sleep(15)
                log("网关已重拉，重启桌面刷新连接")
                kill_hermes()
                time.sleep(2)
                clear_frontend()
                launch_desktop()
            else:
                log("网关未注册但刚拉起不久，再等等")
        else:
            if int(time.time()) % 600 < 20:
                log(f"网关存活 pid={sp}")
            if count_hermes() <= 0:
                log("桌面掉线 -> 重拉（不动网关）")
                clear_frontend()
                launch_desktop()


if __name__ == '__main__':
    main()
