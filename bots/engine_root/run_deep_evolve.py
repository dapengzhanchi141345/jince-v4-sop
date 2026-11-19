import time, json
import continuous_evolution_v2 as ce

t0 = time.time()
for sym in ['EURUSD', 'GBPUSD', 'USDJPY']:
    print(f'\n########## 深度进化 {sym} (400轮) ##########', flush=True)
    try:
        r = ce.run_continuous_evolution(symbol=sym, max_rounds=400)
    except Exception as e:
        print(f'  ERROR {sym}: {e!r}', flush=True)
        continue
    b = r.get(sym)
    print(f'  -> {sym}: {b["name"] if b else None} '
          f'fit={b["fitness"] if b else 0} '
          f'base={b["baseline"] if b else None}', flush=True)
print(f'\nALL DONE in {time.time()-t0:.1f}s', flush=True)

st = json.load(open('data/continuous_evolution/evolution_state.json'))
print('=== 更新后逐品种 fitness ===', flush=True)
for s, v in st['best_per_symbol'].items():
    print(f'  {s}: {v["name"] if v else None} fit={v["fitness"] if v else 0} '
          f'base={v["baseline"] if v else None}', flush=True)
