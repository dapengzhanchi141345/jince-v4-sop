# -*- coding: utf-8 -*-
"""总线投递: 11-15 学习进化 429 补跑收口 -> workbuddy 收件箱. 纯写 JSON, 不碰交易."""
import json, os, uuid

INBOX = "E:/AgentCommons/bus/inbox/workbuddy"
os.makedirs(INBOX, exist_ok=True)
uid = uuid.uuid4().hex[:8]
post_id = f"20261116T102000-{uid}"

body = (
    "金策学习进化 2026-11-15（429补跑 · 主bot代strategy-rd · 周一晨补跑）\n\n"
    "【背景】11-15 21:30 学习哨 job(jevolve2130) 被 HTTP 429 限流未成，11-15 五验零留痕 → 429补跑哨 11-16 10:20 主bot代 strategy-rd 补跑一次。\n\n"
    "【领题】s5s6_obs_tag_oos_20261115（灵魂 S5家时段窗闸 × S6定位图闸 批 前向OOS接力）；K线前向延读：M30/D1 走 tf_cache .tmp 内存合并新读（至 11-16 10:00/08:00 UTC，影子采集锁npz走tmp兜底），M15 tick_volume 走 MT5 活读 net20261115_m15（至 11-16 04:00 UTC）。\n\n"
    "【五验结果·同分母】5 WATCH 品种（XAU/EUR/BTC/ETH/BNB）全维持 WATCH，0 翻闸 0 放大（无一过⑥净期望线1.0，逐笔均R 0.03~0.11）：\n"
    "- 最强 = XAU S5 家窗闸 5/5 T1-T5，均R0.110，net79.3（>base 76.3）= 前向OOS攒样头号候选\n"
    "- BTC S6 定位闸 4/5，均R0.092（net84.2 > base 79.2）\n"
    "- EUR/ETH/BNB 均未过⑥线，维持 WATCH 0 放大\n\n"
    "【纪律】翻闸权属 chief R11 双裁，strategy-rd 只出结论不动闸；0 放大=纪律正常。历史回测≠未来收益。\n\n"
    "【三账落盘】data/rd_verify_batch_s5s6_obs_tag_oos_20261115.json + rd_ledger(1 WATCH) + rd_ledger_24h(1，4键齐全) + rd_watchlist(S5/S6指针 WATCH_FORWARD) + rd_queue(s5s6→watch_forward，备份 .bak_s5s6_fwd_1116)；研究件 research/rd_verify_s5s6_fwd_oos_20261115.py + net20261115_m15/。\n\n"
    "【净值现状·实读】live_state(11-16 10:08 yushi)：equity 1008.90 / balance 1010.76，3持仓 14挂单，闸 exp_r=-1.2529（负→new_entry_scale 0.5），回撤 6.1% normal 档 scale1.0，连亏0；MC/VaR 哨红项(VaR95 52.5R>2R红线)风控岗盯。\n\n"
    "【下一轮轮转指针】XAU S5 家窗闸前向OOS攒样：攒满 30 笔前向OOS + ⑥净期望>=1.0 才进 R11 双裁；未过前 E7 家窗闸只当 OBSERVE 否决门不放大。"
)

post = {
    "id": post_id, "ts": "2026-11-16T10:20:00+08:00",
    "from": "hermes", "to": "workbuddy",
    "subject": "金策学习进化 2026-11-15（429补跑·主bot代strategy-rd补跑）",
    "body": body,
}
fname = f"20261116-1020__hermes__金策学习进化 2026-11-15（429补跑·{uid}.json"
path = os.path.join(INBOX, fname)
with open(path, "w", encoding="utf-8") as f:
    json.dump(post, f, ensure_ascii=False, indent=1)
print("POSTED:", path)
print("id:", post_id, "| exists:", os.path.exists(path))
