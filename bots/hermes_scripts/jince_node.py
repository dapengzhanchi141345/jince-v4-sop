#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""金策宗师团 · 研讨节点确定性生成器 (no_agent L0, 0 LLM, 429-proof)
节点要的"价/动量/我方持仓/胜率/下一条待验证思路"全是能从 data/ 算出的确定性数据,
不烧 LLM —— 根治"LLM 节点被 Agnes 免费池 429 吞掉、静默不发言"。
用法: python jince_node.py   (自动按北京时间判定当前该出哪个节点)
输出: stdout = 一页研讨摘要(投 bot-chat 群); 同时追加一条 JSON 到 data/discussion_log.jsonl
"""
import os, sys, json, time, subprocess, datetime, zoneinfo
import jince_edu

DATA = r"E:/GoldstrategyEngine/data"
ATE_PY = r"C:/Users/ASUS/.workbuddy/binaries/python/envs/ate/Scripts/pythonw.exe"
BJT = zoneinfo.ZoneInfo("Asia/Shanghai")
WATCH = ["XAUUSD","XAGUSD","EURUSD","GBPUSD","USDJPY","BTCUSD","ETHUSD","US500","NAS100"]

def now_bjt():
    return datetime.datetime.now(BJT)

def pick_node(h):
    # 节点 :05 错峰, 判定窗口
    if h in (0, 1, 2): return ("us_close", "美盘收口")
    if h in (8,): return ("asia_open", "东京开评")
    if h in (12,): return ("asia_close", "东京对账")
    if h in (15, 16): return ("europe_open", "伦敦开评")
    if h in (18,): return ("europe_close", "伦敦对账")
    if h in (21, 22): return ("us_open", "美盘开评")
    return (None, None)  # 非节点时刻: 不占节点记号, 防补发/滞压/误跑出"错节点"(2026-10-05 根治)

# 2026-10-05 修复: 手动补发(非 :05 整点)时墙上时钟会误判节点身份(11:39 补发 08:05 节点被印成"美盘开评").
# 现支持 jince_node.py <node_key>: 传了合法 node key 就按身份走, 没传才退回时钟判定(定时 :05 跑不受影响).
NODE_CN = {"asia_open": "东京开评", "asia_close": "东京对账", "europe_open": "伦敦开评",
           "europe_close": "伦敦对账", "us_open": "美盘开评", "us_close": "美盘收口"}

def latest_advisory():
    """返回 (文件名, advisory对象, 基准时间字符串).
    [2026-10-06 根治] 旧写法只取 mtime 最新文件, 但日内该文件 sections[0].beijing
    可能停在早上(如 09:31), 节点评就印旧基准. 现: 在该文件内取 beijing 基准最新的
    section(日内 15:02 的比 09:31 新), 节点评读新基准不再印旧时间."""
    cands = [f for f in os.listdir(DATA) if f.startswith("daily_advisory_") and f.endswith(".json")]
    if not cands: return None, None, None
    f = max(cands, key=lambda x: os.path.getmtime(os.path.join(DATA, x)))
    ad = json.load(open(os.path.join(DATA, f), encoding="utf-8"))
    # 取 beijing 基准最新的 section
    sec = ad.get("sections", [])
    best = None; best_bj = ""
    if isinstance(sec, list):
        for s in sec:
            if isinstance(s, dict):
                b = str(s.get("beijing",""))
                if b > best_bj:
                    best_bj = b; best = s
    elif isinstance(sec, dict):
        best = sec; best_bj = str(sec.get("beijing",""))
    if best is not None:
        ad = best  # 节点评动量读它
    return f, ad, best_bj

def jget(path, default):
    try:
        return json.load(open(os.path.join(DATA, path), encoding="utf-8"))
    except Exception:
        return default

def live_ticks(syms, timeout=30):
    """直接经 ate 解释器拉实时 tick(剥 PYTHONPATH 的 mt5_launch 只为手动命令服务, 纯 tick 拉用不到那层).
    失败 fail-open 返回 {}. 2026-10-04 根治: 旧写法 subprocess.run([mt5_launch.py,...]) 把 .py 当 exe
    报 WinError 193 -> 恒 0 品种; 现直接 [ATE_PY,'-c',code] 走 ate 环境, 节点内不再起 mt5_launch 子进程."""
    code = ("import os,json,MetaTrader5 as m\n"
            "os.environ.pop('PYTHONPATH',None);os.environ.pop('PYTHONHOME',None)\n"
            "ok=m.initialize()\n"
            "out={}\n"
            "for s in %r:\n"
            "    t=m.symbol_info_tick(s)\n"
            "    if t and t.bid>0: out[s]=(t.bid+t.ask)/2.0\n"
            "print(json.dumps(out))\n") % list(syms)
    try:
        r = subprocess.run([ATE_PY, "-c", code], capture_output=True, text=True,
                           timeout=timeout, cwd=r"E:/GoldstrategyEngine",
                           env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")})
        for line in reversed(r.stdout.strip().splitlines()):
            if line.strip().startswith("{"):
                return json.loads(line)
        return {}
    except Exception:
        return {}

def xu_time_gate():
    """[2026-10-13 焊跳②] 徐总时段权重闸: 读 data/xu_time_weight.json 的 dst_* 字段
    (服务器 Eto DST 校准口径; 固定+8 的 top/bottom_hours 已降级存档, 勿用)。
    当前 BJT 时 ∈ dst_bottom_hours → 本时段研判一律降档/否决门; ∈ dst_top_hours → 正常研判; 其余中性。
    只做否决门+提权参考, 不单独开仓(红线不变)。fail-open: 无文件/无字段=静默不展示。"""
    p = os.path.join(DATA, "xu_time_weight.json")
    if not os.path.exists(p):
        return ""
    try:
        tw = json.load(open(p, encoding="utf-8"))
        top = [str(h).zfill(2) for h in (tw.get("dst_top_hours") or [])]
        bot = [str(h).zfill(2) for h in (tw.get("dst_bottom_hours") or [])]
        if not top and not bot:
            return ""
        hh = datetime.datetime.now(BJT).strftime("%H")
        if hh in bot:
            return (f"①.5 时段闸(徐13万笔·DST): 现 {hh} 时 ∈ 下沿时段 {bot} → 本时段研判降档/否决门; "
                    f"上沿时段 {top} 正常研判 (只做参考, 不单独开仓)")
        if hh in top:
            return f"①.5 时段闸(徐13万笔·DST): 现 {hh} 时 ∈ 上沿时段 {top} → 正常研判段 (徐: dst 口径 01/18 时最赚, 16/06 时最亏)"
        return f"①.5 时段闸(徐DST): 现 {hh} 时 中性段 (top {top} / bottom {bot}) → 不降档不否决"
    except Exception:
        return ""


def top_movers(ad, n=10):
    """ad 现 = advisory 文件里的 sections[0] 结构(带 items/bj)"""
    if not ad: return []
    s = ad
    items = [it for it in s.get("items", []) if it.get("sym") and it.get("mom_m30_24h") is not None]
    items.sort(key=lambda x: abs(x.get("mom_m30_24h") or 0), reverse=True)
    out = []
    for it in items[:n]:
        out.append({"sym": it["sym"], "px": it.get("price"), "mom24h": round(it.get("mom_m30_24h"), 2),
                    "dir": it.get("direction"), "conf": it.get("confidence"),
                    "action": (it.get("action") or "")[:20]})
    return out, s.get("beijing")

def _ate_mt5_live_read(timeout=90):
    """[2026-10-05 根治] 节点②改走 ATE 子进程实读 MT5 —— 根治 import 坏.
    根因: 节点 cron 用 3.13 解释器跑, 它没装 MetaTrader5 (No module named),
    mt5_live_read 模块级 import 就崩 -> 节点②必降级; 且 3.13 连节点脚本自身都跑不利索.
    旧补丁"sleep 3s 重试"对 import 失败无效 (已删). 现: 起 ATE 子进程 import 并实读
    (与①tick 同一套被验证连接), 成功即同形状 dict, 失败才 fail-open 降级明示.
    只碰节点脚本, 不改 mt5_live_read.py 本体(strategy-rd 线维护)."""
    code = ("import os,json,sys\n"
            "os.environ.pop('PYTHONPATH',None);os.environ.pop('PYTHONHOME',None)\n"
            "sys.path.insert(0,r'E:/GoldstrategyEngine')\n"
            "import mt5_live_read\n"
            "r=mt5_live_read.live_read()\n"
            "print(json.dumps(r,ensure_ascii=False,default=str))\n")
    try:
        res = subprocess.run([ATE_PY, "-c", code], capture_output=True, text=True,
                             timeout=timeout, cwd=r"E:/GoldstrategyEngine",
                             env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")})
        for line in res.stdout.strip().splitlines():
            line = line.strip()
            if line.startswith("{"):
                r = json.loads(line)
                if r.get("degraded"):
                    r.setdefault("errors", []).append("(ATE 实读降级: %s)" % "; ".join(r.get("errors", []))[:80])
                return r
        return {"degraded": True, "errors": ["ATE 实读子进程无 JSON 输出: %s" % (res.stderr[:60] or res.stdout[:60])],
                "n_orders": None, "n_pos": None}
    except Exception as e:
        return {"degraded": True, "errors": ["ATE 实读异常: %s" % str(e)[:60]], "n_orders": None, "n_pos": None}

def _mt5_live_section():
    """节点报"我方挂单/持仓": ①ATE 子进程实读 MT5 活体 (根治 import 坏);
    实读成功 -> 活挂单/活持仓实数; 实读失败 -> fail-open 降级, 派生簿只留痕, 明示不作实盘断言.
    旧病根(派生簿滞后误报无 open 单)由实读覆盖; 撞车/import 坏由 ATE 子进程根治."""
    return _ate_mt5_live_read()

def our_exposure():
    """[2026-10-05 V13根治] 统一实读入口: 先 MT5 活体, 派生簿只留痕. 返回 (实读dict, 留痕行list)."""
    live = _mt5_live_section()
    traces = []
    try:
        st = json.load(open(os.path.join(DATA, "pending_orders_state.json"), encoding="utf-8"))
    except Exception:
        st = {}
    for bf in ("pending_orders_brief.md", "crypto_pending_brief.md", "equity_pending_brief.md"):
        p = os.path.join(DATA, bf)
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8", errors="replace"):
            if "status=open" in line or "status=filled" in line:
                traces.append(line.strip()[:120])
    return live, traces[:5]

def next_verify_item():
    """从最新 rd_verify_batch 取下一条 PENDING 验证思路"""
    cands = [f for f in os.listdir(DATA) if f.startswith("rd_verify_batch_") and f.endswith(".json")]
    if not cands: return None
    f = sorted(cands)[-1]
    b = json.load(open(os.path.join(DATA, f), encoding="utf-8"))
    for it in b.get("items", []):
        if it.get("status") in ("PENDING", "WATCH", None) or "待" in json.dumps(it, ensure_ascii=False):
            return {"id": it.get("id"), "hypo": it.get("hypo"), "file": f}
    return {"file": f, "hypo": "(批次已满, 收口新批次)"}

def meta_winrate():
    m = jget("meta_evolution.json", {})
    s = m.get("stats", {})
    g = s.get("swing", {})
    if g: return f"swing 腿 n={g.get('n_total')} WR={g.get('wr')} exp_R={g.get('expectancy_R')}"
    return "meta_evolution: 无 swing 统计"

def governor():
    g = jget("governor_state.json", {})
    return f"净值峰值={g.get('peak_equity')} 回撤={g.get('dd_pct')}% 净方向={g.get('net_side')} 热持仓={g.get('live_heat')}%/挂单={g.get('latent_heat')}%"

def event_level():
    r = jget("event_risk.json", {})
    return f"事件面={r.get('level')} scale={r.get('new_entry_scale')}"

def build(node_key=None, noreceipt=False):
    if node_key in NODE_CN:
        node_key, node_cn = node_key, NODE_CN[node_key]
    else:
        node_key, node_cn = pick_node(now_bjt().hour)
    # 非节点时段被无参调用(pick_node 返回 (None,None)): 不占节点记号、不投递、不写节点 log。
    # 手动补某节点请显式传身份: jince_node.py <asia_open|asia_close|europe_open|europe_close|us_open|us_close>
    if node_key is None:
        print("", end="")
        return
    af, ad, ad_bj = latest_advisory()
    movers, bj_basis = top_movers(ad)
    # 实时 tick: WATCH 全量 + 动量 top 实际展示的品种并集(修: 旧写法只拉 WATCH, 动量前6现=仍是研判旧价)
    tick_syms = list(dict.fromkeys(list(WATCH) + [m["sym"] for m in movers[:6]]))
    ticks = live_ticks(tick_syms)
    exp, exp_traces = our_exposure()
    nv = next_verify_item()
    lines = []
    lines.append(f"【{node_cn}】金策宗师团 · 节点 {datetime.datetime.now(BJT).strftime('%m-%d %H:%M')} UTC+8")
    lines.append(f"· 数据基准: 研判 {bj_basis}({af}) + 实时tick {len(ticks)}品种 {datetime.datetime.now(BJT).strftime('%H:%M')}")
    lines.append("")
    lines.append("① 动量 top(24h):")
    for m in movers[:6]:
        t = ticks.get(m["sym"])
        px = f"{t:.4g}" if t else str(m.get("px"))
        lines.append(f"   {m['sym']:<9} 24h={m['mom24h']:+.1f}% 现={px} 系统={m['dir']}(conf {m['conf']}) {m['action']}")
    lines.append("")
    # [2026-10-13 焊跳②] 徐总时段权重: 开评研判前真读 xu_time_weight.json dst 口径, 下沿时段降档/否决
    _tgate = xu_time_gate()
    if _tgate:
        lines.append(_tgate)
        lines.append("")
    lines.append(f"② 我方挂单/持仓 (MT5 活体实读, 派生簿只留痕):")
    if exp.get("degraded"):
        lines.append("   [降级] MT5 实读失败(派生簿口径仅留痕, 不作实盘断言): "
                     + "; ".join(exp.get("errors", []))[:80])
        for r in exp_traces:
            lines.append("   留痕 " + r)
    else:
        lines.append(f"   实读: 账户 {exp['account'].get('login')} 余额 ${exp['account'].get('balance'):.2f} "
                     f"| 活挂单 {exp['n_orders']} 张 | 活持仓 {exp['n_pos']} 张")
        for o in exp.get("orders", [])[:5]:
            lines.append(f"   挂 #{o.get('ticket')} {o.get('symbol')} {o.get('type')} "
                         f"{o.get('volume')}手 @{o.get('price')} (magic {o.get('magic')})")
        for p in exp.get("positions", [])[:5]:
            lines.append(f"   持 #{p.get('ticket')} {p.get('symbol')} {p.get('type')} "
                         f"{p.get('volume')}手 @{p.get('price_open')} 浮={p.get('profit')}")
        if not exp.get("orders") and not exp.get("positions"):
            lines.append("   (实盘 0 挂单 0 持仓)")
        for r in exp_traces:
            lines.append("   留痕 " + r)
    lines.append("")
    lines.append(f"③ 引擎健康: {meta_winrate()} | {governor()} | {event_level()}")
    lines.append("")
    if nv:
        vid = nv.get('id')
        idtag = f"[{vid}]" if vid else ""
        lines.append(f"④ 下一条待验证思路(进五验): {idtag} {nv.get('hypo')}  ← @strategy-rd")
    lines.append("")
    lines.append(jince_edu.edu_section(ad.get("items", []), ticks))
    lines.append("· 闭环铁律: 节点实数已落 discussion_log; 429-proof(0 LLM); 历史回测≠未来收益。")
    text = "\n".join(lines)
    # 追加 discussion_log (投达层回执). noreceipt=巡检补发时不重复写, 防 30min 补发刷屏+留痕错位
    if not noreceipt:
        try:
            rec = {"node": node_key, "ts": int(time.time()), "beijing": datetime.datetime.now(BJT).strftime("%Y-%m-%d %H:%M"),
                   "gen": "no_agent_L0_429proof", "movers_n": len(movers), "next_verify": nv.get("hypo"), "ok": True}
            with open(os.path.join(DATA, "discussion_log.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            text += f"\n· [warn] discussion_log 写失败: {e}"
    print(text)

if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if a != "--noreceipt"]
    build(args[0] if args else None, noreceipt="--noreceipt" in sys.argv[1:])
