# chanlun_analyzer.py — 金策宗师团 · 研究部 · 缠论结构几何层
"""
缠中说禅 (缠论) 程序化核心 — 自包含纯函数模块。

设计原则 (与金策宗师团 v4.0 铁律一致):
  - 单文件自包含: 自带 EMA/MACD, 不依赖 continuous_evolution_v2, 便于离线单测
  - 纯函数式: analyze(close, high, low) 只接受数组, 不碰 MT5 / 不读全局
  - 只做"结构几何分类 + 买卖点识别", 不参与风控/下单

算法流水线 (严格按缠论形态学 → 动力学):
  K线 → 包含处理 → 分型 → 笔 → 中枢 → 走势类型
        → MACD 背驰 → 一/二类买卖点

接入定位 (详见 chanlun_learning_report.md):
  P0 形态学 (本模块): 包含/分型/笔/中枢/走势类型
  P1 背驰+买卖点 (本模块): MACD 背驰 + 一/二类买卖点识别
  → 作为猎场司 gate 的"增强信号源", 只禁反向 + 确认, 中性放行, 绝不替代
    审度司 VETO / ADX<20 硬禁 / 信号质量门禁

注意背驰滞后性: 基于完整笔的背驰必在笔结束后才确认, 实盘需次级别配合;
本模块仅供 gate 过滤与人工复盘参考, 不做实时喊单。
"""
import numpy as np

# ── 笔划分最小间隔 (合并 K 线根数) ──
# 缠论严格: 分型间至少 4 根独立 K 线。此处计数的是"合并后 K 线",
# 等价但更稳 (合并已吃掉噪声包含)。不同品种可调, 默认 4。
MIN_BI_GAP = 4

# ── 背驰力度比较阈值 ──
# 后段面积需 < 前段面积的此比例 才判背驰 (0.70 较严格, 抑制趋势市假信号)
DIVERGE_RATIO = 0.70
# 后段价格相对前段需显著突破 (0.1%), 过滤极小波动的伪突破
PRICE_BREAK = 0.001


# ════════════════════════════════════════════════════════════
# 底层指标 (自包含, 不依赖外部)
# ════════════════════════════════════════════════════════════
def _ema(arr, period):
    """指数移动平均 (递推)。空数组返回空。"""
    arr = np.asarray(arr, dtype=float)
    n = len(arr)
    if n == 0:
        return np.array([])
    alpha = 2.0 / (period + 1.0)
    out = np.empty(n, dtype=float)
    out[0] = arr[0]
    for i in range(1, n):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out


def _macd(close, fast=12, slow=26, signal=9):
    """返回 (dif, dea, bar)。bar = 2*(dif-dea) 与主流软件一致。"""
    close = np.asarray(close, dtype=float)
    dif = _ema(close, fast) - _ema(close, slow)
    dea = _ema(dif, signal)
    bar = 2.0 * (dif - dea)
    return dif, dea, bar


# ════════════════════════════════════════════════════════════
# 形态学: 包含处理 → 分型 → 笔 → 中枢
# ════════════════════════════════════════════════════════════
def _merge_inclusion(highs, lows):
    """K 线包含处理 → 返回合并 K 线列表。

    每个元素: [high, low, start_idx, end_idx]
      start_idx/end_idx 为原始 K 线索引区间 (用于后续区间取 MACD)。
    合并方向由 "前一根独立 K 线" 与 "当前合并末根" 的相对位置决定:
      前低 → 上升 → 取 max(high), max(low) (高高)
      前高 → 下降 → 取 min(high), min(low) (低低)
    """
    n = len(highs)
    if n == 0:
        return []
    merged = [[float(highs[0]), float(lows[0]), 0, 0]]
    for i in range(1, n):
        h, l = float(highs[i]), float(lows[i])
        if len(merged) < 2:
            merged.append([h, l, i, i])
            continue
        last_h, last_l = merged[-1][0], merged[-1][1]
        prev_h = merged[-2][0]
        # 包含关系: 一根的高≥另一根高 且 低≤另一根低 (互为内外)
        contained = ((h >= last_h and l <= last_l) or
                     (h <= last_h and l >= last_l))
        if not contained:
            merged.append([h, l, i, i])
            continue
        # 合并: 方向由 prev 与 last 比较
        if prev_h <= last_h:        # 上升合并 → 取高
            new_h, new_l = max(last_h, h), max(last_l, l)
        else:                       # 下降合并 → 取低
            new_h, new_l = min(last_h, h), min(last_l, l)
        merged[-1] = [new_h, new_l, merged[-1][2], i]
    return merged


