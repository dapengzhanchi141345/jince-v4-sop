# -*- coding: utf-8 -*-
"""生成 docx 规格 JSON (李彦明铁律: 封面+目录+彩色表格+图表+页码, 微软雅黑)"""
import json, os

ROOT = "E:/GoldstrategyEngine"
d = json.load(open(os.path.join(ROOT, "data", "sl1117_deep_20261118.json"), encoding="utf-8"))
ORD = d["orders"]

def row(o):
    cls = "；".join(o.get("classify", [])) or ("方向错(不该进)" if (o.get("mae_atr") or 0) >= 2 and (o.get("mfe_atr") or 0) < 0.5 else "待补数据")
    return [o["sym"], "空" if o["side"] == "sell" else "多", o["time"][6:], f'{o["pnl"]:+.2f}',
            str(o.get("sl_width_atr")), str(o.get("mfe_atr")), str(o.get("mae_atr")),
            ("是" if o.get("tp_hit") else "否" if o.get("tp_hit") is False else "无数据"), cls]

rows = [row(o) for o in ORD]
rb = d.get("rule_b_displacement", {})

spec = {
    "footer": "金策宗师团 · 11-17 止损单深度调研 · 2026-11-18",
    "footer_page_numbers": True,
    "styles": [
        {"name": "JinCeBody", "base": "Normal", "font": "Microsoft YaHei", "size_pt": 11},
        {"name": "JinCeTitle", "base": "Normal", "font": "Microsoft YaHei", "size_pt": 26, "bold": True, "color": "1F4E79"},
    ],
    "blocks": [
        {"type": "paragraph", "text": "金策宗师团", "style": "JinCeTitle", "level": 1},
        {"type": "heading", "text": "11-17 止损单深度调研：进场点位与进场时机归因", "level": 1},
        {"type": "paragraph", "text": "日期：2026-11-18 ｜ 数据：DEMO 60137964 实读 + tf_cache 30日M30 ｜ 口径：同分母五验 + 扫损后12h诊断"},
        {"type": "page_break"},
        {"type": "toc"},
        {"type": "page_break"},
        {"type": "heading", "text": "一、结论摘要（大白话）", "level": 1},
        {"type": "bullet_list", "items": [
            "11-17 共 12 笔止损单。其中至少 3 笔（BLK空/GBP多/DOGE多）是『假扫损』：止损之后 12 小时，价格反而朝有利方向走了 1.5~3.45 倍ATR（GBP 甚至扫损前只差一点就摸到目标）。方向是对的，坏在进场点位/时机 + 止损线画太窄。",
            "日经/JPY 交叉货币 4 腿（USDJPY/GBPJPY/EURJPY/AUDJPY）同方向空单，77 分钟内集体止损 = 同族批量进场，一次判断错就 4 连损。旧族闸只按基础货币计腿，漏掉了『同报价货币篮子』。",
            "12 笔里 7 笔发生在 BJT 04:00-12:00 亚盘低波窗（噪声带内开单，止损率天然高）。",
            "最大单笔亏 BLK.NYS -18.29 元（04:28 亚盘，扫损后顺向 2.27ATR 未回本）= 时间点最差的一单。",
            "已根治项：SL 宽度已全切 spec v4 赚钱格 0.8×ATR30+TP3R（11-17 全品种深优 4/6 OOS 双正）；昨晚三腿（BTC/ETH/SOL）验证有效 = 全部止盈离场，净值 982.90 → 994.85。",
        ]},
        {"type": "heading", "text": "二、11-17 止损单全表（12 笔，MT5 实读）", "level": 1},
        {"type": "table", "style": "Table Grid", "header_bold": True,
         "header": ["品种", "方向", "时间(BJT)", "盈亏(元)", "SL宽(×ATR)", "扫损后MFE", "扫损后MAE", "摸到TP", "归类"],
         "rows": rows},
        {"type": "paragraph", "text": "注：MFE/MAE=止损后 12 小时内最大顺向/逆向波动（ATR 倍数）。MFE≥1.5 且未摸 TP = 假扫损（方向对、被扫）；摸到 TP = 纯假扫损；MAE≥2 且 MFE 小 = 方向错（止损正确，该拦在进场端）。D1 兜底数据的品种无高频 MFE（记无数据）。", "style": "JinCeBody"},
        {"type": "heading", "text": "三、扫损后走势图（可定量 4 单）", "level": 1},
        {"type": "image", "path": os.path.join(ROOT, "data", "sl1117_mfe_chart.png"), "width_mm": 170},
        {"type": "page_break"},
        {"type": "heading", "text": "四、关键单逐单归因", "level": 1},
        {"type": "table", "style": "Table Grid", "header_bold": True,
         "header": ["单", "事实", "归因", "教训"],
         "rows": [
            ["BLK空 @04:28 (-18.29)", "扫损后顺向 2.27ATR，未回 TP", "亚盘低波窗开单 + SL 在噪声带内", "低波窗不开仓（规则 R3）"],
            ["GBP多 @18:46 (-0.37)", "3.7pip 无锚紧损，14 分钟被扫；扫损后顺向 3.45ATR", "SL 太窄（无结构锚）", "R1 已根治：SL≥0.8×ATR30"],
            ["DOGE多 @08:12 (-0.01)", "SL≈点差级，扫损后直接摸到 TP", "纯假扫损", "R1 覆盖"],
            ["US30空 @12:54 (-2.95)", "扫损后逆向 8.79ATR", "方向错（不该进）", "止损正确；进场端加位移确认（R4）"],
            ["JPY族 4腿 @13:14-14:31", "同向空单 77 分钟全平，合计 -0.82", "同报价货币篮子无上限 + 同信号批量", "R2：同报价货币同向 ≤2 腿"],
        ]},
        {"type": "heading", "text": "五、防继续止损：五条规则 + 数据", "level": 1},
        {"type": "table", "style": "Table Grid", "header_bold": True,
         "header": ["规则", "内容", "数据依据", "状态"],
         "rows": [
            ["R1 SL≥0.8×ATR30", "止损宽度出噪声带（spec v4 赚钱格 + TP3R）", "全品种深优 4/6 五验 OOS 双正；11-17 假扫损 3/12 均因 SL 窄", "已生效（昨晚三腿验证）"],
            ["R2 同报价货币族闸", "同 JPY/同 EUR 报价篮子同向 ≤2 腿（旧族闸只数基础货币）", "11-17 JPY 4 腿 77 分钟全损 -0.82", "rd 工单→执行岗引擎接线"],
            ["R3 亚盘低波窗禁开", "外汇/股指 BJT 00:00-07:00 不开新仓（币 24h 不受限）", "12 笔中 7 笔在 04-12 时段；BLK 最大亏在 04:28", "rd 工单→信号岗时段闸"],
            ["R4 位移确认闸(按品种)", "信号棒实体 ≥0.45×ATR30 才放行进场", "30日回测：BTC 净R 69.6→99.1(+30)、GBP -7.1→+11.2 转正；ETH/SOL 变差→只给 BTC/GBP 开", "WATCH 攒样（30笔OOS后裁定）"],
            ["R5 既有机制", "12h红线 + 事件窗降半 + 验尸哨 + OOS30 翻闸", "11-09~11 实证", "保持"],
        ]},
        {"type": "heading", "text": "六、下一步与今晚结算", "level": 1},
        {"type": "bullet_list", "items": [
            "昨晚三腿（BTC/ETH/SOL 空，赚钱格参数）凌晨 01:58 全部止盈离场：BTC +11.30 元(≈+4.4R) / ETH +0.46 / SOL +1.81，净值 982.90→994.85。",
            "07:30 晨间战报自动送达；09:35 红线哨处置（结构破=平腿/未破=滚 12h，最小影响）。",
            "R2/R3/R4 工单入 rd_queue（执行岗/信号岗/参数官），OOS 30 笔账本由参数官 30min 哨自动记账。",
            "结论一句话：方向错不该进（R4 拦），方向对不该扫（R1+R2+R3 保），亏损单继续当学费当样本，不斩除。",
        ]},
        {"type": "paragraph", "text": "声明：历史回测≠未来收益；R2-R4 为前向攒样口径（WATCH），未过 30 笔 OOS 前不翻闸；全部动作限 DEMO 练习账户，REAL 零动。"},
    ],
}

out = os.path.join(ROOT, "data", "sl1117_docx_spec.json")
json.dump(spec, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("spec OK ->", out)
