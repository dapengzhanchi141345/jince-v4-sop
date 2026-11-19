# -*- coding: utf-8 -*-
"""金策事件风控写入器 (automation-1786669748876) — 2026-09-23 21:55 BJT 运行。
按契约写入 data/event_risk.json: level / HIGH<->new_entry_scale 0.3 / HALT<->halt_new_entries true。
时间一律由 datetime(Asia/Shanghai) 计算, 禁止硬编码 unix 时间戳。"""
import json, time, datetime
from zoneinfo import ZoneInfo

BJT = ZoneInfo("Asia/Shanghai")

def bjt(y, mo, d, h, mi=0):
    return int(datetime.datetime(y, mo, d, h, mi, tzinfo=BJT).timestamp())

NOW = int(time.time())

# 等级判定 (2026-09-23 21:55 BJT 运行):
#  (a) 美伊9/22纽约3小时斡旋会谈=结构性HIGH尾部(连续18次HIGH主驱动)已暂停: 特朗普称"非常有建设性/大量动能",
#      但伊朗坚持7项最高纲领条件(结束所有战线战争/解除海上封锁/解冻资产等), 称满足条件后7天内可重开霍尔木兹;
#      海峡通行9/21仅2艘(基线125, 降98%)→属"谈判降级中"而非100%确认冻结, 不升HALT。
#  (b) 即时2h窗(21:55→23:55)仅含 Fed Barr 22:05 + Jefferson 22:20 讲话(MED级, 非HIGH级数据), 无HIGH即期事件。
#  (c) 现货金 relief rally 退潮回落至~4317(利率通道+2月高美元压制), 非危机; 加密BTC~86K超买但无级联清算(非HALT)。
#  (d) 无黑天鹅/HALT: 无确认100%海峡冻结/无市-wide流动性冻结/USDJPY有序/加密无级联/无俄打英本土。
# => MED (续 13:40 运行, 仍非HIGH/HALT)。EA恢复常规手数(scale 1.0)。
LEVEL = "MED"
assert LEVEL in ("LOW", "MED", "HIGH", "HALT")
NEW_ENTRY_SCALE = 0.3 if LEVEL == "HIGH" else 1.0
HALT = (LEVEL == "HALT")

# 事件时间点 (北京时间)
t_barr      = bjt(2026, 9, 23, 22, 5)    # Fed Barkin 住房峰会讲话
t_jeff      = bjt(2026, 9, 23, 22, 20)   # Fed Jefferson 国债市场会议讲话
t_pmi       = bjt(2026, 9, 24, 9, 45)    # 美国S&P Global闪存PMI
t_au        = bjt(2026, 9, 24, 9, 30)    # 澳大利亚8月就业
t_snb       = bjt(2026, 9, 24, 15, 0)    # SNB + Riksbank 利率决议
t_trumpxi   = bjt(2026, 9, 24, 12, 0)    # 特朗普-习近平峰会(前瞻, 时间近似)