def _fenxing(merged):
    """在合并 K 线上找分型。返回 list of (idx_in_merged, type, price, src_i, src_e)。

    idx_in_merged: 分型在合并序列中的位置 (供笔划分用)
    src_i/src_e: 原始 K 线区间 (供背驰取 MACD 区间用)
    双严格判定 (高与低都严格) 减少噪声分型。
    """
    m = len(merged)
    fx = []
    for i in range(1, m - 1):
        a_h, a_l = merged[i - 1][0], merged[i - 1][1]
        b_h, b_l = merged[i][0], merged[i][1]
        c_h, c_l = merged[i + 1][0], merged[i + 1][1]
        if b_h > a_h and b_h > c_h and b_l > a_l and b_l > c_l:
            fx.append((i, 'TOP', b_h, merged[i][2], merged[i][3]))
        elif b_l < a_l and b_l < c_l and b_h < a_h and b_h < c_h:
            fx.append((i, 'BOTTOM', b_l, merged[i][2], merged[i][3]))
    return fx


def _bi_from_fenxing(fx, min_gap=MIN_BI_GAP):
    """从分型序列划分笔。返回 list of dict。

    规则:
      - 相邻笔必须反向 (顶→底 / 底→顶)
      - 相邻同向分型只保留极值 (取利润更优的端点)
      - 两分型合并索引间隔 >= min_gap 才能成笔
    每笔: {dir:'UP'|'DOWN', start_idx, end_idx, start_px, end_px,
           src_i, src_e}
      start_idx/end_idx 是合并序列索引; src_i/src_e 是原始 K 线索引。
    """
    if len(fx) < 2:
        return []
    bis = []
    prev = fx[0]
    for k in range(1, len(fx)):
        cur = fx[k]
        if cur[1] == prev[1]:
            # 同向: 保留极值
            if (cur[1] == 'TOP' and cur[2] > prev[2]) or \
               (cur[1] == 'BOTTOM' and cur[2] < prev[2]):
                prev = cur
            continue
        # 反向: 尝试成笔
        gap = cur[0] - prev[0]
        if gap >= min_gap:
            bis.append({
                'dir': 'UP' if prev[1] == 'BOTTOM' else 'DOWN',
                'start_idx': prev[0], 'end_idx': cur[0],
                'start_px': prev[2], 'end_px': cur[2],
                'src_i': prev[3], 'src_e': cur[4],
            })
            prev = cur
        else:
            # 间隔不足: 若 cur 更极端则更新 prev (否则忽略 cur)
            if (cur[1] == 'TOP' and cur[2] > prev[2]) or \
               (cur[1] == 'BOTTOM' and cur[2] < prev[2]):
                prev = cur
    return bis


def _zhongshu(bis):
    """在笔序列上找中枢 (连续 3 笔重叠)。返回 list of dict。

    ZG = min(三笔高点), ZD = max(三笔低点); ZD < ZG → 中枢成立。
    每中枢: {ZG, ZD, start, end}  (start/end 为合并序列索引)
    """
    zs = []
    for i in range(len(bis) - 2):
        b1, b2, b3 = bis[i], bis[i + 1], bis[i + 2]
        highs = [max(b1['start_px'], b1['end_px']),
                 max(b2['start_px'], b2['end_px']),
                 max(b3['start_px'], b3['end_px'])]
        lows = [min(b1['start_px'], b1['end_px']),
                min(b2['start_px'], b2['end_px']),
                min(b3['start_px'], b3['end_px'])]
        ZG = min(highs)
        ZD = max(lows)
        if ZD < ZG:
            zs.append({'ZG': ZG, 'ZD': ZD,
                       'start': b1['start_idx'], 'end': b3['end_idx']})
    return zs


