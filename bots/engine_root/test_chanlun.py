# test_chanlun.py — 缠论结构层离线单测 (不连 MT5)
import sys
import numpy as np
import chanlun_analyzer as cl


def _synth_bi_wave():
    """构造多段转折走势, 首尾留缓冲使转折点都在序列内部 (能形成完整分型)。

    内部转折点: 顶100 → 底85 → 顶110 → 底92 → 顶108 → 底95
    笔: DOWN UP DOWN UP DOWN (5 笔, 方向交替)
    连续 3 笔重叠 → 中枢; 整体对称 → 无背驰 (中性), 适合断言
    """
    pts = []
    # 段A 缓冲: 80→100 上升 40 根
    for i in range(40):
        p = 80 + 0.5 * i
        pts.append((p + 0.5, p - 0.5, p))
    # 段B: 100→85 下降 30 根
    for i in range(30):
        p = 100 - 0.5 * i
        pts.append((p + 0.5, p - 0.5, p))
    # 段C: 85→110 上升 30 根
    for i in range(30):
        p = 85 + 0.833 * i
        pts.append((p + 0.5, p - 0.5, p))
    # 段D: 110→92 下降 30 根
    for i in range(30):
        p = 110 - 0.6 * i
        pts.append((p + 0.5, p - 0.5, p))
    # 段E: 92→108 上升 30 根
    for i in range(30):
        p = 92 + 0.533 * i
        pts.append((p + 0.5, p - 0.5, p))
    # 段F: 108→95 下降 30 根
    for i in range(30):
        p = 108 - 0.433 * i
        pts.append((p + 0.5, p - 0.5, p))
    # 段G 缓冲: 95→105 上升 40 根
    for i in range(40):
        p = 95 + 0.25 * i
        pts.append((p + 0.5, p - 0.5, p))
    high = np.array([x[0] for x in pts])
    low = np.array([x[1] for x in pts])
    close = np.array([x[2] for x in pts])
    return close, high, low


