# -*- coding: utf-8 -*-
"""决定性实验 v10：用正确 purpose 签票访问 native HTTP，判定 401 到底出在网关还是桌面。只读探测。"""
import sys, json, http.client
from pathlib import Path

ROOT = Path(r'E:\workbuddy\国外模型\hermes')
sys.path.insert(0, str(ROOT / 'hermes-agent'))
from hermes_cli.gateway_client import private_control_query

def p(tag, val):
    print('[%s] %s' % (tag, val), flush=True)

def q(verb, params=None):
    raw = private_control_query(
        ROOT, (json.dumps({'protocol': 1, 'id': 1, 'verb': verb, 'params': params or {}}) + '\n').encode(),
        timeout=8)
    return raw.decode('utf-8', 'replace')

def first(text):
    return json.loads(text.split('\n', 1)[0])

ident = first(q('identify')).get('result', {}) or {}
inst = ident.get('instance_id')
port = int(str(ident.get('api_origin') or 'http://127.0.0.1:61083').rsplit(':', 1)[1])
profiles = ident.get('served_profiles') or []
pid = profiles[0].get('profile_id') if isinstance(profiles[0], dict) else profiles[0]
p('instance_id', inst)
p('api_port', port)
p('descriptor.state', ident.get('state'))
p('descriptor.capabilities', ident.get('capabilities'))
p('descriptor.authority_epoch', ident.get('authority_epoch'))
p('served_profiles count', len(profiles))
p('ticket profile_id', pid)

def get(path, ticket, extra_headers=None):
    h = {'X-Hermes-Gateway-Ticket': ticket, 'Accept': 'application/json'}
    if extra_headers:
        h.update(extra_headers)
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=8)
    try:
        conn.request('GET', path, headers=h)
        r = conn.getresponse()
        return r.status, r.read(500).decode('utf-8', 'replace')
    finally:
        conn.close()

# 逐个 purpose 签票并请求 /api/status
for purpose in ('native-http', 'interactive', 'native-profile-create'):
    try:
        out = q('session-ticket', {'profile_id': pid, 'instance_id': inst, 'purpose': purpose})
        j = first(out)
        if not j.get('ok'):
            p('MINT %-24s' % purpose, 'FAILED: ' + out[:240])
            continue
        ticket = j['result']['ticket']
        p('MINT %-24s' % purpose, 'OK')
        for path in ('/api/status',):
            try:
                code, body = get(path, ticket)
                p('HTTP %-24s %s' % (purpose, path), '%d %s' % (code, body[:300]))
            except Exception as e:
                p('HTTP %-24s ERR' % purpose, repr(e))
    except Exception as e:
        p('MINT %-24s ERR' % purpose, repr(e))

# 无票 / 双票 / 带 Origin 的对照，用于区分 gate 与 redeem 两条 401 来源
try:
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=8)
    conn.request('GET', '/api/status', headers={'Accept': 'application/json'})
    r = conn.getresponse()
    p('CONTROL no-ticket', '%d %s' % (r.status, r.read(200).decode('utf-8', 'replace')))
    conn.close()
except Exception as e:
    p('CONTROL no-ticket ERR', repr(e))

print('__V10_DONE__', flush=True)