# ════════════════════════════════════════════════════════════
# 动力学: 背驰 + 买卖点
# ════════════════════════════════════════════════════════════
def _macd_area(bar, src_i, src_e):
    """取某笔覆盖原始 K 线区间的 MACD 柱绝对值累加 (力度度量)。"""
    if src_e < src_i:
        src_i, src_e = src_e, src_i
    seg = bar[src_i:src_e + 1]
    if len(seg) == 0:
        return 0.0
    return float(np.sum(np.abs(seg)))


def _divergence(bis, bar):
    """MACD 背驰判定 (顶/底)。

    顶背驰: 相邻向上笔 (被反向笔隔开), 后笔价格显著新高 (突破>PRICE_BREAK),
            但 MACD 面积 < 前笔*DIVERGE_RATIO → 上涨动能衰竭
    底背驰: 相邻向下笔, 后笔价格显著新低, 但 MACD 面积 < 前笔*DIVERGE_RATIO
            → 下跌动能衰竭
    双阈值 (价格突破 + 面积严格萎缩) 抑制趋势市中的假背驰信号。
    返回 'TOP' / 'BOTTOM' / None (取最近一次)。
    """
    ups = [b for b in bis if b['dir'] == 'UP']
    downs = [b for b in bis if b['dir'] == 'DOWN']
    div = None
    for a, b in zip(ups[:-1], ups[1:]):
        price_break = (b['end_px'] - a['end_px']) / max(abs(a['end_px']), 1e-9)
        if price_break > PRICE_BREAK and b['end_px'] > a['end_px']:
            area_a = _macd_area(bar, a['src_i'], a['src_e'])
            area_b = _macd_area(bar, b['src_i'], b['src_e'])
            if area_a > 0 and area_b < area_a * DIVERGE_RATIO:
                div = 'TOP'
    for a, b in zip(downs[:-1], downs[1:]):
        price_break = (a['end_px'] - b['end_px']) / max(abs(a['end_px']), 1e-9)
        if price_break > PRICE_BREAK and b['end_px'] < a['end_px']:
            area_a = _macd_area(bar, a['src_i'], a['src_e'])
            area_b = _macd_area(bar, b['src_i'], b['src_e'])
            if area_a > 0 and area_b < area_a * DIVERGE_RATIO:
                div = 'BOTTOM'
    return div


def _buy_sell_points(bis, zs, div):
    """一/二类买卖点 (简化但完备, 基于中枢 + 背驰)。

    一类买 (1B): 下跌结构末端 — 存在底背驰 且 最后笔为向下
    二类买 (2B): 1B 后 出现向上笔 再 向下笔 未破 1B 低点 (回抽确认)
    三类买 (3B): 向上笔离开最近中枢 ZG 后, 回抽低点 >= ZG (突破确认)
    (卖点对称 1S/2S/3S)
    """
    bsp = None
    if len(bis) < 2:
        return None
    last = bis[-1]

    # —— 一类买卖点 ——
    if div == 'BOTTOM' and last['dir'] == 'DOWN':
        bsp = '1B'
    elif div == 'TOP' and last['dir'] == 'UP':
        bsp = '1S'

    # —— 二类买卖点 (需至少 4 笔: 1B后 上 下 或 1S后 下 上) ——
    if bsp in ('1B', '1S') and len(bis) >= 4:
        b0, b1, b2, b3 = bis[-4], bis[-3], bis[-2], bis[-1]
        if bsp == '1B':
            # 1B在 b1(向下), b2向上, b3向下且 b3终点 >= b1起点(未破前低)
            if (b1['dir'] == 'DOWN' and b2['dir'] == 'UP' and
                    b3['dir'] == 'DOWN' and b3['end_px'] >= b1['start_px']):
                bsp = '2B'
        else:  # 1S
            if (b1['dir'] == 'UP' and b2['dir'] == 'DOWN' and
                    b3['dir'] == 'UP' and b3['end_px'] <= b1['start_px']):
                bsp = '2S'

    # —— 三类买卖点 (中枢离开 + 回抽不回中枢) ——
    # 3B: 向上笔离开中枢(ZG 之上启动) 后, 向下回抽笔低点 >= ZG (突破确认)
    # 3S: 向下笔离开中枢(ZD 之下启动) 后, 向上回抽笔高点 <= ZD (跌破确认)
    if zs:
        z = zs[-1]
        if len(bis) >= 2:
            lb = bis[-1]
            prev = bis[-2]
            if (lb['dir'] == 'DOWN' and prev['dir'] == 'UP' and
                    prev['start_px'] >= z['ZG'] and lb['end_px'] >= z['ZG']):
                bsp = '3B'
            elif (lb['dir'] == 'UP' and prev['dir'] == 'DOWN' and
                  prev['start_px'] <= z['ZD'] and lb['end_px'] <= z['ZD']):
                bsp = '3S'

    return bsp


