# -*- coding: utf-8 -*-
"""v16：逐字复刻桌面 TicketBridge helper 的签票逻辑，验证 primary/secondary profile 是否能签出票。只读。"""
import sys, json
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(r'E:\workbuddy\国外模型\hermes')
sys.path.insert(0, str(ROOT / 'hermes-agent'))
from hermes_cli.gateway_client import private_control_query, _session_ticket

def p(tag, val):
    print('[%s] %s' % (tag, val), flush=True)

def q(verb, params=None):
    raw = private_control_query(
        ROOT, (json.dumps({'protocol': 1, 'id': 1, 'verb': verb, 'params': params or {}}) + '\n').encode(),
        timeout=8)
    return json.loads(raw.decode('utf-8', 'replace').split('\n', 1)[0])

ident = q('identify').get('result', {}) or {}
inst = ident.get('instance_id')
sps = ident.get('served_profiles') or []
p('gateway', 'instance=%s runtime_protocol=%s served=%d' % (
    inst, ident.get('runtime_protocol'), len(sps)))

# 逐个复刻 helper 校验 + 签票（primary + 前 3 个 secondary）
for sp in sps[:4]:
    pid = sp.get('profile_id') if isinstance(sp, dict) else sp
    home = Path(pid)
    resolved = str(home.resolve())
    ok_path = (resolved == pid)
    p('CHECK %-62s' % str(pid)[-62:], 'resolve_equal=%s' % ok_path)
    ep = SimpleNamespace(profile_id=pid, instance_id=inst,
                         runtime_protocol=ident.get('runtime_protocol', 1),
                         control_home=None)
    try:
        t = _session_ticket(home, ep, purpose='native-http')
        p('  TICKET', 'OK %s...' % t[:18])
    except Exception as e:
        p('  TICKET', 'ERR %r' % e)

# 模拟"旧 instance_id"（网关重启前），看桌面会拿到什么错
p('--- stale instance_id simulation ---', '')
ep = SimpleNamespace(profile_id=sps[0]['profile_id'], instance_id='0' * 32,
                     runtime_protocol=1, control_home=None)
try:
    t = _session_ticket(Path(sps[0]['profile_id']), ep, purpose='native-http')
    p('  STALE TICKET', 'OK %s...' % t[:18])
except Exception as e:
    p('  STALE TICKET', 'ERR %r' % e)

# 模拟 "E:/hb" 形式 profile_id（若桌面 descriptor 存的是这个）
p('--- E:/hb style profile_id simulation ---', '')
for candidate in (r'E:/hb', r'E:\hb', 'default'):
    ep = SimpleNamespace(profile_id=candidate, instance_id=inst,
                         runtime_protocol=1, control_home=None)
    home = Path(candidate)
    try:
        same = str(home.resolve()) == candidate
    except Exception as e:
        same = 'ERR %r' % e
    p('  CAND %-14s' % candidate, 'resolve_equal=%s' % same)
    try:
        t = _session_ticket(home, ep, purpose='native-http')
        p('  CAND %-14s' % candidate, 'TICKET OK')
    except Exception as e:
        p('  CAND %-14s' % candidate, 'TICKET ERR %r' % e)

print('__V16_DONE__', flush=True)
