# -*- coding: utf-8 -*-
"""金策事件风控写入器 (automation-1786669748876) — 2026-09-03 08:01 BJT 刷新。
按契约写入 data/event_risk.json: level/HIGH<->new_entry_scale 0.3 / HALT<->halt_new_entries true。
时间一律由 datetime 计算, 禁止硬编码 unix 时间戳。"""
import json, time, datetime
from zoneinfo import ZoneInfo

BJT = ZoneInfo("Asia/Shanghai")

def bjt(y, mo, d, h, mi=0):
    return int(datetime.datetime(y, mo, d, h, mi, tzinfo=BJT).timestamp())

NOW = int(time.time())

# 等级判定 (2026-09-03 08:01 BJT 刷新):
#  (a) 结构性HIGH尾部延续·第7个月再升级: 美军昨夜对100+ IRGC目标大规模空袭(防空/雷达/海上资产/布雷能力),
#      伊朗报复约旦/巴林/科威特驻美军队; CENTCOM海上封锁执法(86船改道/3船瘫痪/2登检), 海峡商品船~4艘/日
#      (10日均~13, 战前~130), 两油轮触雷起火; Brent收95.21-95.63(盘中97.04)/WTI 90.63-91.01(盘中92.29)
#  (b) 今日24h窗口双HIGH: 20:30 沃勒访谈(9/5静默期前关键鹰鸽信号)+22:00 ISM服务业PMI(非农前最后重量级)
#  (c) 无黑天鹅/HALT: 海峡未100%冻结(美称周一1700万桶过峡); USDJPY 158.2<162; 加密无级联清算; 无俄打英本土
# => HIGH
LEVEL = "HIGH"
assert LEVEL in ("LOW", "MED", "HIGH", "HALT")
NEW_ENTRY_SCALE = 0.3 if LEVEL == "HIGH" else (1.0 if LEVEL in ("LOW", "MED") else 1.0)
HALT = (LEVEL == "HALT")

# 事件时间点 (北京时间, 2026-09-03)
t_cn_pmi = bjt(2026, 9, 3, 9, 45)     # 中国8月服务业PMI (近2h窗)
t_ez_ppi = bjt(2026, 9, 3, 17, 0)     # 欧元区7月PPI
t_us_hrs = bjt(2026, 9, 3, 20, 30)    # 初请+贸易帐+沃勒访谈
t_us_pmi = bjt(2026, 9, 3, 21, 45)    # 标普全球服务业PMI终值
t_ism    = bjt(2026, 9, 3, 22, 0)     # ISM服务业PMI
t_eia_ng = bjt(2026, 9, 3, 22, 30)    # EIA天然气库存
t_fed_am = bjt(2026, 9, 4, 3, 0)      # 哈马克+古尔斯比 (静默期前)
t_nfp    = bjt(2026, 9, 4, 20, 30)    # 非农 (窗外前瞻, 超出24h窗口约12.5h)

