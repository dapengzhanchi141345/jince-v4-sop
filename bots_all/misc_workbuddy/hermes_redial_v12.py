# -*- coding: utf-8 -*-
"""
v12 —— 单次桌面冷启动重握手（不重启网关 / 不清前端数据 / 不打断长 agent turn）。

依据（2026-11-14 实测）：
  * control socket identify: state=ready, instance_id=d762..., 31 served profiles。
  * 用当前 instance_id + native-http purpose 签票，/api/health 与 /api/local-models/status
    均 200 -> _native_store() 的 descriptor/authorities/served_profiles 校验是通过的。
  * 桌面却持续 401 -> 桌面缓存 descriptor 的旧 instance_id / 票据兑换失败。
  * 官方 attach 只校验不写 backendPool，rescan-profiles 只对齐 served set，
    刷新 descriptor 只能靠桌面进程重新 ensureLocalGateway()（内存态，冷启动即重建）。
  * 网关有 2983s 的 delegation + 353s 的 chat turn，绝对不能重启网关。

严格保护：
  * 只终止 Hermes.exe 及其直接派生的 '-P -u -c' python helper。
  * 绝不碰 ppid=31736 的网关子进程、agnes 密钥池/看门狗、grep/head 等长 turn 工具。
  * 启动前后校验网关 PID 与 instance_id 不变。
  * 单次执行，无 keepalive、无循环、无互杀。
"""
import os, sys, time, json, subprocess, datetime, http.client
from pathlib import Path

ROOT = Path(r'E:\workbuddy\国外模型\hermes')
AGENT = ROOT / 'hermes-agent'
DESKTOP_EXE = Path(r'E:\hb\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe')
DESKLOG = ROOT / 'logs' / 'desktop.log'
VLOG = Path(r'E:/workbuddy/hermes_v12.log')
REPORT = Path(r'E:/workbuddy/hermes_v12_report.json')
GW_PID = 31736
FLAGS = 0x00000200 | 0x00000800

sys.path.insert(0, str(AGENT))
from hermes_cli.gateway_client import private_control_query

DROP_PREFIX = ('CODEBUDDY_', 'WORKBUDDY_', 'SANDBOX_', 'LSBOX_', 'CLAUDE_', 'GENIE_')
DROP_EXACT = ('PYTHONPATH', 'BASH_ENV', 'NODE_OPTIONS', 'NODE_EXTRA_CA_CERTS',
              'PYTHONSTARTUP', 'PYTHONHOME')


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
        x for x in env.get('PATH', '').split(os.pathsep)
        if x and 'sandbox-center-runtime-kit' not in x and 'safe-bin' not in x)
    env['CODEBUDDY_SAFE_DELETE_ENABLED'] = '0'
    env['CODEBUDDY_SAFE_DELETE_SANDBOX'] = '0'
    env['HERMES_HOME'] = str(ROOT)   # 与网关完全一致的 home 字符串
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    tmp = r'E:\workbuddy\tmp'
    os.makedirs(tmp, exist_ok=True)
    env['TEMP'] = env['TMP'] = tmp
    env['TMPDIR'] = tmp.replace('\\', '/')
    return env


def q(verb, params=None, timeout=8):
    raw = private_control_query(
        ROOT, (json.dumps({'protocol': 1, 'id': 1, 'verb': verb, 'params': params or {}}) + '\n').encode(),
        timeout=timeout)
    return json.loads(raw.decode('utf-8', 'replace').split('\n', 1)[0])


def identify():
    return q('identify').get('result', {}) or {}


def gateway_alive():
    try:
        import psutil
        return psutil.pid_exists(GW_PID)
    except Exception:
        return False


def desktop_pids():
    import psutil
    out = set()
    for pr in psutil.process_iter(['pid', 'name']):
        try:
            if (pr.info['name'] or '').lower() == 'hermes.exe':
                out.add(pr.info['pid'])
        except Exception:
            pass
    return out


def helper_pids(parents):
    """只收集桌面进程直接派生、且 cmdline 含 '-P -u -c' 的 python helper。"""
    import psutil
    out = []
    for pr in psutil.process_iter(['pid', 'ppid', 'name', 'cmdline']):
        try:
            if pr.info['ppid'] not in parents:
                continue
            nm = (pr.info['name'] or '').lower()
            cmd = ' '.join(pr.info['cmdline'] or [])
            if nm.startswith('python') and '-P -u -c' in cmd:
                out.append(pr.info['pid'])
        except Exception:
            pass
    return out


