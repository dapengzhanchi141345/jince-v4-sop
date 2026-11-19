# backtest_rf_threshold.py — P1-C: RF 准入门槛回测 (金策宗师团·研策师)
"""
验证: "提高 RF 准入门槛是否提胜率/PF (确定性过滤)"。
方法 (self-consistent, 无未来函数):
  - 对每个品种取 H1 历史, 滚动训练 RFAlpha(H1, 消费 RFAlpha 自带因果特征+错位标签)
  - 对第 t 根 score 得 UP/DOWN 概率, 若 max(UP,DOWN) >= 阈值 → 虚拟押该方向
  - 持仓 n_future=20 根 H1, 结算用 RFAlpha 标签定义 (未来 N 根极值偏移):
        up_exc = (max(high[t+1:t+N+1])-close[t])/close[t]
        dn_exc = (close[t]-min(low[t+1:t+N+1]))/close[t]
      押 UP 盈利=up_exc(若 up_exc>dn_exc) 否则 -dn_exc; DOWN 反之
  → 与 RFAlpha 训练标签完全一致, 无泄漏。
  - 多阈值 [0.50,0.55,0.60,0.65,0.70] 模拟准入, 对比 n/wr/pf/expectancy
DRY-RUN, 不下单, 不影响 live。
"""
import json
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime as dt
import rf_alpha as ra
import continuous_evolution_v2 as ce  # SYMBOL_CONFIG

THRESHOLDS = [0.50, 0.55, 0.60, 0.65, 0.70]
N_FUTURE = 20          # 与 RFAlpha 默认 n_future 一致
TRAIN_WINDOW = 300      # 与 RFAlpha 默认 train_window 一致
RETRAIN_EVERY = 50      # 每 50 根 H1 重训一次 (降计算, 模型泛化足够)
H1_BARS = 2500          # ~3.5 个月 H1 历史


def load_h1(sym):
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, H1_BARS)
    if rates is None or len(rates) < TRAIN_WINDOW + N_FUTURE + 10:
        return None
    c = np.array([r['close'] for r in rates], float)
    h = np.array([r['high'] for r in rates], float)
    l = np.array([r['low'] for r in rates], float)
    return c, h, l


def backtest_sym(sym):
    data = load_h1(sym)
    if data is None:
        return {'symbol': sym, 'error': 'no data / too short'}
    c, h, l = data
    n = len(c)
    # Walk-forward 简化: 前 60% 训练, 后 40% 测试打分.
    # 设计说明: live 的 RFAlpha 是懒训练+缓存(_rf_models 不滚动重训),
    #   故一次性训练比滚动重训更贴近真实行为; 且规避 sklearn 频繁
    #   建/销 RandomForest 的 C 层累积崩溃(已实测: 滚动50次训练+2180次
    #   score 在 t~1500-2000 触发 segfault, 单 model 全长度 score 正常).
    split = int(n * 0.6)
    if split < TRAIN_WINDOW + N_FUTURE:
        return {'symbol': sym, 'error': 'too short for split'}
    model = ra.RFAlpha()
    if not model.fit((c[:split], h[:split], l[:split])):
        return {'symbol': sym, 'error': 'RF untrainable on train split'}
    stats = {thr: {'n': 0, 'w': 0, 'exc': []} for thr in THRESHOLDS}
    for t in range(split, n - N_FUTURE):
        sc = model.score(c[:t + 1], h[:t + 1], l[:t + 1])
        if sc is None:
            continue
        up, down = sc['UP'], sc['DOWN']
        pmax = max(up, down)
        direction = 'UP' if up >= down else 'DOWN'
        # 结算 t+1..t+N (严格错位, 不含 t)
        fh = float(np.max(h[t + 1:t + 1 + N_FUTURE]))
        fl = float(np.min(l[t + 1:t + 1 + N_FUTURE]))
        base = c[t]
        up_exc = (fh - base) / base
        dn_exc = (base - fl) / base
        for thr in THRESHOLDS:
            if pmax >= thr:
                if direction == 'UP':
                    win = up_exc > dn_exc
                    ret = up_exc if win else -dn_exc
                else:
                    win = dn_exc > up_exc
                    ret = dn_exc if win else -up_exc
                s = stats[thr]
                s['n'] += 1
                if win:
                    s['w'] += 1
                s['exc'].append(ret)
    out = {'symbol': sym, 'n_total': n, 'train_split': split}
    for thr in THRESHOLDS:
        s = stats[thr]
        nn = s['n']
        if nn == 0:
            out[f'thr{thr}'] = {'n': 0}
            continue
        wr = s['w'] / nn
        ex = np.array(s['exc'], dtype=float)
        gross_w = float(ex[ex > 0].sum()) if (ex > 0).any() else 0.0
        gross_l = float(-ex[ex < 0].sum()) if (ex < 0).any() else 0.0
        pf = (gross_w / gross_l) if gross_l > 0 else float('inf')
        out[f'thr{thr}'] = {
            'n': nn, 'wr': round(wr, 3),
            'pf': round(pf, 3), 'expectancy': round(float(ex.mean()), 5),
        }
    return out


def main():
    import sys
    # --symbol SYM: 单品种独立进程模式 (供 driver 逐个调用, 规避 sklearn
    #   单进程累积 segfault — 实测第 3 个品种训练时 C 层崩; 独立进程干净).
    sym_arg = None
    if '--symbol' in sys.argv:
        try:
            sym_arg = sys.argv[sys.argv.index('--symbol') + 1]
        except Exception:
            sym_arg = None
    if not mt5.initialize():
        print(json.dumps({'error': 'MT5 init failed'}))
        return
    if sym_arg:
        r = backtest_sym(sym_arg)
        mt5.shutdown()
        print(json.dumps({'generated': dt.now().isoformat(timespec='seconds'),
                          'symbol': sym_arg, 'result': r},
                         ensure_ascii=False, indent=2))
        return
    # 全部品种 (driver 应改用 --symbol 逐个调用)
    out = {'generated': dt.now().isoformat(timespec='seconds'),
           'n_future': N_FUTURE, 'train_window': TRAIN_WINDOW,
           'thresholds': THRESHOLDS, 'symbols': {}}
    for sym in ce.SYMBOL_CONFIG.keys():
        try:
            out['symbols'][sym] = backtest_sym(sym)
        except Exception as e:
            out['symbols'][sym] = {'symbol': sym, 'error': str(e)}
    mt5.shutdown()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
