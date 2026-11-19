# -*- coding: utf-8 -*-
"""v15：对比不同 HERMES_HOME 字符串解析到的 control channel，定位桌面签票失败根因。只读。"""
import sys, json, datetime
from pathlib import Path

ROOT = Path(r'E:\workbuddy\国外模型\hermes')
sys.path.insert(0, str(ROOT / 'hermes-agent'))
from hermes_cli.gateway_client import private_control_query

def p(tag, val):
    print('[%s] %s' % (tag, val), flush=True)

def q(home, verb, params=None, timeout=8):
    req = (json.dumps({'protocol': 1, 'id': 1, 'verb': verb, 'params': params or {}}) + '\n').encode()
    try:
        return private_control_query(Path(home), req, timeout).decode('utf-8', 'replace')
    except Exception as e:
        return 'ERR %r' % e

HOMES = [
    r'E:\workbuddy\国外模型\hermes',
    r'E:/workbuddy/国外模型/hermes',
    r'E:\hb',
    r'E:/hb',
]
for home in HOMES:
    out = q(home, 'identify')
    try:
        j = json.loads(out.split('\n', 1)[0])
        r = j.get('result', {}) if j.get('ok') else j
        p('HOME %-38s' % home, 'ok=%s pid=%s instance=%s api=%s state=%s' % (
            j.get('ok'), r.get('pid'), r.get('instance_id'),
            r.get('api_origin'), r.get('state')))
    except Exception:
        p('HOME %-38s' % home, out[:300])

# 用两种 home 尝试签 native-http 票
for home in HOMES:
    out = q(home, 'identify')
    try:
        r = json.loads(out.split('\n', 1)[0]).get('result', {})
    except Exception:
        continue
    inst = r.get('instance_id')
    sp = r.get('served_profiles') or []
    pid = sp[0].get('profile_id') if sp and isinstance(sp[0], dict) else (sp[0] if sp else None)
    if not (inst and pid):
        p('TICKET %-38s' % home, 'SKIP (no instance/profile)')
        continue
    ans = q(home, 'session-ticket', {
        'profile_id': pid, 'instance_id': inst, 'purpose': 'native-http'})
    p('TICKET %-38s' % home, ans[:260])

# 13692 是谁
try:
    import psutil
    pr = psutil.Process(13692)
    p('PARENT 13692', '%s | %s | born=%s' % (
        pr.name(), ' '.join(pr.cmdline())[:220],
        datetime.datetime.fromtimestamp(pr.create_time()).strftime('%H:%M:%S')))
    p('PARENT children', [c.pid for c in pr.children()][:20])
except Exception as e:
    p('PARENT ERR', repr(e))

# control pointer 相关文件（Windows runtime bootstrap）
try:
    from gateway import runtime_bootstrap_windows as rb
    p('runtime_bootstrap_windows', rb.__file__)
    for attr in ('control_pointer_path', 'pointer_path', 'CONTROL_POINTER', '_pointer_path'):
        if hasattr(rb, attr):
            p('  attr ' + attr, str(getattr(rb, attr))[:200])
except Exception as e:
    p('rb import ERR', repr(e))

print('__V15_DONE__', flush=True)
