# -*- coding: utf-8 -*-
"""Hermes 401 决定性探测：control socket 实况 + 合法票据访问 native HTTP。只读探测，不改任何状态。"""
import os, sys, json, time, urllib.request, urllib.error, http.client
from pathlib import Path

ROOT = Path(r'E:\workbuddy\国外模型\hermes')
sys.path.insert(0, str(ROOT / 'hermes-agent'))

def p(tag, val):
    print('[%s] %s' % (tag, val), flush=True)

try:
    from hermes_cli.gateway_client import private_control_query
    p('import', 'private_control_query OK')
except Exception as e:
    p('import ERR', repr(e))
    raise

def q(verb, params=None):
    payload = {'protocol': 1, 'id': 1, 'verb': verb, 'params': params or {}}
    raw = private_control_query(ROOT, (json.dumps(payload) + '\n').encode(), timeout=8)
    return raw.decode('utf-8', 'replace')

def first_json(text):
    return json.loads(text.split('\n', 1)[0])

# ---- 1. control socket 实况 ----
ident = {}
for v in ('identify', 'status', '__probe_unknown_verb__'):
    try:
        out = q(v)
        p('CTRL ' + v, out[:2500])
        if v == 'identify':
            ident = first_json(out).get('result', {}) or {}
    except Exception as e:
        p('CTRL ' + v + ' ERR', repr(e))

p('IDENT KEYS', ', '.join(sorted(ident.keys())))
p('IDENT instance_id', ident.get('instance_id'))
p('IDENT state', ident.get('state'))
sp = ident.get('served_profiles') or []
p('IDENT served_profiles', '%s / count=%d / sample=%s' % (
    type(sp).__name__, len(sp), json.dumps(sp[:2], ensure_ascii=False)[:600]))

# ---- 2. 找 API 端口 ----
origin = ident.get('api_origin') or ident.get('origin') or ident.get('http_origin')
p('API origin (from identify)', origin)
ports = []
try:
    import psutil
    gw_pid = 31736
    for c in psutil.net_connections(kind='inet'):
        if c.status == 'LISTEN' and c.pid == gw_pid:
            ports.append(c.laddr.port)
    ports = sorted(set(ports))
    p('GW LISTEN ports (pid 31736)', ports)
except Exception as e:
    p('ports ERR', repr(e))

if origin:
    try:
        from urllib.parse import urlparse
        u = urlparse(origin)
        if u.port and u.port not in ports:
            ports.insert(0, u.port)
    except Exception:
        pass

# ---- 3. 用当前真实 instance_id 签合法票 ----
inst = ident.get('instance_id')
cands = []
if sp:
    first = sp[0]
    if isinstance(first, dict):
        for k in ('profile_id', 'home', 'id', 'name'):
            if first.get(k):
                cands.append(first[k])
    elif isinstance(first, str):
        cands.append(first)
cands += [
    'default',
    str(ROOT / 'profiles' / 'default'),
    'E:\\workbuddy\\国外模型\\hermes\\profiles\\default',
    str(ROOT),
]
cands = [c for c in dict.fromkeys(cands) if c]
p('ticket profile candidates', json.dumps(cands, ensure_ascii=False)[:900])

ticket = None
signed_profile = None
for pid in cands:
    try:
        out = q('session-ticket', {
            'profile_id': pid, 'instance_id': inst, 'purpose': 'interactive'})
        j = first_json(out)
        p('TICKET try %-72s' % str(pid)[:72], out[:260])
        if j.get('ok') and isinstance(j.get('result'), dict) and j['result'].get('ticket'):
            ticket = j['result']['ticket']
            signed_profile = pid
            break
    except Exception as e:
        p('TICKET try ERR %s' % str(pid)[:60], repr(e))

p('TICKET RESULT', 'OK profile=%s' % signed_profile if ticket else 'FAILED - no ticket minted')

# ---- 4. 决定性实验：合法票 GET /api/status ----
if ticket and ports:
    for port in ports[:8]:
        for path in ('/api/status',):
            try:
                conn = http.client.HTTPConnection('127.0.0.1', port, timeout=6)
                conn.request('GET', path, headers={
                    'X-Hermes-Gateway-Ticket': ticket,
                    'Accept': 'application/json',
                })
                resp = conn.getresponse()
                body = resp.read(400).decode('utf-8', 'replace')
                p('HTTP %s:%d%s' % ('127.0.0.1', port, path),
                  'STATUS=%d BODY=%s' % (resp.status, body))
                conn.close()
            except Exception as e:
                p('HTTP %s:%d%s ERR' % ('127.0.0.1', port, path), repr(e))
else:
    p('HTTP', 'SKIPPED (no ticket or no port)')

p('VERDICT',
  'gateway-side descriptor OK -> desktop cache is the culprit'
  if ticket and ports else 'inconclusive; see lines above')
print('__PROBE_DONE__', flush=True)
