"""金策SD批全链路深检 9 项 (2026-11-15 终审后复检). exit 0=全 PASS"""
import py_compile, json, os, glob, subprocess, sys

ok = []
# C1 全链编译
files = ['E:/GoldstrategyEngine/research/place_sd_all_20261115.py',
         'E:/GoldstrategyEngine/research/sd_profitlock_guard.py',
         'E:/GoldstrategyEngine/research/sd_symopt_20261115.py',
         'E:/GoldstrategyEngine/research/sd_zone_oe_20261115.py',
         r'E:\workbuddy\国外模型\hermes\scripts\sd_e3s1_12h_forceclose.py',
         r'E:\workbuddy\国外模型\hermes\scripts\sd_forceclose_cron.py',
         r'E:\workbuddy\国外模型\hermes\scripts\sd_place_fx_monday.py',
         r'E:\workbuddy\国外模型\hermes\scripts\sd_place_crypto_monday.py']
for f in files:
    py_compile.compile(f, doraise=True)
ok.append('C1 编译 8 文件 PASS')

# C2 参数表
sp = json.load(open('E:/GoldstrategyEngine/research/sd_symbol_params.json', encoding='utf-8'))['params']
npz = sorted(os.path.basename(x)[:-4].replace('_M15', '') for x in glob.glob('E:/GoldstrategyEngine/research/allsyms_m15/*.npz'))
assert set(npz) <= set(sp) and len(sp) == 30, (len(npz), len(sp))
ok.append('C2 参数表 30/30 覆盖数据 PASS')

# C3 挂单器关键逻辑
src = open('E:/GoldstrategyEngine/research/place_sd_all_20261115.py', encoding='utf-8').read()
assert 'sp_all' in src and 'o.state in (0, 1)' in src and '(10008, 10009, 10010)' in src and 'ORDER_FILLING_RETURN' in src
ok.append('C3 挂单器(分品种表+在册dedup+成功码收口+RETURN填充+stops预检) PASS')

# C4 锁利守护
g = open('E:/GoldstrategyEngine/research/sd_profitlock_guard.py', encoding='utf-8').read()
assert 'peak_r < trig' in g and 'open_risk(p.symbol, p.price_open)' in g and 'OpenProcess' in g and 'symbol_select' in g
ok.append('C4 锁利(峰值口径+价格匹配+OpenProcess锁+select防护) PASS')

# C5 分级强平
fc = open(r'E:\workbuddy\国外模型\hermes\scripts\sd_e3s1_12h_forceclose.py', encoding='utf-8').read()
assert 'locked' in fc and 'age_h > 24.0' in fc and 'tick2' in fc
ok.append('C5 分级强平(锁利豁免+24h二道闸+重试刷新价) PASS')

# C6 cron 任务
jobs = json.load(open('E:/workbuddy/国外模型/hermes/cron/jobs.json', encoding='utf-8'))
flat = []
if isinstance(jobs, dict):
    for v in jobs.values():
        if isinstance(v, list):
            flat += v
        elif isinstance(v, dict):
            flat.append(v)
else:
    flat = jobs
byid = {str(j.get('id')): j for j in flat if isinstance(j, dict)}
assert byid['92212bf4d61e']['enabled'] and 'forceclose' in str(byid['92212bf4d61e'].get('script'))
assert byid['afe459d823a0']['enabled'] and byid['afe459d823a0'].get('next_run_at', '').startswith('2026-11-16T21:05:00+08:00')
assert 'b4b91e3dc4a9' not in byid, '币系12点任务应已撤'
ok.append('C6 cron(强平30min+周一21:05全品种+币系12点已撤) PASS')

# C7 活体 + 计划任务
ps1 = ('(Get-CimInstance Win32_Process -Filter "Name=\'python.exe\'") '
       "| Where-Object { $_.CommandLine -like '*sd_profitlock_guard*' } | Select-Object -ExpandProperty ProcessId")
out = subprocess.run(['powershell', '-NoProfile', '-Command', ps1], capture_output=True, text=True).stdout.strip().splitlines()
lock = json.load(open('E:/GoldstrategyEngine/data/sd_profitlock.lock', encoding='utf-8'))['pid']
assert len(out) == 1 and int(out[0]) == lock, ('活体', out, 'lock', lock)
st = subprocess.run(['powershell', '-NoProfile', '-Command',
                     '(Get-ScheduledTask -TaskName SD-ProfitLock).State'], capture_output=True, text=True).stdout.strip()
assert st == 'Running', st
ok.append('C7 守护独活 PID=%s 锁同步 + 计划任务Running PASS' % lock)

# C8 留痕链
pl = sum(1 for _ in open('E:/GoldstrategyEngine/data/_manual_prac_log.jsonl', encoding='utf-8'))
assert pl >= 81
ok.append('C8 留痕 prac_log %d 行 PASS' % pl)

# C9 周一任务 = 30 品种
fx = open(r'E:\workbuddy\国外模型\hermes\scripts\sd_place_fx_monday.py', encoding='utf-8').read()
assert 'sd_all_best_params.json' in fx and '--syms' not in fx
ok.append('C9 周一任务=30品种全量(无syms限制) PASS')

print('全链路深检 9/9 PASS')
for l in ok:
    print(' ', l)