def _trend_type(bis, zs):
    """走势类型: UP / DOWN / SHOCK (盘整/震荡)。"""
    if len(bis) < 2:
        return 'SHOCK'
    # 看最后 3 笔方向序列
    last3 = bis[-3:]
    dirs = [b['dir'] for b in last3]
    # 价格端点
    last_end = bis[-1]['end_px']
    prev_start = bis[-1]['start_px']
    if last_end > prev_start and dirs[-1] == 'UP':
        return 'UP'
    if last_end < prev_start and dirs[-1] == 'DOWN':
        return 'DOWN'
    # 有中枢但方向不明显 → 盘整
    if zs:
        return 'SHOCK'
    return 'SHOCK'


# ════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════
def analyze(close, high, low, min_gap=MIN_BI_GAP, min_bars=60):
    """缠论结构分析主入口。

    参数:
      close/high/low: 1D 数组 (已清洗, 无 NaN)
      min_gap: 笔间隔 (合并 K 线根数)
      min_bars: 最少 K 线数, 不足返回中性
    返回 dict:
      {
        'ok':           bool      数据是否足够分析
        'trend_type':   'UP'/'DOWN'/'SHOCK'
        'zhongshu':     (ZD, ZG) or None
        'divergence':   'TOP'/'BOTTOM'/None
        'latest_bsp':   '1B'/'2B'/'3B'/'1S'/'2S'/'3S'/None
        'bi_count':     int
        'last_bi_dir':  'UP'/'DOWN'/None
        'struct_note':  str
      }
    """
    out = {
        'ok': False, 'trend_type': 'SHOCK', 'zhongshu': None,
        'divergence': None, 'latest_bsp': None, 'bi_count': 0,
        'last_bi_dir': None, 'struct_note': '',
    }
    try:
        close = np.asarray(close, dtype=float)
        high = np.asarray(high, dtype=float)
        low = np.asarray(low, dtype=float)
    except Exception:
        out['struct_note'] = '输入非数组'
        return out

    n = len(close)
    if n < min_bars or n < 10:
        out['struct_note'] = f'K线不足 ({n}<{min_bars})'
        return out
    # 去除首尾可能的 NaN
    if np.any(~np.isfinite(close)) or np.any(~np.isfinite(high)) \
            or np.any(~np.isfinite(low)):
        out['struct_note'] = '含非有限值'
        return out

    merged = _merge_inclusion(high, low)
    if len(merged) < 5:
        out['struct_note'] = '合并后K线不足, 无法分型'
        out['ok'] = True
        return out

    fx = _fenxing(merged)
    if len(fx) < 2:
        out['struct_note'] = '分型不足, 无法成笔'
        out['ok'] = True
        return out

    bis = _bi_from_fenxing(fx, min_gap=min_gap)
    if len(bis) < 2:
        out['struct_note'] = '笔不足, 无结构'
        out['ok'] = True
        return out

    zs = _zhongshu(bis)
    _, _, bar = _macd(close)
    div = _divergence(bis, bar)
    bsp = _buy_sell_points(bis, zs, div)
    tt = _trend_type(bis, zs)

    out.update({
        'ok': True,
        'trend_type': tt,
        'zhongshu': (zs[-1]['ZD'], zs[-1]['ZG']) if zs else None,
        'divergence': div,
        'latest_bsp': bsp,
        'bi_count': len(bis),
        'last_bi_dir': bis[-1]['dir'],
        'struct_note': (
            f'笔{len(bis)} 中枢{len(zs)} '
            f'走势{tt} 背驰{div or "-"} 买卖点{bsp or "-"}'),
    })
    return out


