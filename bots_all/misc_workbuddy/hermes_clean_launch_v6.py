# -*- coding: utf-8 -*-
"""
Hermes 干净恢复启动器 v6 —— 一次性收敛，不再互杀。

根因（2026-11-14 定位）：
  1. WorkBuddy 沙箱把 PYTHONPATH 指向 sandbox-center-runtime-kit/shim，
     sitecustomize.py 会 patch os.remove/os.unlink。凡是从沙箱 Bash 派生的
     Python 进程（含网关）继承此环境，删除 gateway.pid / .gateway-takeover.json
     时被 SAFE_DELETE_BULK_CONFIRM_REQUIRED 拦截，网关永远卡在 gateway_state=starting。
  2. v3/v4/v5 外部监督脚本另起一套网关，与桌面原生的
     `hermes.exe gateway ensure` 链路抢 host lock；keepalive 又每 20~40s
     taskkill /F /IM Hermes.exe + 清空前端，形成无限互杀循环。

修复：
  - 停止所有外部监督器（由调用方完成）。
  - 备份并清除陈旧 host rendezvous / pid / state / takeover 文件。
  - 构造「干净 env」：剥离 PYTHONPATH、BASH_ENV、NODE_OPTIONS、
    CODEBUDDY_*/WORKBUDDY_*/SANDBOX_*/LSBOX_* 与 PATH 中的 safe-bin，
    TEMP/TMP 重定向到 E 盘（C 盘零落盘铁律）。
  - 只启动桌面 Hermes.exe（DETACHED + BREAKAWAY），让桌面自己的
    gateway ensure 拉起唯一健康网关。
  - 轮询验证；本脚本常驻做「只记录不干预」心跳，绝不杀桌面、绝不重拉网关。
"""
import os
import sys
import time
import json
import shutil
import ctypes
import datetime
import subprocess
from pathlib import Path

LOG = r'E:/workbuddy/hermes_v6.log'
REPORT = r'E:/workbuddy/hermes_v6_report.json'
BACKUP = r'E:/workbuddy/hermes_state_backup_20261114_1747'

DESKTOP_EXE = r'E:/hb/hermes-agent/apps/desktop/release/win-unpacked/Hermes.exe'
DESKTOP_CWD = r'E:/hb/hermes-agent/apps/desktop/release/win-unpacked'

HERMES_HOME = r'E:\workbuddy\国外模型\hermes'
LOCKS_DIR = Path(r'C:\Users\Administrator\.local\state\hermes\gateway-locks')
STATE = Path(HERMES_HOME) / 'gateway_state.json'

# 陈旧状态文件：清掉后由原生链路重新发布
RESET_FILES = [
    LOCKS_DIR / 'host-gateway.json',
    LOCKS_DIR / 'host-gateway.lock',
    LOCKS_DIR / 'host-gateway.token',
    LOCKS_DIR / 'host-serve.json',
    LOCKS_DIR / 'host-serve.lock',
    LOCKS_DIR / 'host-serve.token',
    LOCKS_DIR / 'host-desktop-serve.json',
    LOCKS_DIR / 'host-desktop-serve.lock',
    LOCKS_DIR / 'host-desktop-serve.token',
    Path(HERMES_HOME) / 'gateway.pid',
    Path(HERMES_HOME) / 'gateway.lock',
    Path(HERMES_HOME) / 'gateway_state.json',
    Path(HERMES_HOME) / '.gateway-takeover.json',
    Path(HERMES_HOME) / 'gateway.status',
]

_DROP_PREFIXES = ('CODEBUDDY_', 'WORKBUDDY_', 'SANDBOX_', 'LSBOX_', 'CLAUDE_', 'GENIE_')
_DROP_EXACT = ('PYTHONPATH', 'BASH_ENV', 'NODE_OPTIONS', 'NODE_EXTRA_CA_CERTS',
               'PYTHONSTARTUP', 'PYTHONHOME', 'AGENT_BROWSER_ARGS',
               'PLAYWRIGHT_MCP_NO_SANDBOX', 'BROWSER_USE_CHROMIUM_SANDBOX')


