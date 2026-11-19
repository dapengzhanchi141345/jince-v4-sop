# -*- coding: utf-8 -*-
"""v11：确认有效票据下的 REST 超时是否普遍 + 当前活跃工作 + 进程快照。只读探测。"""
import sys, json, time, http.client
from pathlib import Path

ROOT = Path(r'E:\workbuddy\国外模型\hermes')
sys.path.insert(0, str(ROOT / 'hermes-agent'))
from hermes_cli.gateway_client import private_control_query

def p(tag, val):
    print('[%s] %s' % (tag, val), flush=True)

def q(verb, params=None, timeout=8):
    raw = private_control_query(
        ROOT, (json.dumps({'protocol': 1, 'id': 1, 'verb': verb, 'params': params or {}}) + '\n').encode(),
        timeout=timeout)
    return raw.decode('utf-8', 'replace')

def first(text):
    return json.loads(text.split('\n', 1)[0])

# ---- 活跃工作 / 状态 ----
for verb in ('active-work', 'status'):
    try:
        p('CTRL ' + verb, q(verb)[:1200])
    except Exception as e:
        p('CTRL ' + verb + ' ERR', repr(e))

ident = first(q('identify')).get('result', {}) or {}
inst = ident.get('instance_id')
port = int(str(ident.get('api_origin') or 'http://127.0.0.1:61083').rsplit(':', 1)[1])
profiles = ident.get('served_profiles') or []
pid = profiles[0].get('profile_id') if isinstance(profiles[0], dict) else profiles[0]
p('gateway', 'instance=%s port=%s state=%s' % (inst, port, ident.get('state')))

# ---- 有效 native-http 票，探多个 endpoint ----
out = q('session-ticket', {'profile_id': pid, 'instance_id': inst, 'purpose': 'native-http'})
j = first(out)
if not j.get('ok'):
    p('MINT', 'FAILED ' + out[:300])
    raise SystemExit(0)

paths = ['/api/status', '/api/profiles', '/api/local-models/status', '/api/health']
for path in paths:
    # 每张票一次性，逐路径重新签
    o = q('session-ticket', {'profile_id': pid, 'instance_id': inst, 'purpose': 'native-http'})
    jj = first(o)
    if not jj.get('ok'):
        p('MINT for %s' % path, 'FAILED')
        continue
    tk = jj['result']['ticket']
    t0 = time.time()
    try:
        c = http.client.HTTPConnection('127.0.0.1', port, timeout=6)
        c.request('GET', path, headers={'X-Hermes-Gateway-Ticket': tk, 'Accept': 'application/json'})
        r = c.getresponse()
        body = r.read(300).decode('utf-8', 'replace')
        p('HTTP %-30s' % path, '%d (%.2fs) %s' % (r.status, time.time() - t0, body[:200]))
        c.close()
    except Exception as e:
        p('HTTP %-30s' % path, 'ERR (%.2fs) %r' % (time.time() - t0, e))

# ---- 进程快照 ----
try:
    import psutil
    rows = []
    for pr in psutil.process_iter(['pid', 'ppid', 'name', 'cmdline', 'create_time']):
        try:
            name = (pr.info['name'] or '').lower()
            cmd = ' '.join(pr.info['cmdline'] or [])
            if ('hermes' in name or 'hermes' in cmd.lower() or 'electron' in name):
                rows.append((pr.info['pid'], pr.info['ppid'], pr.info['name'], cmd[:170]))
        except Exception:
            pass
    p('PROC count', len(rows))
    for pid_, ppid, name, cmd in rows:
        p('PROC %s ppid=%s %s' % (pid_, ppid, name), cmd)
except Exception as e:
    p('PROC ERR', repr(e))

print('__V11_DONE__', flush=True)
