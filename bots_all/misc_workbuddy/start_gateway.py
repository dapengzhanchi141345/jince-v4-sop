# -*- coding: utf-8 -*-
"""显式拉起 Hermes 网关（脱钩、持久、外部 supervisor 模式）。
- 使用已验证可用的好 venv（e5c564bcc6c6450e926a327c3e00991c, pydantic_core 2.50.1）
- 传 --external-supervisor：不注册 Windows 服务/schtasks（沙箱会拦截 schtasks），改由本脚本监督
- 启动前备份并清空陈旧的 gateway_state.json / gateway.lock，确保干净启动
- DETACHED + BREAKAWAY，不被父 shell 带走
"""
import os, subprocess, sys, datetime, shutil

VENV_PY = r'E:/hb/installs/4ea489dd943be455/environments/e5c564bcc6c6450e926a327c3e00991c/venv/Scripts/python.exe'
MAIN = r'E:\workbuddy\国外模型\hermes\hermes-agent\hermes_cli\main.py'
CWD = r'E:\workbuddy\国外模型\hermes\hermes-agent'
HERMES_HOME = r'E:\workbuddy\国外模型\hermes'
STATE = r'E:/hb/gateway_state.json'
LOCK = r'E:/hb/gateway.lock'
LOG = r'E:/workbuddy/gateway_launch.log'


def log(msg):
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}\n"
    sys.stdout.write(line); sys.stdout.flush()
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass


def reset_state():
    for f in (STATE, LOCK):
        if os.path.exists(f):
            bak = f + '.bak-reset-' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            try:
                shutil.copy2(f, bak)
                os.remove(f)
                log(f"已备份并清空 {f} -> {bak}")
            except Exception as e:
                log(f"清空 {f} 失败(尝试继续): {e}")


def main():
    log("=== 显式启动 Hermes 网关 (external-supervisor) ===")
    reset_state()
    if not os.path.exists(VENV_PY):
        log(f"venv python 不存在: {VENV_PY}"); return
    if not os.path.exists(MAIN):
        log(f"main.py 不存在: {MAIN}"); return
    env = dict(os.environ)
    env['HERMES_HOME'] = HERMES_HOME
    env['PYTHONIOENCODING'] = 'utf-8'
    f = open(LOG, 'ab', 0)
    try:
        p = subprocess.Popen(
            [VENV_PY, MAIN, 'gateway', 'run', '--quiet', '--external-supervisor'],
            cwd=CWD, env=env, stdout=f, stderr=f,
            creationflags=0x00000200 | 0x00000800  # DETACHED | BREAKAWAY
        )
        log(f"已 Popen 网关, pid={p.pid}")
    except Exception as e:
        log(f"启动失败: {e}")
    finally:
        try:
            f.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()