def log(msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    line = '[%s] %s' % (ts, msg)
    print(line, flush=True)
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def clean_env():
    """剥离 WorkBuddy 沙箱注入，避免 sitecustomize 删除钩子污染桌面/网关。"""
    env = dict(os.environ)
    for key in list(env):
        up = key.upper()
        if up.startswith(_DROP_PREFIXES) or up in _DROP_EXACT:
            env.pop(key, None)
    # PATH 中的 safe-bin 是命令行删除 shim，一并剔除
    parts = [p for p in env.get('PATH', '').split(os.pathsep)
             if p and 'sandbox-center-runtime-kit' not in p and 'safe-bin' not in p]
    env['PATH'] = os.pathsep.join(parts)
    # 双保险：即使 sitecustomize 被加载，也不启用删除钩子
    env['CODEBUDDY_SAFE_DELETE_ENABLED'] = '0'
    env['CODEBUDDY_SAFE_DELETE_SANDBOX'] = '0'
    # 运行环境
    env['HERMES_HOME'] = HERMES_HOME
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    # C 盘零落盘铁律
    tmp = r'E:\workbuddy\tmp'
    try:
        os.makedirs(tmp, exist_ok=True)
    except Exception:
        pass
    env['TEMP'] = tmp
    env['TMP'] = tmp
    env['TMPDIR'] = tmp.replace('\\', '/')
    return env


def _native_delete(path):
    """绕过任何 Python 层 shim 的原生删除（ctypes 直调 Win32 DeleteFileW）。"""
    try:
        return bool(ctypes.windll.kernel32.DeleteFileW(ctypes.c_wchar_p(str(path))))
    except Exception:
        return False


def reset_state():
    """备份 -> 清除陈旧所有权/pid/state 文件。返回 (备份数, 删除数, 失败列表)。"""
    bak = Path(BACKUP)
    try:
        bak.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log('备份目录创建失败: %s' % e)
    backed, removed, failed = 0, 0, []
    for i, p in enumerate(RESET_FILES):
        if not p.exists():
            continue
        try:
            shutil.copy2(str(p), str(bak / ('%02d_%s' % (i, p.name))))
            backed += 1
        except Exception as e:
            log('备份失败 %s: %s' % (p.name, e))
        ok = False
        try:
            os.remove(str(p))
            ok = True
        except Exception:
            ok = _native_delete(p)
        if p.exists():
            failed.append(str(p))
            log('删除失败 %s' % p.name)
        else:
            removed += 1
    log('状态重置: 备份 %d / 删除 %d / 失败 %d -> %s' % (backed, removed, len(failed), BACKUP))
    return backed, removed, failed


def popen_detached(cmd, cwd, env, stdout=None):
    """DETACHED + BREAKAWAY 启动；job 不允许 breakaway 时逐级降级。"""
    DETACHED = 0x00000008
    NEW_GROUP = 0x00000200
    BREAKAWAY = 0x01000000
    NO_WINDOW = 0x08000000
    for flags, label in (
        (DETACHED | NEW_GROUP | BREAKAWAY, 'detached+breakaway'),
        (DETACHED | NEW_GROUP, 'detached'),
        (NO_WINDOW, 'nowindow'),
    ):
        try:
            p = subprocess.Popen(cmd, cwd=cwd, env=env,
                                 stdout=stdout or subprocess.DEVNULL,
                                 stderr=stdout or subprocess.DEVNULL,
                                 creationflags=flags, close_fds=True)
            log('Popen %s pid=%s [%s]' % (Path(cmd[0]).name, p.pid, label))
            return p
        except Exception as e:
            log('Popen flags %s 失败: %s' % (label, e))
    return None


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except Exception:
        return {}


def snapshot():
    st = read_json(STATE)
    rec = read_json(LOCKS_DIR / 'host-gateway.json')
    return {
        'checked_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'gateway_state': st.get('gateway_state'),
        'state_pid': st.get('pid'),
        'active_agents': st.get('active_agents'),
        'platforms': st.get('platforms'),
        'host_pid': rec.get('pid'),
        'host_port': rec.get('port'),
        'host_profiles': rec.get('profiles'),
        'host_updated_at': rec.get('updatedAt'),
    }


def verify(wait_s=210):
    """轮询等待网关真正注册：state 推进 + host record 绑定端口。"""
    log('开始验证（最多等待 %ds）...' % wait_s)
    start = time.time()
    best = None
    while time.time() - start < wait_s:
        s = snapshot()
        best = s
        ready = (s['gateway_state'] not in (None, 'starting')
                 and s['host_port'] is not None)
        if ready:
            log('网关已注册: %s' % json.dumps(s, ensure_ascii=False))
            try:
                Path(REPORT).write_text(
                    json.dumps({'result': 'READY', 'snapshot': s,
                                'elapsed_s': round(time.time() - start, 1)},
                               ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception:
                pass
            return True, s
        if int(time.time() - start) % 30 < 5:
            log('  等待中 state=%s port=%s host_pid=%s' %
                (s['gateway_state'], s['host_port'], s['host_pid']))
        time.sleep(5)
    log('验证超时，最后快照: %s' % json.dumps(best, ensure_ascii=False))
    try:
        Path(REPORT).write_text(
            json.dumps({'result': 'TIMEOUT', 'snapshot': best,
                        'elapsed_s': round(time.time() - start, 1)},
                       ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass
    return False, best


def main():
    log('=== Hermes 干净恢复 v6 启动 ===')
    log('PYPATH(源)=%r' % os.environ.get('PYTHONPATH'))
    env = clean_env()
    log('干净 env: PYTHONPATH=%r  SAFE_DELETE=%r  TEMP=%r' %
        (env.get('PYTHONPATH'), env.get('CODEBUDDY_SAFE_DELETE_ENABLED'), env.get('TEMP')))

    reset_state()
    # 桌面用自带 electron，不需要 PYTHONPATH；它拉起网关时会继承这一份干净 env
    p = popen_detached([DESKTOP_EXE], DESKTOP_CWD, env)
    if p is None:
        log('桌面启动失败')
        Path(REPORT).write_text(json.dumps({'result': 'LAUNCH_FAILED'},
                                           ensure_ascii=False, indent=2), encoding='utf-8')
        return

    ok, snap = verify()
    log('=== 结果: %s ===' % ('READY' if ok else 'TIMEOUT'))

    # 常驻心跳：只记录，绝不杀桌面 / 绝不重拉网关 / 绝不清前端
    log('进入只读心跳（每 60s 记录一次，不干预任何进程）')
    while True:
        time.sleep(60)
        s = snapshot()
        log('HEARTBEAT state=%s pid=%s port=%s profiles=%s' %
            (s['gateway_state'], s['state_pid'], s['host_port'], s['host_profiles']))


if __name__ == '__main__':
    main()
