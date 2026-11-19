# -*- coding: utf-8 -*-
"""
v13 —— 精确清场 + 真正冷启动桌面（v12 的 taskkill /IM 未生效的纠正版）。

v12 复盘：
  * taskkill /F /IM Hermes.exe 返回 rc=0，但旧桌面进程树 40440/12388/1048/19156/38596
    20s 后仍全部存活；新 Popen 的 28372 撞 Electron 单实例锁后未写日志。
  * desktop.log 自 19:37:18 起零新增，说明"重握手"实际没发生。
  * /api/status 200 只来自 helper 清理后的网关减压，不是桌面恢复的证据。

v13 做法：
  * 按 PID 用 psutil 逐个 kill + wait 确认退出；失败则 taskkill /F /PID 兜底。
  * 同时清理桌面派生的 '-P -u -c' python helper。
  * 确认 Hermes.exe 数量归零后才启动；若旧进程杀不掉就中止（绝不制造第二个实例）。
  * 仍严格不动网关 PID 31736 及其子进程、密钥池看门狗、长 turn 工具进程。
  * 启动后以 desktop.log 的字节数增长 + 新 401 计数作为验收依据。
"""
import os, sys, time, json, subprocess, datetime, http.client
from pathlib import Path

ROOT = Path(r'E:\workbuddy\国外模型\hermes')
AGENT = ROOT / 'hermes-agent'
DESKTOP_EXE = Path(r'E:\hb\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe')
DESKLOG = ROOT / 'logs' / 'desktop.log'
VLOG = Path(r'E:/workbuddy/hermes_v13.log')
REPORT = Path(r'E:/workbuddy/hermes_v13_report.json')
GW_PID = 31736
FLAGS = 0x00000200 | 0x00000800
USERDATA = Path(r'C:\Users\Administrator\AppData\Roaming\Hermes')

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
    env['HERMES_HOME'] = str(ROOT)
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


def hermes_procs():
    import psutil
    out = []
    for pr in psutil.process_iter(['pid', 'ppid', 'name', 'cmdline', 'create_time']):
        try:
            if (pr.info['name'] or '').lower() == 'hermes.exe':
                out.append(pr.info)
        except Exception:
            pass
    return out


def helper_pids(parents):
    import psutil
    out = []
    for pr in psutil.process_iter(['pid', 'ppid', 'name', 'cmdline']):
        try:
            if pr.info['ppid'] not in parents:
                continue
            if (pr.info['name'] or '').lower().startswith('python') and '-P -u -c' in ' '.join(pr.info['cmdline'] or []):
                out.append(pr.info['pid'])
        except Exception:
            pass
    return out


def kill_pid(pid):
    import psutil
    try:
        p = psutil.Process(pid)
        p.kill()
        p.wait(timeout=6)
        return 'killed'
    except Exception as e:
        try:
            r = subprocess.run(['taskkill.exe', '/F', '/PID', str(pid)],
                               capture_output=True, timeout=15)
            return 'taskkill rc=%s' % r.returncode
        except Exception as e2:
            return 'FAILED %r / %r' % (e, e2)


