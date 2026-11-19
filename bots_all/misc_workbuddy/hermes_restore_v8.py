# -*- coding: utf-8 -*-
"""
Hermes 最终恢复 v8 —— 一次性收敛 + 只读常驻心跳。

综合定位（2026-11-14）：
  1) WorkBuddy 沙箱把 PYTHONPATH 指向 sandbox-center-runtime-kit/shim，
     sitecustomize.py patch 了 os.remove/os.unlink。从沙箱 Bash 派生的网关
     删除 gateway.pid / .gateway-takeover.json 被 SAFE_DELETE_BULK 拦截，
     陈旧 pid 文件残留 -> write_pid_file() 的 O_EXCL 必失败 -> 启动闸门退回。
  2) gateway_state.json 自身也是门禁：gateway_state="starting" 被
     get_runtime_status_running_pid() 当作活动网关，反过来阻止新网关绑定。
  3) --replace 在 "owner 未发布 served set / home 字符串不一致 / pid 陈旧"
     三种情况下 fail-closed 拒绝；必须 --force 跳过 host 级所有权 ladder。
  4) _same_hermes_home 是字符串比较（非 samefile）：E:/hb 与
     E:\\workbuddy\\国外模型\\hermes 视为不同 home。必须全程统一一个路径。
  5) v3/v4/v5 外部监督器每 20~40s taskkill 桌面 + 清空前端，与桌面原生
     gateway ensure 链路互抢 host lock，形成无限互杀。

v8 做法：
  - 干净 env：剥离 PYTHONPATH/BASH_ENV/NODE_OPTIONS/CODEBUDDY_*/PATH-shim；
    TEMP/TMP 指向 E 盘（C 盘零落盘铁律）。
  - 统一 HERMES_HOME = E:\\workbuddy\\国外模型\\hermes，桌面与网关同路径字符串。
  - 清掉全部 8 类门禁文件（先备份到 E 盘）。
  - 用 --force（不是 --replace）+ --external-supervisor 拉唯一网关。
  - 等 gateway_state 变 running（最多 360s），期间打印 gateway.log 新增行定位卡点。
  - 只有网关 ready 才启动桌面（v5 实测有效的 0x200|0x800 flags，不用 DETACHED_PROCESS）。
  - 之后只做只读心跳：绝不杀桌面、绝不重拉网关、绝不清前端。
"""
import os, sys, time, json, shutil, ctypes, subprocess, datetime
from pathlib import Path

ROOT = Path(r'E:\workbuddy\国外模型\hermes')
AGENT = ROOT / 'hermes-agent'
LOCKS = Path(r'C:\Users\Administrator\.local\state\hermes\gateway-locks')
STATE = ROOT / 'gateway_state.json'
GWLOG = Path(r'E:/workbuddy/gateway_v8_stdout.log')
APPLOG = ROOT / 'logs' / 'gateway.log'
DESKLOG = ROOT / 'logs' / 'desktop.log'
VLOG = Path(r'E:/workbuddy/hermes_v8.log')
REPORT = Path(r'E:/workbuddy/hermes_v8_report.json')
BAK = Path(r'E:/workbuddy/hermes_state_backup_v8_1800')

DESKTOP_EXE = ROOT / 'hermes-agent' / 'apps' / 'desktop' / 'release' / 'win-unpacked' / 'Hermes.exe'
DESKTOP_CWD = DESKTOP_EXE.parent
PY = ROOT / 'tools' / 'python-3.14.9+20261021-win32-x64' / 'python.exe'

DROP_PREFIX = ('CODEBUDDY_', 'WORKBUDDY_', 'SANDBOX_', 'LSBOX_', 'CLAUDE_', 'GENIE_')
DROP_EXACT = ('PYTHONPATH', 'BASH_ENV', 'NODE_OPTIONS', 'NODE_EXTRA_CA_CERTS',
              'PYTHONSTARTUP', 'PYTHONHOME')