# ════════════════════════════════════════════════════════════
# 给猎场司 gate 用的便捷判定 (纯逻辑, 无副作用)
# ════════════════════════════════════════════════════════════
def gate_signal(cl, direction):
    """根据缠论分析 dict 与提案方向, 返回 (allowed: bool, tag: str, note: str)。

    规则 (增强非替代):
      - 缠论明确反向 (BUY 遇顶背驰/卖点; SELL 遇底背驰/买点) → 禁止
      - 缠论同向确认 (底背驰/买点配 BUY; 顶背驰/卖点配 SELL) → 强确认
      - 其余 (中性/无结构/无背驰) → 放行 (不强制要求买卖点, 避免漏单)
    """
    if cl is None or not cl.get('ok', False):
        return True, 'NEUTRAL_SKIP', '缠论无结论, 放行'
    div = cl.get('divergence')
    bsp = cl.get('latest_bsp')
    buy_pts = ('1B', '2B', '3B')
    sell_pts = ('1S', '2S', '3S')

    if direction == 'BUY':
        if div == 'TOP' or bsp in sell_pts:
            return False, 'REVERSE_BLOCK', f'缠论反向: 背驰{div} 买卖点{bsp}'
        if div == 'BOTTOM' or bsp in buy_pts:
            return True, 'BULLISH_CONFIRM', f'缠论看多确认: 背驰{div} 买卖点{bsp}'
        return True, 'NEUTRAL_ALLOW', '缠论中性, 放行'
    else:  # SELL
        if div == 'BOTTOM' or bsp in buy_pts:
            return False, 'REVERSE_BLOCK', f'缠论反向: 背驰{div} 买卖点{bsp}'
        if div == 'TOP' or bsp in sell_pts:
            return True, 'BEARISH_CONFIRM', f'缠论看空确认: 背驰{div} 买卖点{bsp}'
        return True, 'NEUTRAL_ALLOW', '缠论中性, 放行'


def chanlun_stop(side, zhongshu, buffer_frac=0.001):
    """中枢动态止损价 (缠论式结构防守)。

    参数:
      side:      'BUY' / 'SELL' (持仓方向)
      zhongshu:  analyze() 返回的 (ZD, ZG) 元组, 或 None
      buffer_frac: 缓冲比例 (中枢边界外再留 0.1% 余量, 防毛刺扫损)
    返回:
      float SL 价, 或 None (无中枢 / 中枢无效)

    逻辑 (P2 开仓侧精准止损源):
      多单 BUY:  止损置于中枢上沿 ZG 下方 buffer → 跌破中枢即离场 (结构破位)
      空单 SELL: 止损置于中枢下沿 ZD 上方 buffer → 突破中枢即离场
    注意: 中枢边界需位于入场价"外部"才有意义 (多单 ZG<entry),
          方向合理性由调用方 (_apply_chanlun_sl) 校验, 本函数只算价。
    """
    if zhongshu is None:
        return None
    try:
        ZD, ZG = zhongshu
        ZD = float(ZD)
        ZG = float(ZG)
    except (TypeError, ValueError):
        return None
    if not (ZD < ZG):
        return None  # 中枢无效
    if side == 'BUY':
        return ZG * (1.0 - buffer_frac)
    elif side == 'SELL':
        return ZD * (1.0 + buffer_frac)
    return None


if __name__ == '__main__':
    print("chanlun_analyzer: 自包含缠论结构层, import 使用 analyze()/gate_signal()")