def run():
    try:
        # 1. 包含处理: 3 根 K 线, 第 2 根被第 1/3 包 → 合并为 2 根
        h = np.array([10.0, 9.5, 9.8])
        l = np.array([8.0, 8.5, 8.2])
        merged = cl._merge_inclusion(h, l)
        assert len(merged) == 2, f"包含处理应并 3→2, 实际 {len(merged)}"
        assert abs(merged[-1][0] - 9.5) < 1e-9 and abs(merged[-1][1] - 8.2) < 1e-9, \
            f"合并末根应为 (9.5,8.2), 实际 {merged[-1][:2]}"
        # 无包含序列应保持独立
        h2 = np.array([8.0, 10.0, 7.0])
        l2 = np.array([6.0, 9.0, 5.0])
        merged2 = cl._merge_inclusion(h2, l2)
        assert len(merged2) == 3, "无包含应保留 3 根"

        # 2. 分型: 顶/底分型识别
        fh = np.array([8.0, 10.0, 7.0])
        fl = np.array([6.0, 9.0, 5.0])
        fx = cl._fenxing(cl._merge_inclusion(fh, fl))
        types = [f[1] for f in fx]
        assert 'TOP' in types, f"应识别顶分型, 实际 {types}"
        # 底分型
        bh = np.array([10.0, 6.0, 10.0])
        bl = np.array([9.0, 5.0, 9.0])
        fx2 = cl._fenxing(cl._merge_inclusion(bh, bl))
        assert 'BOTTOM' in [f[1] for f in fx2], "应识别底分型"

        # 3. 笔划分 + 中枢 (用合成波)
        c, hi, lo = _synth_bi_wave()
        merged3 = cl._merge_inclusion(hi, lo)
        fx3 = cl._fenxing(merged3)
        bis = cl._bi_from_fenxing(fx3, min_gap=2)
        assert len(bis) >= 3, f"应至少 3 笔, 实际 {len(bis)}"
        dirs = [b['dir'] for b in bis]
        # 方向应交替 (首笔方向取决于首个分型位置, 不强制)
        for i in range(1, len(bis)):
            assert bis[i]['dir'] != bis[i - 1]['dir'], \
                f"笔方向应交替, 在 {i} 处 {bis[i-1]['dir']}->{bis[i]['dir']}"
        zs = cl._zhongshu(bis)
        assert len(zs) >= 1, "应识别至少 1 个中枢"
        assert zs[-1]['ZD'] < zs[-1]['ZG'], \
            f"中枢应 ZD<ZG, 实际 ZD={zs[-1]['ZD']} ZG={zs[-1]['ZG']}"

        # 4. 背驰 (底层直接构造 bis + bar)
        # 顶背驰: 两向上笔, 后笔价格新高但 MACD 面积小
        bis_up = [
            {'dir': 'UP', 'start_px': 80, 'end_px': 100, 'src_i': 0, 'src_e': 10},
            {'dir': 'UP', 'start_px': 90, 'end_px': 105, 'src_i': 20, 'src_e': 30},
        ]
        bar = np.zeros(40)
        bar[0:11] = 2.0     # A 面积 22
        bar[20:31] = 0.5    # B 面积 5.5 < 22*0.85
        assert cl._divergence(bis_up, bar) == 'TOP', "应识别顶背驰"
        # 底背驰: 两向下笔, 后笔价格新低但面积小
        bis_dn = [
            {'dir': 'DOWN', 'start_px': 100, 'end_px': 80, 'src_i': 0, 'src_e': 10},
            {'dir': 'DOWN', 'start_px': 95, 'end_px': 70, 'src_i': 20, 'src_e': 30},
        ]
        bar2 = np.zeros(40)
        bar2[0:11] = 2.0
        bar2[20:31] = 0.5
        assert cl._divergence(bis_dn, bar2) == 'BOTTOM', "应识别底背驰"
        # 无背驰: 后笔力度更大 → None
        bar3 = np.zeros(40)
        bar3[0:11] = 0.5
        bar3[20:31] = 2.0
        assert cl._divergence(bis_up, bar3) is None, "力度增强不应判背驰"

        # 5. 买卖点 (底层构造)
        # 1B: 末端向下笔 + 底背驰
        bis_1b = [
            {'dir': 'UP', 'start_px': 80, 'end_px': 100, 'src_i': 0, 'src_e': 5},
            {'dir': 'DOWN', 'start_px': 100, 'end_px': 85, 'src_i': 5, 'src_e': 10},
            {'dir': 'UP', 'start_px': 85, 'end_px': 95, 'src_i': 10, 'src_e': 15},
            {'dir': 'DOWN', 'start_px': 95, 'end_px': 90, 'src_i': 15, 'src_e': 20},
        ]
        assert cl._buy_sell_points(bis_1b, [], 'BOTTOM') == '1B', "应判 1B"
        # 2B: 1B 后 上 下 未破前低
        bis_2b = bis_1b + [
            {'dir': 'UP', 'start_px': 90, 'end_px': 98, 'src_i': 20, 'src_e': 25},
            {'dir': 'DOWN', 'start_px': 98, 'end_px': 96, 'src_i': 25, 'src_e': 30},
        ]
        assert cl._buy_sell_points(bis_2b, [], 'BOTTOM') == '2B', "应判 2B"
        # 3B: 向上离开中枢 + 回抽不破 ZG
        zs3 = [{'ZG': 100, 'ZD': 95, 'start': 0, 'end': 10}]
        bis_3b = [
            {'dir': 'DOWN', 'start_px': 108, 'end_px': 99, 'src_i': 0, 'src_e': 5},
            {'dir': 'UP', 'start_px': 100, 'end_px': 115, 'src_i': 5, 'src_e': 10},
            {'dir': 'DOWN', 'start_px': 115, 'end_px': 102, 'src_i': 10, 'src_e': 15},
        ]
        assert cl._buy_sell_points(bis_3b, zs3, None) == '3B', "应判 3B"
        # 3S 对称
        zs3s = [{'ZG': 105, 'ZD': 100, 'start': 0, 'end': 10}]
        bis_3s = [
            {'dir': 'UP', 'start_px': 95, 'end_px': 106, 'src_i': 0, 'src_e': 5},
            {'dir': 'DOWN', 'start_px': 100, 'end_px': 90, 'src_i': 5, 'src_e': 10},
            {'dir': 'UP', 'start_px': 90, 'end_px': 98, 'src_i': 10, 'src_e': 15},
        ]
        assert cl._buy_sell_points(bis_3s, zs3s, None) == '3S', "应判 3S"

        # 6. gate_signal 逻辑
        cl_top = {'ok': True, 'divergence': 'TOP', 'latest_bsp': None}
        cl_bot = {'ok': True, 'divergence': 'BOTTOM', 'latest_bsp': None}
        cl_1b = {'ok': True, 'divergence': None, 'latest_bsp': '1B'}
        assert cl.gate_signal(cl_top, 'BUY')[0] is False, "BUY遇顶背驰应禁"
        assert cl.gate_signal(cl_bot, 'SELL')[0] is False, "SELL遇底背驰应禁"
        assert cl.gate_signal(cl_bot, 'BUY')[1] == 'BULLISH_CONFIRM', "BUY遇底背驰应确认"
        assert cl.gate_signal(cl_1b, 'BUY')[1] == 'BULLISH_CONFIRM', "BUY遇1B应确认"
        assert cl.gate_signal({'ok': False}, 'BUY')[0] is True, "无结论应放行"
        # 中性 (无背驰无买卖点) 放行
        cl_neu = {'ok': True, 'divergence': None, 'latest_bsp': None}
        assert cl.gate_signal(cl_neu, 'BUY')[0] is True, "中性应放行"

        # 7. 端到端 analyze
        res = cl.analyze(c, hi, lo)
        assert res['ok'] is True, f"analyze 应 ok, 实际 {res}"
        assert res['bi_count'] >= 3, f"应识别多笔, 实际 {res['bi_count']}"
        assert 'trend_type' in res and res['trend_type'] in ('UP', 'DOWN', 'SHOCK')
        # 不足 K 线 → 中性
        res2 = cl.analyze(c[:10], hi[:10], lo[:10])
        assert res2['ok'] is False, "K线不足应 ok=False"

        # 8. 中枢动态止损价 chanlun_stop (P2)
        assert cl.chanlun_stop('BUY', (90.0, 100.0)) == 99.9, \
            "BUY 中枢SL应为 ZG*(1-0.001)"
        assert abs(cl.chanlun_stop('SELL', (90.0, 100.0)) - 90.09) < 1e-9, \
            "SELL 中枢SL应为 ZD*(1+0.001)"
        assert cl.chanlun_stop('BUY', None) is None, "无中枢应返回 None"
        assert cl.chanlun_stop('BUY', (100.0, 90.0)) is None, \
            "无效中枢(ZD>=ZG)应返回 None"

        print("SELFTEST PASS: 13/13 缠论结构层通过 "
              "(包含/分型/笔/中枢/顶背驰/底背驰/1B/2B/3B/3S/gate/端到端/中枢止损价)")
        return True
    except AssertionError as e:
        print("SELFTEST FAIL:", e)
        return False
    except Exception as e:
        print("SELFTEST ERROR:", repr(e))
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