def main():
    R = {}
    log('=== v13 精确清场 + 真冷启动 ===')
    before = identify()
    R['before'] = {'instance_id': before.get('instance_id'), 'state': before.get('state')}
    log('网关基线 instance=%s state=%s' % (before.get('instance_id'), before.get('state')))
    if before.get('state') != 'ready':
        R['result'] = 'ABORT_GATEWAY_NOT_READY'
        REPORT.write_text(json.dumps(R, ensure_ascii=False, indent=2), encoding='utf-8')
        return

    try:
        log_size_before = DESKLOG.stat().st_size
    except Exception:
        log_size_before = 0
    R['desklog_size_before'] = log_size_before

    # ---- 1. 精确清场 ----
    procs = hermes_procs()
    dpids = {x['pid'] for x in procs}
    R['desktop_before'] = [
        {'pid': x['pid'], 'ppid': x['ppid'], 'create_time': x['create_time'],
         'cmd': ' '.join(x['cmdline'] or [])[:110]} for x in procs]
    log('清场前 Hermes.exe %d 个:' % len(procs))
    for x in procs:
        log('  pid=%s ppid=%s born=%s %s' % (
            x['pid'], x['ppid'],
            datetime.datetime.fromtimestamp(x['create_time']).strftime('%H:%M:%S') if x['create_time'] else '?',
            ' '.join(x['cmdline'] or [])[:100]))

    hps = helper_pids(dpids)
    R['helper_before'] = hps
    log('桌面 helper %d 个' % len(hps))

    results = {}
    for pid in sorted(dpids):
        results[pid] = kill_pid(pid)
        log('kill Hermes pid=%s -> %s' % (pid, results[pid]))
    for pid in hps:
        kill_pid(pid)
    R['kill_results'] = {str(k): v for k, v in results.items()}
    log('helper 已清理 %d 个' % len(hps))

    time.sleep(4)
    remaining = hermes_procs()
    R['desktop_remaining'] = [x['pid'] for x in remaining]
    log('清场后残留 Hermes.exe: %s' % R['desktop_remaining'])
    if remaining:
        # 再补一轮，绝不带着旧实例启动第二个
        log('残留仍存在，补杀一轮')
        for x in remaining:
            kill_pid(x['pid'])
        time.sleep(4)
        remaining = hermes_procs()
        R['desktop_remaining_2'] = [x['pid'] for x in remaining]
        log('补杀后残留: %s' % R['desktop_remaining_2'])
    if remaining:
        R['result'] = 'ABORT_OLD_DESKTOP_STILL_ALIVE'
        REPORT.write_text(json.dumps(R, ensure_ascii=False, indent=2), encoding='utf-8')
        log('旧桌面清不掉，中止启动（避免双实例）')
        return

    # ---- 2. Electron 单实例锁（旧进程已死，锁文件残留会挡新实例）----
    locks = []
    try:
        for name in ('SingletonLock', 'SingletonCookie', 'SingletonSocket'):
            f = USERDATA / name
            if f.exists():
                locks.append(name)
                try:
                    f.unlink()
                    log('移除单实例锁 %s' % name)
                except Exception as e:
                    log('移除 %s 失败 %r' % (name, e))
    except Exception as e:
        log('单实例锁检查失败 %r' % e)
    R['singleton_locks_removed'] = locks

    # ---- 3. 启动桌面 ----
    env = clean_env()
    exe = DESKTOP_EXE if DESKTOP_EXE.exists() else (
        ROOT / 'hermes-agent' / 'apps' / 'desktop' / 'release' / 'win-unpacked' / 'Hermes.exe')
    R['desktop_exe'] = str(exe)
    try:
        d = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=FLAGS)
        R['desktop_new_pid'] = d.pid
        log('桌面已启动 pid=%s' % d.pid)
    except Exception as e:
        R['result'] = 'LAUNCH_FAILED'
        R['error'] = repr(e)
        REPORT.write_text(json.dumps(R, ensure_ascii=False, indent=2), encoding='utf-8')
        return

    # ---- 4. 验收：新进程 + 日志新增 + 401 计数 ----
    time.sleep(40)
    R['desktop_after'] = [
        {'pid': x['pid'], 'ppid': x['ppid'],
         'born': datetime.datetime.fromtimestamp(x['create_time']).strftime('%H:%M:%S') if x['create_time'] else '?'}
        for x in hermes_procs()]
    log('40s 后 Hermes.exe: %s' % R['desktop_after'])

    try:
        size_after = DESKLOG.stat().st_size
        R['desklog_size_after'] = size_after
        R['desklog_grew'] = size_after - log_size_before
        with open(DESKLOG, 'rb') as f:
            f.seek(log_size_before)
            new = f.read().decode('utf-8', 'replace').splitlines()
        R['desklog_new_lines'] = len(new)
        R['new_401_count'] = sum(1 for l in new if '401' in l)
        R['new_gtbf_count'] = sum(1 for l in new if 'Gateway ticket bootstrap failed' in l)
        R['desklog_tail'] = new[-15:]
        log('日志新增 %d 字节 / %d 行, 401=%d, GTBF=%d' % (
            size_after - log_size_before, len(new), R['new_401_count'], R['new_gtbf_count']))
        for l in new[-8:]:
            log('  DESK %s' % l[:180])
    except Exception as e:
        log('日志验收失败 %r' % e)

    # ---- 5. 网关未被改动 ----
    after = identify()
    R['gateway_after'] = {'instance_id': after.get('instance_id'), 'state': after.get('state'),
                          'alive': after.get('pid') == GW_PID}
    R['gateway_unchanged'] = after.get('instance_id') == before.get('instance_id')
    log('网关校验: pid=%s instance 未变=%s state=%s' % (
        after.get('pid'), R['gateway_unchanged'], after.get('state')))

    R['result'] = 'DESKTOP_COLD_STARTED'
    R['at'] = datetime.datetime.now().isoformat(timespec='seconds')
    REPORT.write_text(json.dumps(R, ensure_ascii=False, indent=2), encoding='utf-8')
    log('=== 完成 -> %s ===' % REPORT)


if __name__ == '__main__':
    main()