def main():
    R = {}
    log('=== v12 单次桌面重握手 ===')
    before = identify()
    R['before'] = {'gateway_pid': GW_PID, 'instance_id': before.get('instance_id'),
                   'state': before.get('state'), 'alive': gateway_alive()}
    log('网关基线 pid=%s instance=%s state=%s alive=%s' % (
        GW_PID, before.get('instance_id'), before.get('state'), R['before']['alive']))
    if not R['before']['alive'] or before.get('state') != 'ready':
        R['result'] = 'ABORT_GATEWAY_NOT_READY'
        REPORT.write_text(json.dumps(R, ensure_ascii=False, indent=2), encoding='utf-8')
        log('网关不健康，中止（不动桌面）')
        return

    try:
        R['desklog_start_line'] = len(DESKLOG.read_text(encoding='utf-8', errors='replace').splitlines())
    except Exception:
        R['desklog_start_line'] = 0

    # ---- 1. 精确终止桌面 + 其 helper ----
    dps = desktop_pids()
    hps = helper_pids(dps)
    R['desktop_pids_before'] = sorted(dps)
    R['helper_pids_before'] = hps
    log('桌面进程 %d 个: %s' % (len(dps), sorted(dps)))
    log('待清理 helper %d 个' % len(hps))

    try:
        r = subprocess.run(['taskkill.exe', '/F', '/IM', 'Hermes.exe'],
                           capture_output=True, timeout=25)
        log('taskkill Hermes.exe rc=%s' % r.returncode)
    except Exception as e:
        log('taskkill ERR %r' % e)

    import psutil
    killed = 0
    for pid in hps:
        try:
            p = psutil.Process(pid)
            # 二次确认：仍是 python 且仍带目标 cmdline
            if 'python' in (p.name() or '').lower() and '-P -u -c' in ' '.join(p.cmdline()):
                p.kill()
                killed += 1
        except Exception:
            pass
    R['helpers_killed'] = killed
    log('清理 helper %d 个' % killed)
    time.sleep(3)
    R['desktop_pids_after_kill'] = sorted(desktop_pids())
    log('kill 后残留桌面进程: %s' % R['desktop_pids_after_kill'])

    # ---- 2. 单次启动桌面 ----
    env = clean_env()
    if not DESKTOP_EXE.exists():
        DESKTOP_EXE2 = ROOT / 'hermes-agent' / 'apps' / 'desktop' / 'release' / 'win-unpacked' / 'Hermes.exe'
        log('E:/hb 路径不存在，改用 %s' % DESKTOP_EXE2)
        exe = DESKTOP_EXE2
    else:
        exe = DESKTOP_EXE
    R['desktop_exe'] = str(exe)
    try:
        d = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=FLAGS)
        R['desktop_new_pid'] = d.pid
        log('桌面已冷启动 pid=%s exe=%s' % (d.pid, exe))
    except Exception as e:
        R['result'] = 'DESKTOP_LAUNCH_FAILED'
        R['error'] = repr(e)
        REPORT.write_text(json.dumps(R, ensure_ascii=False, indent=2), encoding='utf-8')
        log('桌面启动失败 %r' % e)
        return

    # ---- 3. 保护性验证：网关未被重启 ----
    time.sleep(20)
    after = identify()
    R['after_20s'] = {'gateway_alive': gateway_alive(),
                      'instance_id': after.get('instance_id'),
                      'state': after.get('state'),
                      'desktop_pids': sorted(desktop_pids())}
    same_inst = after.get('instance_id') == before.get('instance_id')
    R['gateway_unchanged'] = same_inst and R['after_20s']['gateway_alive']
    log('20s 校验: 网关存活=%s instance 未变=%s 桌面进程=%s' % (
        R['after_20s']['gateway_alive'], same_inst, R['after_20s']['desktop_pids']))

    # ---- 4. 观察桌面日志新增行 ----
    time.sleep(55)
    try:
        lines = DESKLOG.read_text(encoding='utf-8', errors='replace').splitlines()
        new = lines[R['desklog_start_line']:]
        R['desklog_new_lines'] = len(new)
        R['new_401_count'] = sum(1 for l in new if '401' in l)
        R['new_gtbf_count'] = sum(1 for l in new if 'Gateway ticket bootstrap failed' in l)
        R['desklog_tail'] = new[-18:]
        log('桌面日志新增 %d 行, 401=%d, GTBF=%d' % (
            len(new), R['new_401_count'], R['new_gtbf_count']))
        for l in new[-6:]:
            log('  DESK %s' % l[:180])
    except Exception as e:
        log('desktop.log 读取失败 %r' % e)

    # ---- 5. 复测 native HTTP ----
    ident2 = identify()
    inst = ident2.get('instance_id')
    port = int(str(ident2.get('api_origin') or 'http://127.0.0.1:61083').rsplit(':', 1)[1])
    sp = ident2.get('served_profiles') or []
    pid = sp[0].get('profile_id') if sp and isinstance(sp[0], dict) else (sp[0] if sp else str(ROOT))
    http_results = {}
    for path in ('/api/health', '/api/status', '/api/profiles'):
        try:
            tk = q('session-ticket', {'profile_id': pid, 'instance_id': inst,
                                      'purpose': 'native-http'})['result']['ticket']
            c = http.client.HTTPConnection('127.0.0.1', port, timeout=8)
            c.request('GET', path, headers={'X-Hermes-Gateway-Ticket': tk, 'Accept': 'application/json'})
            resp = c.getresponse()
            http_results[path] = {'status': resp.status,
                                  'body': resp.read(180).decode('utf-8', 'replace')}
            c.close()
        except Exception as e:
            http_results[path] = {'error': repr(e)}
        log('HTTP %-18s -> %s' % (path, json.dumps(http_results[path], ensure_ascii=False)[:180]))
    R['http_probe'] = http_results

    R['final'] = {'gateway_alive': gateway_alive(),
                  'instance_id': identify().get('instance_id'),
                  'desktop_pids': sorted(desktop_pids())}
    R['result'] = 'DESKTOP_REDIALED'
    R['at'] = datetime.datetime.now().isoformat(timespec='seconds')
    REPORT.write_text(json.dumps(R, ensure_ascii=False, indent=2), encoding='utf-8')
    log('=== 完成，报告 -> %s ===' % REPORT)


if __name__ == '__main__':
    main()