events = [
    {
        "time": NOW,
        "title": "霍尔木兹结构性HIGH尾部延续(美伊冲突第7个月, 昨夜迄今最猛升级, 非HALT): 美军对100+ IRGC目标大规模空袭(防空网络/雷达/海上资产/布雷设施/通信), 伊朗报复约旦/巴林/科威特驻美军国; CENTCOM海上封锁严格执法(截至9/2: 86船改道/3船瘫痪/2登检), 海峡商品船通行~4艘/日(10日均~13, 战前~130), 伊方称两油轮触雷并更新'违规船只'名单。Brent收95.21-95.63(盘中触及97.04=7月下旬来最高)/WTI 90.63-91.01(盘中92.29, 五周高, 连续第三日收涨); 美EIA原油库存超预期-450万桶, 炼厂开工率98%(七年高); 俄Kirishi炼厂遭袭停产+诺瓦克称OPEC+周日不会讨论减产。特朗普称打击'不会持续太久'但'随时准备再袭'。油→通胀→加息通道为核心压制变量, 维持降手看护。",
        "impact": "high",
        "symbols": ["BRENT", "WTI", "XAUUSD", "USD", "USDJPY", "AUDJPY", "GBPJPY", "GBPAUD", "EURAUD"],
    },
    {
        "time": NOW,
        "title": "现货金V形反转收~4388(+1.38%, 自9/2低4282=8/7来最低强势回升, 仍破200日线~4528): 美元走弱(DXY 99.51, -0.11%)+10Y自盘中4.816%(三年高)回落收4.783%+油价冲高回落缓解通胀压力三重短线支撑; COMEX金4434.30(+0.86%)。但9月FOMC(9/15-16)加息定价64-65%(CME FedWatch)中长期压制未消。现货银+1.94%收65.30/COMEX银65.93; 央行购金托底。EA内置0.5x ELEVATED(黄金拥挤守卫)维持降手, 勿抄底勿追空, 仅看护既有持仓(移动SL/跟踪)。",
        "impact": "high",
        "symbols": ["XAUUSD", "XAGUSD"],
    },
    {
        "time": NOW,
        "title": "USDJPY 158.2-158.7(盘中一度触及160.39=干预后最弱后急挫~1.2%至158.22, 干预疑云再起, 实际规模或仅~$5B被夸大): 日方过去一月已耗创纪录964亿美元支撑日元; 高田创(最鹰委员)称25bp'并非板上钉钉'、或更大幅度甚至连续加息, 植田和男暗示9月(9/17-18会议)评估物价上行风险并加息, 市场已完全定价加息25bp至1.25%; JGB 10Y触及3.016%(1996年来首破3%); 贝森特G20会晤植田后施压'做正确的事'; 日本9月食品涨价近5000种推升通胀。现价<162→原HALT触发线(大规模协调干预/失速)暂未触及, 但急涨急跌+持仓4个日元交叉(AUDJPY/GBPJPY/GBPAUD/EURAUD)套息平仓波动敞口直接, 重点看护。",
        "impact": "medium",
        "symbols": ["USDJPY", "JPY", "AUDJPY", "GBPJPY", "GBPAUD", "EURAUD"],
    },
    {
        "time": NOW,
        "title": "加密平静(非HALT): BTC ~$77.1-77.4K横盘(-0.4%, 地缘+油价压制风险偏好), ETH ~$2,384-2,392; 24h全网清算仅~$55-98M(无级联、无强平簇), 9/2 BTC ETF净流入+94.32 BTC。无系统性流动性冻结→不纳入HALT。",
        "impact": "medium",
        "symbols": ["BTC", "ETH", "XAUUSD", "US500"],
    },
    {
        "time": t_cn_pmi,
        "title": "09-03 09:45 BJT 中国8月RatingDog服务业PMI(MED, 距~1.7h落入即时2h窗): 前日官方制造业PMI偏弱背景下, 全球第二大经济体服务业需求信号; 影响CNY/商品货币与亚太风险偏好, 对XAUUSD短线情绪有扰动但非主线。",
        "impact": "medium",
        "symbols": ["CNY", "AUDUSD", "NZDUSD", "XAUUSD"],
    },
    {
        "time": t_ez_ppi,
        "title": "09-03 17:00 BJT 欧元区7月PPI(MED): 油价大涨传导下的生产者通胀读数, 关联ECB(9/10)加息叙事与全球利率通道; 影响EURUSD与加息定价。",
        "impact": "medium",
        "symbols": ["EURUSD", "USD", "BRENT"],
    },
    {
        "time": t_us_hrs,
        "title": "09-03 20:30 BJT 美国初请失业金(预期20.5万/前值20.3万)+7月贸易帐+单位劳力成本 + 美联储理事沃勒访谈(HIGH, 9/5静默期前最后关键鹰鸽表态): 9/2 ADP私营+38K(预期47K)偏弱已令加息定价小幅回落; 沃勒对通胀/就业的表态直接主导9/15-16 FOMC预期, 利率期货当前定价加息~65%。",
        "impact": "high",
        "symbols": ["USD", "XAUUSD", "US500", "US30Y"],
    },
    {
        "time": t_us_pmi,
        "title": "09-03 21:45 BJT 美国8月标普全球服务业PMI终值(MED, 前值56.8): 与ISM交叉验证服务业景气, 次要数据但对美元短线有扰动。",
        "impact": "medium",
        "symbols": ["USD", "XAUUSD", "US500"],
    },
    {
        "time": t_ism,
        "title": "09-03 22:00 BJT 美国8月ISM非制造业PMI(HIGH, 预期54.1/前值54.1, 价格支付分项前值70.3高位): 服务业占美经济~80%, 价格分项检验高油价下通胀黏性, 为9/4非农前最后重量级数据; 直接主导加息概率与黄金/美元方向。落入下一运行2h窗时或推升/维持HIGH。",
        "impact": "high",
        "symbols": ["USD", "XAUUSD", "US500", "US30Y"],
    },
    {
        "time": t_eia_ng,
        "title": "09-03 22:30 BJT EIA天然气库存(LOW): 原油库存已于9/2公布(超预期-450万桶, 炼厂开工98%); 天然气对XAU/油链影响有限, 仅列示不升权重。",
        "impact": "low",
        "symbols": ["NG", "WTI", "BRENT"],
    },
    {
        "time": t_fed_am,
        "title": "09-04 03:00/03:55 BJT 美联储哈马克+古尔斯比讲话(MED, 静默期前收尾信号): 9/5起进入FOMC静默期, 此为窗口内最后官员表态, 留意对9月加息预期的边际修正。",
        "impact": "medium",
        "symbols": ["USD", "XAUUSD", "US500"],
    },
    {
        "time": t_nfp,
        "title": "09-04 20:30 BJT 美国8月非农+失业率(前瞻, 窗外~12.5h, 列入监控): FOMC(9/15-16)前最后一份非农; 7月意外-2.3万(年内最差, 含两月下修-10.3万), 预期8月回暖+5.5万左右、失业率4.1%、时薪环比+0.3%。强于预期→加息概率再升压制黄金; 弱→缓解恐慌。当前HIGH环境核心变量, 下一运行周期重点监控。",
        "impact": "high",
        "symbols": ["USD", "XAUUSD", "US500", "US30Y"],
    },
]

doc = {
    "updated": NOW,
    "level": LEVEL,
    "new_entry_scale": NEW_ENTRY_SCALE,
    "halt_new_entries": HALT,
    "events": events,
}

# 契约断言
assert doc["level"] == "HIGH" and doc["new_entry_scale"] == 0.3, "HIGH<->0.3 契约破坏"
assert doc["halt_new_entries"] is False
assert all("time" in e and "title" in e and "impact" in e and "symbols" in e for e in events), "事件字段缺失"

with open(r"E:\GoldstrategyEngine\data\event_risk.json", "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)

print("CONTRACT VALIDATED OK")
print("updated=", NOW, "level=", LEVEL, "scale=", NEW_ENTRY_SCALE, "halt=", HALT, "events=", len(events))
