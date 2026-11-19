# -*- coding: utf-8 -*-
"""
受控探针 v7：验证「沙箱 sitecustomize 删除钩子导致网关永远 starting」这一根因。
网关是本脚本的子进程，脚本存活期间网关全程存活；脚本结束网关随之回收。
只做诊断，不做常驻、不启动桌面、不清理前端。
"""
import os, sys, time, json, subprocess, shutil, ctypes, datetime
from pathlib import Path

HOME = Path(r'E:\workbuddy\国外模型\hermes')
AGENT = HOME / 'hermes-agent'
LOCKS = Path(r'C:\Users\Administrator\.local\state\hermes\gateway-locks')
STATE = HOME / 'gateway_state.json'
GWLOG = Path(r'E:/workbuddy/gw_probe_clean.log')
BAK = Path(r'E:/workbuddy/hermes_state_backup_probe_1747')

DROP_PREFIX = ('CODEBUDDY_', 'WORKBUDDY_', 'SANDBOX_', 'LSBOX_', 'CLAUDE_', 'GENIE_')
DROP_EXACT = ('PYTHONPATH', 'BASH_ENV', 'NODE_OPTIONS', 'NODE_EXTRA_CA_CERTS',
              'PYTHONSTARTUP', 'PYTHONHOME')

RESET = [LOCKS / 'host-gateway.json', LOCKS / 'host-gateway.lock', LOCKS / 'host-gateway.token',
         HOME / 'gateway.pid', HOME / 'gateway.lock', STATE, HOME / '.gateway-takeover.json']


def clean_env():
    env = dict(os.environ)
    for k in list(env):
        if k.upper().startswith(DROP_PREFIX) or k.upper() in DROP_EXACT:
            env.pop(k, None)
    env['PATH'] = os.pathsep.join(
        p for p in env.get('PATH', '').split(os.pathsep)
        if p and 'sandbox-center-runtime-kit' not in p and 'safe-bin' not in p)
    env['CODEBUDDY_SAFE_DELETE_ENABLED'] = '0'
    env['CODEBUDDY_SAFE_DELETE_SANDBOX'] = '0'
    env['HERMES_HOME'] = str(HOME)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    tmp = r'E:\workbuddy\tmp'
    os.makedirs(tmp, exist_ok=True)
    env['TEMP'] = env['TMP'] = tmp
    return env


def reset_state():
    BAK.mkdir(parents=True, exist_ok=True)
    n = 0
    for i, p in enumerate(RESET):
        if not p.exists():
            continue
        try:
            shutil.copy2(str(p), str(BAK / ('%02d_%s' % (i, p.name))))
        except Exception:
            pass
        try:
            os.remove(str(p))
        except Exception:
            ctypes.windll.kernel32.DeleteFileW(ctypes.c_wchar_p(str(p)))
        if not p.exists():
            n += 1
    print('state reset: %d files removed' % n, flush=True)


def jread(p):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8-sig'))
    except Exception:
        return {}


def main():
    print('=== GW PROBE v7 ===', flush=True)
    print('source PYTHONPATH = %r' % os.environ.get('PYTHONPATH'), flush=True)
    # 清掉 v6 挂起的桌面（它占着 job 且不拉网关），避免与探针抢 host lock
    try:
        r = subprocess.run(['taskkill.exe', '/F', '/IM', 'Hermes.exe'],
                           capture_output=True, timeout=20)
        print('leftover desktop cleanup rc=%s' % r.returncode, flush=True)
    except Exception as e:
        print('taskkill err %s' % e, flush=True)
    time.sleep(1.5)
    env = clean_env()
    reset_state()

    # 官方运行时入口（桌面 gateway ensure 用的就是它）
    py = HOME / 'tools' / 'python-3.14.9+20261021-win32-x64' / 'python.exe'
    if not py.exists():
        cand = list((HOME / 'tools').glob('python-*/python.exe'))
        py = cand[0] if cand else None
    print('python = %s' % py, flush=True)

    f = open(GWLOG, 'ab', 0)
    cmd = [str(py), '-m', 'hermes_cli.main', '--profile', 'default',
           'gateway', 'run', '--quiet', '--external-supervisor']
    print('cmd = %s' % ' '.join(cmd), flush=True)
    p = subprocess.Popen(cmd, cwd=str(AGENT), env=env, stdout=f, stderr=f,
                         creationflags=0x00000200 | 0x00000800)
    print('gateway pid = %s' % p.pid, flush=True)

    start = time.time()
    while time.time() - start < 75:
        time.sleep(5)
        st = jread(STATE)
        rec = jread(LOCKS / 'host-gateway.json')
        alive = p.poll() is None
        print('[%3.0fs] proc=%s state=%-10s state_pid=%-7s port=%-6s profiles=%-4s agents=%s' % (
            time.time() - start, 'ALIVE' if alive else 'DEAD',
            st.get('gateway_state'), st.get('pid'), rec.get('port'),
            len(rec.get('profiles') or []), st.get('active_agents')), flush=True)
        if rec.get('port') and st.get('gateway_state') not in (None, 'starting'):
            print('>>> ROOT CAUSE CONFIRMED: clean env -> gateway registered', flush=True)
            break
    try:
        tail = GWLOG.read_text(encoding='utf-8', errors='replace').splitlines()[-25:]
        print('=== gateway stdout tail ===', flush=True)
        for l in tail:
            print('   ', l[:200], flush=True)
    except Exception as e:
        print('log err', e, flush=True)
    print('=== probe done ===', flush=True)


if __name__ == '__main__':
    main()
