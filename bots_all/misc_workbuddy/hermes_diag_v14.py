# -*- coding: utf-8 -*-
"""v14：诊断冷启动后的 Electron 主进程是否挂起，以及桌面日志/网关现状。只读。"""
import os, sys, json, time, datetime, http.client
from pathlib import Path

ROOT = Path(r'E:\workbuddy\国外模型\hermes')
sys.path.insert(0, str(ROOT / 'hermes-agent'))
from hermes_cli.gateway_client import private_control_query

DESKLOG = ROOT / 'logs' / 'desktop.log'
GWLOG = ROOT / 'logs' / 'gateway.log'

def p(tag, val):
    print('[%s] %s' % (tag, val), flush=True)

def q(verb, params=None):
    raw = private_control_query(
        ROOT, (json.dumps({'protocol': 1, 'id': 1, 'verb': verb, 'params': params or {}}) + '\n').encode(),
        timeout=8)
    return json.loads(raw.decode('utf-8', 'replace').split('\n', 1)[0])

# 1. Hermes.exe 进程详情
try:
    import psutil
    rows = []
    for pr in psutil.process_iter(['pid', 'ppid', 'name', 'cmdline', 'create_time']):
        try:
            if (pr.info['name'] or '').lower() != 'hermes.exe':
                continue
            x = pr.info
            born = datetime.datetime.fromtimestamp(x['create_time']).strftime('%H:%M:%S') if x['create_time'] else '?'
            try:
                obj = psutil.Process(x['pid'])
                status = obj.status()
                children = len(obj.children(recursive=False))
                cpu = round(obj.cpu_percent(interval=0.3), 1)
                mem = round(obj.memory_info().rss / 1024 / 1024)
                opened = []
                for f in obj.open_files()[:6]:
                    opened.append(f.path)
            except Exception as e:
                status, children, cpu, mem, opened = 'ERR %r' % e, -1, -1, -1, []
            rows.append({'pid': x['pid'], 'ppid': x['ppid'], 'born': born, 'status': status,
                         'children': children, 'cpu': cpu, 'mem_mb': mem,
                         'cmd': ' '.join(x['cmdline'] or [])[:140], 'open_files': opened})
        except Exception:
            pass
    p('Hermes.exe count', len(rows))
    for r in rows:
        p('PROC', json.dumps(r, ensure_ascii=False)[:420])
    # 所有 hermes 相关的 python helper 计数
    helpers = 0
    for pr in psutil.process_iter(['name', 'cmdline', 'ppid']):
        try:
            if (pr.info['name'] or '').lower().startswith('python') and '-P -u -c' in ' '.join(pr.info['cmdline'] or []):
                helpers += 1
        except Exception:
            pass
    p('python -P -u -c helpers', helpers)
except Exception as e:
    p('PROC ERR', repr(e))

# 2. 日志状态
for label, path in (('desktop.log', DESKLOG), ('gateway.log', GWLOG)):
    try:
        st = path.stat()
        p(label, 'size=%d mtime=%s' % (
            st.st_size, datetime.datetime.fromtimestamp(st.st_mtime).strftime('%H:%M:%S')))
    except Exception as e:
        p(label + ' ERR', repr(e))

try:
    lines = DESKLOG.read_text(encoding='utf-8', errors='replace').splitlines()
    p('desktop.log tail_401_in_last_80', sum(1 for l in lines[-80:] if '401' in l))
    for l in lines[-8:]:
        p('DESK', l[:190])
except Exception as e:
    p('DESK ERR', repr(e))

# 3. 网关状态
try:
    ident = q('identify').get('result', {}) or {}
    p('gateway', 'pid=%s state=%s instance=%s port=%s' % (
        ident.get('pid'), ident.get('state'), ident.get('instance_id'), ident.get('api_origin')))
    aw = q('active-work').get('result', {}) or {}
    p('active-work', json.dumps({'active_agents': aw.get('active_agents'),
                                 'items': aw.get('active_work')}, ensure_ascii=False)[:600])
except Exception as e:
    p('GW ERR', repr(e))

print('__V14_DONE__', flush=True)
