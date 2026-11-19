import json, os
r = json.load(open('E:/GoldstrategyEngine/research/coin_hourwindow_test_20261114.json', encoding='utf-8'))
for s in ['BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD']:
    h = r['coins'][s]['hourly']
    prof = ' '.join(f"{int(k):02d}:{h[k]['abs_med']:.3f}" for k in sorted(h))
    print(s, prof)
print('jsonl exists:', os.path.exists('E:/GoldstrategyEngine/research/family_deep_study_log.jsonl'))
