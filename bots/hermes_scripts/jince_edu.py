#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策宗师团 · 会议技能教学层 (2026-10-08 用户令"全面深度优化会议内容 言之有物 提升操盘手技能")
设计: 共享模块, 被 jince_node.py(6开/关评) + jince_midday_deep.py(3中间) 复用, 单一事实源不复制.
0 LLM / 429-proof / 全从实数算(advisory 的 stop/target/price + edge_tracker 的 pf/WR + setup 词).
输出 3 条"可练技能", 每条=大白话结论 + 实数依据 + 操盘手该怎么做(不给方向指令, 只教纪律/方法):
  L1 盈亏比实算: 拿当前 top 品种真实 stop/target 算 RR, 教"RR≥2 才值得进、<1.5 不追"的量化口
  L2 弃负期望腿: 拿 edge_tracker 里 pf 最低的实盘腿, 教"数据判负的腿要放弃"的止损纪律
  L3 形态白话: 把真实 setup/patterns 翻成操盘手人话 + 该形态的操作纪律(不荐方向, 讲方法)
"""
import os, json, time, datetime, zoneinfo

DATA = r"E:/GoldstrategyEngine/data"
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")

def jget(path, default):
    try:
        return json.load(open(os.path.join(DATA, path), encoding="utf-8"))
    except Exception:
        return default

# setup/patterns 词 -> 操盘手白话 + 操作纪律 (词从 7 天 advisory 真实分布提炼, 不编造)
SETUP_CN = {
    "double_top": ("双顶(两个高点排开, 价已往下拐)", "到第二个顶就减/反手, 别追第一顶的价"),
    "double_top_confirmed": ("双顶已确认(跌破两顶间的颈线)", "确认后才算数, 没破颈线只是预警"),
    "double_bottom": ("双底(两个低点排开, 价要往上拐)", "到第二底才动手, 第一底是试探不是买"),
    "double_bottom_confirmed": ("双底已确认(站上两底间的颈线)", "站上颈线才确认, 没站上仍算反弹"),
    "head_shoulders_top": ("头肩顶(三峰中间最高, 反转信号)", "右肩不过头就成立, 破颈线才反手"),
    "head_shoulders_bottom": ("头肩底(倒过来的顶, 看涨)", "站上颈线才算反转, 没站上别接刀"),
    "ma_bull": ("价在均线上方(多头排列)", "只考虑顺势单, 逆势抄底是接刀"),
    "ma_bear": ("价在均线下方(空头排列)", "只考虑顺势单, 逆势摸顶是接刀"),
    "trend_up": ("上升趋势中", "回调到均线才做, 不追高位"),
    "range": ("震荡区间(高卖低买)", "区间里不追突破, 等确认再动"),
    "bull_flag": ("牛旗(涨一段后横一下, 蓄力)", "横盘不破前低, 破前高才追"),
    "bear_flag": ("熊旗(跌一段后横一下, 蓄力)", "横盘不破前高, 破前低才追"),
    "converging_wedge": ("收敛楔形(波动收窄, 要变盘)", "收窄末端别做, 等突破方向再动"),
}

def _rr(price, stop, target, direction):
    """RR = 潜在收益 / 潜在亏损. 只对有数能算的回返, 否则 None. target/stop 可能是 [值] 数组, 取首元素."""
    if isinstance(target, (list, tuple)):
        target = target[0] if target else None
    if isinstance(stop, (list, tuple)):
        stop = stop[0] if stop else None
    if not all([price, stop, target]) or price <= 0:
        return None
    risk = abs(price - stop)
    if risk <= 0:
        return None
    # [2026-11-11 chief] 脏样本闸: 止损距离<现价0.1% = 研判leg stop贴价(异常/已失效), RR会算出123倍
    # 误导教学(11-11 21:06 USDJPY stop=px案例), 这类样本直接弃, 不进教学.
    if risk < price * 0.001:
        return None
    reward = abs(target - price)
    return round(reward / risk, 2)

def _plain_num(x):
    """把 float 价变成大白话(最多 4 位有效数字)."""
    if x is None:
        return "-"
    return ("%.4g" % x) if abs(x) < 10000 else ("%.1f" % x)

def rr_lesson(ad_items, ticks, topn=3):
    """L1: 从当前研判 top 品种里挑 RR 最能教人的 1 条, 给实数 + 操盘手口径."""
    cands = []
    for it in ad_items:
        sym = it.get("sym")
        if not sym:
            continue
        px = ticks.get(sym) or it.get("price")
        rr = _rr(px, it.get("stop"), it.get("target"), it.get("direction"))
        if rr is None:
            continue
        cands.append((rr, sym, px, it.get("stop"), it.get("target"), it.get("direction"), it.get("confidence")))
    cands.sort(key=lambda x: x[0], reverse=True)
    # [2026-11-11 chief] 教学样本上界: RR>10 视为脏样本(目标/止损口径异常), 不进教学, 防"123倍盈亏比"误导
    cands = [c for c in cands if c[0] <= 10]
    if not cands:
        return "· L1 盈亏比实算: 当前 top 品种 stop/target 不全或异常, 跳过(不编 RR)。"
    rr, sym, px, stop, target, d, conf = cands[0]
    if isinstance(target, (list, tuple)):
        target = target[0] if target else None
    if isinstance(stop, (list, tuple)):
        stop = stop[0] if stop else None
    verdict = ("RR%.1f 高(≥2, 一笔亏 1 赚 2 以上, 顶配)" % rr if rr >= 2
               else "RR%.1f 中(1.5~2, 可做但要守止损)" % rr if rr >= 1.5
               else "RR%.1f 低(<1.5, 亏多赚少, 顶配不碰)" % rr)
    return ("· L1 盈亏比实算 [%s]: 现价%s 止损%s 目标%s -> %s. "
            "操盘手口径: 先算'亏 1 块能赚几块', 算不清不进; 低于 1.5 直接放弃, 别安慰自己'感觉要涨'. "
            "今天 0 仓 = 有得选, 专挑 RR 高的下." % (sym, _plain_num(px), _plain_num(stop), _plain_num(target), verdict))

def negative_expectancy_lesson(topn=2):
    """L2: 教'弃负期望腿'。优先点 RETIRE 腿(数据判负+系统已关阀=最强叙事), 没有才退回在役亏损腿."""
    et = jget("edge_tracker.json", {})
    syms = et.get("symbols", {})
    retired = []   # 已判负退役
    losing = []    # 在役但亏损
    for sym, d in syms.items():
        n = d.get("n") or 0
        pf = d.get("pf")
        wr = d.get("wr")
        is_ret = bool((d.get("gate_flags") or {}).get("retired"))
        if n < 3 or pf is None:
            continue
        if is_ret:
            retired.append((pf, sym, n, wr))
        elif pf < 0.8:
            losing.append((pf, sym, n, wr))
    if retired:
        retired.sort(key=lambda x: x[0])
        pf, sym, n, wr = retired[0]
        return ("· L2 弃负期望腿 [%s·已退役]: 实盘 n=%d 笔 WR=%.0f%% pf=%.2f, 已被系统 L5 判负并 RETIRE(0 生成 0 放大). "
                "操盘手纪律: 一条腿数据亏到这样, 顶配是'关掉它攒新证据', 不是'再加单赌它回本'. 你现在的 0 仓 0 单就是对的, 守住别破."
                % (sym, n, (wr or 0) * 100, pf))
    if losing:
        losing.sort(key=lambda x: x[0])
        pf, sym, n, wr = losing[0]
        return ("· L2 弃负期望腿 [%s·在役亏损]: 实盘 n=%d 笔 WR=%.0f%% pf=%.2f. "
                "操盘手纪律: 期望为负的腿顶配先减半或关, 不是死扛加仓(Martin 是红线, 永禁)."
                % (sym, n, (wr or 0) * 100, pf))
    return ("· L2 弃负期望腿: 实盘各腿 pf 都还健康(没有亏损/退役腿), 保持纪律——"
            "这是'没亏就是赚', 别急着给自己找毛病。")

def setup_lesson(ad_items, topn=1):
    """L3: 拿当前真实出现最多的 setup/patterns, 翻成大白话 + 操作纪律(不荐方向)."""
    cnt = {}
    for it in ad_items:
        for key in [it.get("setup")] + list((it.get("patterns") or [])):
            if key and key in SETUP_CN:
                cnt[key] = cnt.get(key, 0) + 1
    if not cnt:
        return "· L3 形态白话: 当前 top 品种没标可识别形态, 跳过(不硬凑)。"
    top = sorted(cnt.items(), key=lambda x: x[1], reverse=True)[:topn]
    lines = []
    for key, _c in top:
        cn, rule = SETUP_CN[key]
        lines.append("  %s -> %s" % (cn, rule))
    joined = "\n".join(lines)
    return ("· L3 形态白话(当前盘面高频, 教你认图形+纪律, 不荐方向):\n" + joined)

def edu_section(ad_items, ticks):
    """汇总 3 条教学, 返回可投群的文本块."""
    out = []
    out.append("⑥ 技能教学(顶配操盘手怎么干, 每场练一条):")
    out.append(rr_lesson(ad_items, ticks))
    out.append(negative_expectancy_lesson())
    out.append(setup_lesson(ad_items))
    out.append("· 教学口径: 只教纪律/方法/量化口, 不给'买哪个卖哪个'的方向指令; 历史回测≠未来收益。")
    return "\n".join(out)

if __name__ == "__main__":
    import sys, glob
    f = sorted(glob.glob(os.path.join(DATA, "daily_advisory_*.json")), key=os.path.getmtime)[-1]
    ad = json.load(open(f, encoding="utf-8"))
    items = ad["sections"][0].get("items", [])
    print(edu_section(items, {}))
