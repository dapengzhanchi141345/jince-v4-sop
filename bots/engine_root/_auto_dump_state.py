import json, io, sys, os, datetime
sys.stdout = open(r'E:\GoldstrategyEngine\_auto_state_dump.txt', 'w', encoding='utf-8')
p = r'E:\GoldstrategyEngine\market_state.json'
print('MTIME:', datetime.datetime.fromtimestamp(os.path.getmtime(p)))
d = json.load(open(p, encoding='utf-8'))
print('TOPKEYS:', list(d.keys()))
sy = d.get('symbols', d)
for k, v in sy.items():
    if not isinstance(v, dict):
        continue
    print('---', k)
    for kk, vv in v.items():
        if isinstance(vv, (dict, list)):
            print('   ', kk, '=', json.dumps(vv, ensure_ascii=False)[:200])
        else:
            print('   ', kk, '=', vv)