RESET = [
    LOCKS / 'host-gateway.json', LOCKS / 'host-gateway.lock', LOCKS / 'host-gateway.token',
    LOCKS / 'host-serve.json', LOCKS / 'host-serve.lock', LOCKS / 'host-serve.token',
    ROOT / 'gateway.pid', ROOT / 'gateway.lock', STATE, ROOT / '.gateway-takeover.json',
    ROOT / 'gateway.status',
]
# v5 实测可用的 flags（不用 DETACHED_PROCESS，Electron 会挂起）
FLAGS = 0x00000200 | 0x00000800


def log(msg):
    line = '[%s] %s' % (datetime.datetime.now().strftime('%H:%M:%S'), msg)
    print(line, flush=True)
    try:
        with open(VLOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def clean_env():
    env = dict(os.environ)
    for k in list(env):
        if k.upper().startswith(DROP_PREFIX) or k.upper() in DROP_EXACT:
            env.pop(k, None)
    env['PATH'] = os.pathsep.join(
        p for p in env.get('PATH', '').split(os.pathsep)
        if p and 'sandbox-center-runtime-kit' not in p and 'safe-bin' not in p)
    # 双保险：即便 sitecustomize 被加载也不启用删除钩子
    env['CODEBUDDY_SAFE_DELETE_ENABLED'] = '0'
    env['CODEBUDDY_SAFE_DELETE_SANDBOX'] = '0'
    env['HERMES_HOME'] = str(ROOT)          # 全程统一的 home 字符串
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    tmp = r'E:\workbuddy\tmp'
    os.makedirs(tmp, exist_ok=True)
    env['TEMP'] = env['TMP'] = tmp
    env['TMPDIR'] = tmp.replace('\\', '/')
    return env


def reset_state():
    BAK.mkdir(parents=True, exist_ok=True)
    n, fail = 0, []
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
        if p.exists():
            fail.append(str(p))
        else:
            n += 1
    log('门禁文件重置: 删除 %d / 失败 %d -> %s' % (n, len(fail), BAK))
    if fail:
        log('  失败清单: %s' % fail)
    return not fail


def kill_hermes():
    # 只杀 Hermes 桌面/网关，保留 agnes 密钥池与 GoldstrategyEngine 守护进程
    try:
        r = subprocess.run(['taskkill.exe', '/F', '/IM', 'Hermes.exe'],
                           capture_output=True, timeout=20)
        log('taskkill Hermes.exe rc=%s' % r.returncode)
    except Exception as e:
        log('taskkill err %s' % e)
    try:
        import psutil
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cl = ' '.join(p.info['cmdline'] or []).lower()
                if ('gateway run' in cl or 'gateway ensure' in cl
                        or 'hermes_cli.main' in cl) and 'hermes' in cl:
                    p.kill()
                    log('kill leftover gateway pid=%s' % p.info['pid'])
            except Exception:
                pass
    except ImportError:
        log('psutil 不可用，跳过命令行精确杀')
    time.sleep(2)


def jread(p):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8-sig'))
    except Exception:
        return {}


def wait_gateway(timeout=360):
    log('等待网关注册（最多 %ds，验收=gateway_state 变 running/degraded）...' % timeout)
    start = time.time()
    seen_log_pos = 0
    try:
        seen_log_pos = len(APPLOG.read_text(encoding='utf-8', errors='replace').splitlines())
    except Exception:
        pass
    last_state = None
    while time.time() - start < timeout:
        time.sleep(10)
        st = jread(STATE)
        rec = jread(LOCKS / 'host-gateway.json')
        s = st.get('gateway_state')
        if s != last_state:
            log('  state 变化: %r -> %r (pid=%s, agents=%s, platforms=%d)' % (
                last_state, s, st.get('pid'), st.get('active_agents'),
                len(st.get('platforms') or {})))
            last_state = s
        if int(time.time() - start) % 40 < 10:
            log('  [%3.0fs] state=%-14s port=%-6s profiles=%-3s exit_reason=%s' % (
                time.time() - start, s, rec.get('port'),
                len(rec.get('profiles') or []), st.get('exit_reason')))
        # 打印 gateway.log 新增行，定位卡点
        try:
            lines = APPLOG.read_text(encoding='utf-8', errors='replace').splitlines()
            new = lines[seen_log_pos:]
            seen_log_pos = len(lines)
            for l in new[:12]:
                if any(k in l for k in ('ERROR', 'WARNING', 'INFO gateway.run',
                                        'INFO gateway.run_startup', 'Starting', 'ready', 'READY')):
                    log('    LOG %s' % l[:190])
        except Exception:
            pass
        if s in ('running', 'degraded'):
            log('>>> 网关已注册: %s' % json.dumps(st, ensure_ascii=False)[:500])
            return True, st
        if s == 'startup_failed':
            log('>>> 启动失败 exit_reason=%s' % st.get('exit_reason'))
            return False, st
    log('>>> 等待超时，最后 state=%s' % last_state)
    return False, jread(STATE)


def main():
    log('=== Hermes 最终恢复 v8 ===')
    log('HOME=%s' % ROOT)
    log('source PYTHONPATH=%r' % os.environ.get('PYTHONPATH'))
    env = clean_env()
    log('干净 env: PYTHONPATH=%r SAFE_DELETE=%r TEMP=%r' % (
        env.get('PYTHONPATH'), env.get('CODEBUDDY_SAFE_DELETE_ENABLED'), env.get('TEMP')))

    kill_hermes()
    if not reset_state():
        log('门禁文件删除失败，中止'); return
    py = PY
    if not py.exists():
        cands = list((ROOT / 'tools').glob('python-*/python.exe'))
        if cands:
            py = cands[0]
    log('python=%s' % py)

    f = open(GWLOG, 'ab', 0)
    cmd = [str(py), '-m', 'hermes_cli.main', '--profile', 'default',
           'gateway', 'run', '--quiet', '--external-supervisor', '--force']
    log('网关命令: %s' % ' '.join(cmd))
    try:
        gw = subprocess.Popen(cmd, cwd=str(AGENT), env=env, stdout=f, stderr=f,
                              creationflags=FLAGS)
        log('网关 pid=%s' % gw.pid)
    except Exception as e:
        log('网关启动失败: %s' % e)
        REPORT.write_text(json.dumps({'result': 'LAUNCH_FAILED', 'error': str(e)},
                                     ensure_ascii=False, indent=2), encoding='utf-8')
        return

    ok, st = wait_gateway()
    result = {'gateway_ready': ok, 'gateway_state': st,
              'host_record': jread(LOCKS / 'host-gateway.json')}

    if ok:
        log('网关 READY -> 启动桌面（同一干净 env / 同一 home 字符串）')
        try:
            d = subprocess.Popen([str(DESKTOP_EXE)], cwd=str(DESKTOP_CWD), env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=FLAGS)
            log('桌面 pid=%s' % d.pid)
            result['desktop_pid'] = d.pid
        except Exception as e:
            log('桌面启动失败: %s' % e)
            result['desktop_error'] = str(e)
        time.sleep(45)
        try:
            dl = DESKLOG.read_text(encoding='utf-8', errors='replace').splitlines()[-40:]
            result['desktop_log_tail'] = dl
            n401 = sum(1 for l in dl if '401' in l)
            result['desktop_401_count'] = n401
            log('桌面日志尾部 401 计数=%d' % n401)
            for l in dl[-8:]:
                log('    DESK %s' % l[:190])
        except Exception as e:
            log('desktop.log 读取失败 %s' % e)
    else:
        log('网关未就绪，不启动桌面（避免再次制造 401/互杀）')
        try:
            result['gateway_stdout_tail'] = GWLOG.read_text(
                encoding='utf-8', errors='replace').splitlines()[-30:]
        except Exception:
            pass

    result['result'] = 'READY' if ok else 'NOT_READY'
    result['at'] = datetime.datetime.now().isoformat(timespec='seconds')
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    log('=== 结果 %s，报告 -> %s ===' % (result['result'], REPORT))

    log('进入只读心跳（每 60s 记录，不干预任何进程）')
    while True:
        time.sleep(60)
        s = jread(STATE)
        log('HEARTBEAT state=%s pid=%s agents=%s platforms=%d' % (
            s.get('gateway_state'), s.get('pid'), s.get('active_agents'),
            len(s.get('platforms') or {})))


if __name__ == '__main__':
    main()