events = [
    {
        "time": NOW,
        "title": "美伊9/22纽约3小时斡旋会谈=连续18次HIGH主驱动(活跃战争尾部)已暂停, 但极脆弱: 特朗普称'非常有建设性/大量动能', 拟近期再谈; 伊朗外长阿拉格齐+威特科夫+库什纳(卡塔尔斡旋). 但伊方坚持7项最高纲领条件(结束所有战线战争/解除海上封锁/解冻全部资产/赔偿等), 称满足后'7天内可重开霍尔木兹'. 海峡通行9/21仅2艘商船(基线125, 降~98%)→属'谈判降级中'而非100%确认冻结, 不升HALT. 同时特朗普联大威胁' annihilate'伊朗, 新制裁伊朗民航9/22生效, 佩泽希齐扬9/23联大讲话. ⚠脆弱性: 谈判'远未最终', 若破裂→下一轮升HIGH/HALT.",
        "impact": "high",
        "symbols": ["XAUUSD", "XTIUSD", "XBRUSD", "USD", "USDJPY"],
    },
    {
        "time": NOW,
        "title": "现货金 relief rally 退潮回落至~4317(9/23 18:30 BJT, 仍守4300-4400窄幅): 承压于2个月高美元 + 鹰派Fed(Barkin称加息可压制通胀预期/穆萨莱姆称或需更多加息), Fed已加至3.75-4.00%且CME定价10月再加息概率53%. 银-2.7%/铂-2.3%. 叙事回到'利率通道压金'主导(非地缘对冲). EA: 本文件level=MED→恢复常规手数(scale 1.0), 但仍仅看护既有持仓、勿追高. 阻力4393-4400, 支撑4300-4333.",
        "impact": "high",
        "symbols": ["XAUUSD", "XAGUSD"],
    },
    {
        "time": t_barr,
        "title": "09-23 22:05 BJT 美联储Barkin(住房峰会)讲话(MED): 加息后Fed官员密集鹰派发声(古尔斯比/穆萨莱姆/巴尔金), 任何再加息暗示都压制黄金与风险. 落入即时2h窗(21:55-23:55)但属讲话非数据→不升HIGH.",
        "impact": "medium",
        "symbols": ["XAUUSD", "US10Y", "USD", "BTCUSD"],
    },
    {
        "time": t_jeff,
        "title": "09-23 22:20 BJT 美联储Jefferson(国债市场会议)讲话(MED): 议题含'国债市场运转'→利率/长久期敏感; 与Barkin构成本周密集Fed发声. 即时窗内但非HIGH级→维持MED.",
        "impact": "medium",
        "symbols": ["XAUUSD", "US10Y", "USD", "BTCUSD"],
    },
    {
        "time": t_pmi,
        "title": "09-24 09:45 BJT 美国9月S&P Global闪存PMI(制造/服务/综合, HIGH): 9月加息后首个重要美国软数据, 检验'单次加息还是新一轮紧缩起点'叙事; 强→美元/收益率压金, 弱→缓解. 落入24h窗但非即时2h窗→不升HIGH.",
        "impact": "high",
        "symbols": ["XAUUSD", "EURUSD", "USD", "US500"],
    },
    {
        "time": t_au,
        "title": "09-24 09:30 BJT 澳大利亚8月就业(失业率预期4.5%, 就业+20K vs 前值-15.8K, MED): 影响AUD与商品货币, 间接作用于持仓中的AUDJPY交叉.",
        "impact": "medium",
        "symbols": ["AUDUSD", "AUDJPY"],
    },
    {
        "time": t_snb,
        "title": "09-24 15:00 BJT 瑞士央行(SNB, 0%预期)+瑞典央行(Riksbank, 1.75%)利率决议(MED): 非美/非日主要央行, 影响CHF/SEK交叉; 关注是否跟随全球转鹰共振.",
        "impact": "medium",
        "symbols": ["USDCHF", "EURSEK", "EURCHF"],
    },
    {
        "time": t_trumpxi,
        "title": "09-24 特朗普-习近平峰会(前瞻, MED): Polymarket定价年内美中关税协议概率92%; 结果影响CNY/AUD/全球风险偏好. 属潜在正向催化, 但亦含谈判破裂尾部.",
        "impact": "medium",
        "symbols": ["CNY", "AUDUSD", "XAUUSD", "US500"],
    },
    {
        "time": NOW,
        "title": "加密超买(非HALT): BTC ~86K(盘中冲87.3K为1月来高后回落, 周+14%)/ETH~2726; 9/21现货BTC ETF单日净流入~9.99亿(11月最大)但24h清算~2.92亿(91,443人), 9/21单日曾>14亿元; F&G贪婪区/RSI72超买. 无级联清算→不升HALT, 但85K上方杠杆多头堆积=均值回归风险(若BTC失守85K支撑或触发多头平仓).",
        "impact": "low",
        "symbols": ["BTCUSD", "ETHUSD"],
    },
]

doc = {
    "updated": NOW,
    "level": LEVEL,
    "new_entry_scale": NEW_ENTRY_SCALE,
    "halt_new_entries": HALT,
    "events": events,
}

# 契约断言 (通用版)
if LEVEL == "HIGH":
    assert doc["new_entry_scale"] == 0.3, "HIGH<->0.3 契约破坏"
if LEVEL == "HALT":
    assert doc["halt_new_entries"] is True, "HALT<->halt_new_entries 契约破坏"
assert all("time" in e and "title" in e and "impact" in e and "symbols" in e for e in events), "事件字段缺失"
assert doc["level"] == "MED" and doc["new_entry_scale"] == 1.0 and doc["halt_new_entries"] is False, "MED契约应为 scale=1.0/halt=False"

with open(r"E:\GoldstrategyEngine\data\event_risk.json", "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)

print("CONTRACT VALIDATED OK")
print("updated=", NOW, "level=", LEVEL, "scale=", NEW_ENTRY_SCALE, "halt=", HALT, "events=", len(events))
