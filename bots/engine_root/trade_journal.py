# trade_journal.py — 金策宗师团 · 运营合规部 · 度支司 (trade-journal)
"""
交易日志 + 自适应仓位 (吸收另一账号 GoldstrategyEngine 的
trade_journal → 自适应仓位设计, 改造后接入金策宗师团执行链)。

设计要点:
  - 每笔成交(FILL)与平仓(CLOSE)落盘 jsonl, 供复盘与绩效归因
    (路径: data/continuous_evolution/trade_journal.jsonl)
  - AdaptiveSizer: 读近 N 笔平仓, 算胜率/期望值 → 给仓位乘数
    (近况好→加仓, 近况差→砍仓, 期望为负且胜率低→暂停开仓)
  - 低风险增强: 只缩放已通过审度司 VETO 的仓位, 不绕过任何风控闸门

与对方系统的关键差异:
  对方: calc_smart_lot 用近 20 笔直接乘系数, 无显式暂停门。
  我们: 同样基于日志, 但加"期望为负且胜率低→硬暂停开仓"闸门,
        且与审度司 VETO 解耦 (自适应只管乘数/暂停, 风险上限仍由审度司把守)。
"""
import json
import os
import datetime


class TradeJournal:
    def __init__(self, path=None):
        if path is None:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'data', 'continuous_evolution',
                                'trade_journal.jsonl')
        self.path = path
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        except Exception:
            pass

    def _append(self, rec):
        try:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + '\n')
        except Exception:
            pass  # 日志写入失败绝不阻断交易

    def log_fill(self, symbol, direction, lot, price, sl, tp, sl_pts,
                 tp_pts, adx, equity, strategy, ticket=None):
        self._append({
            'type': 'FILL', 'ts': datetime.datetime.now().isoformat(),
            'symbol': symbol, 'direction': direction, 'lot': lot,
            'price': price, 'sl': sl, 'tp': tp,
            'sl_pts': sl_pts, 'tp_pts': tp_pts, 'adx': adx,
            'equity': equity, 'strategy': strategy, 'ticket': ticket,
        })

    def log_close(self, symbol, direction, profit, reason, ticket=None,
                  balance_before=None, balance_after=None):
        self._append({
            'type': 'CLOSE', 'ts': datetime.datetime.now().isoformat(),
            'symbol': symbol, 'direction': direction, 'profit': profit,
            'reason': reason, 'ticket': ticket,
            'balance_before': balance_before,
            'balance_after': balance_after,
        })

    def _read_closes(self, symbol=None, n=50):
        out = []
        if not os.path.exists(self.path):
            return out
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    if r.get('type') != 'CLOSE':
                        continue
                    if symbol is not None and r.get('symbol') != symbol:
                        continue
                    out.append(r)
        except Exception:
            return out
        return out[-n:]

    def stats(self, symbol=None, n=20):
        """返回近 n 笔平仓的胜率/期望值/仓位乘数。样本<5 视为冷启动, 乘数=1.0。"""
        closes = self._read_closes(symbol=symbol, n=n)
        if len(closes) < 5:
            return {'n': len(closes), 'win_rate': None,
                    'expectancy': None, 'lot_mult': 1.0}
        wins = [c for c in closes if float(c.get('profit', 0) or 0) > 0]
        losses = [c for c in closes if float(c.get('profit', 0) or 0) <= 0]
        win_rate = len(wins) / len(closes)
        gross_win = sum(float(c.get('profit', 0) or 0) for c in wins)
        gross_loss = sum(float(c.get('profit', 0) or 0) for c in losses)
        expectancy = (gross_win + gross_loss) / len(closes)
        if win_rate >= 0.55 and expectancy > 0:
            lot_mult = 1.3
        elif win_rate < 0.4 or expectancy <= 0:
            lot_mult = 0.5
        else:
            lot_mult = 1.0
        return {'n': len(closes), 'win_rate': round(win_rate, 3),
                'expectancy': round(expectancy, 4), 'lot_mult': lot_mult}


class AdaptiveSizer:
    """基于交易日志的自适应仓位: 近况好→加仓, 差→砍仓/暂停。低风险增强。"""

    def __init__(self, journal=None, window=20,
                 good_wr=0.55, bad_wr=0.4,
                 pause_min_n_sym=8, pause_min_n_all=12):
        self.j = journal or TradeJournal()
        self.window = window
        self.good_wr = good_wr
        self.bad_wr = bad_wr
        self.pause_min_n_sym = pause_min_n_sym
        self.pause_min_n_all = pause_min_n_all

    def lot_multiplier(self, symbol):
        """返回该品种(不足则全局)的仓位乘数 0.5/1.0/1.3"""
        s_sym = self.j.stats(symbol=symbol, n=self.window)
        if s_sym['n'] >= 5:
            return s_sym['lot_mult']
        s_all = self.j.stats(symbol=None, n=self.window)
        return s_all['lot_mult']

    def should_pause(self, symbol):
        """近况期望为负且胜率过低 → 硬暂停开仓 (仍过审度司, 只是信号层不产单)"""
        def _wr(s):
            return s['win_rate'] if s['win_rate'] is not None else 1.0
        s = self.j.stats(symbol=symbol, n=self.window)
        if (s['n'] >= self.pause_min_n_sym and s['expectancy'] is not None
                and s['expectancy'] <= 0 and _wr(s) < self.bad_wr):
            return True, f"品种 {symbol} 近 {s['n']} 笔期望 {s['expectancy']} 胜率 {_wr(s)} → 暂停"
        s_all = self.j.stats(symbol=None, n=self.window)
        if (s_all['n'] >= self.pause_min_n_all and s_all['expectancy'] is not None
                and s_all['expectancy'] <= 0 and _wr(s_all) < 0.35):
            return True, f"全局近 {s_all['n']} 笔期望 {s_all['expectancy']} 胜率 {_wr(s_all)} → 暂停"
        return False, ''
