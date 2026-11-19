# -*- coding: utf-8 -*-
"""
write_risk_state.py - L4 风控状态文件生成器 (t_a3872914 承接)
================================================================
组合风险总督(第13部门) 与 事件快通道 event_guard.py 共用的一份"组合风险体温表"。
原则: 只泄压不加息 — 本文件只降 new_entry_scale / 抬 10pct_circuit_progress,
绝不放大仓位。写盘后 event_guard/30min全链 读它做快速判断。

数据源 (全部只读, 不发明数字):
  data/governor_state.json      第13部门 热量/净方向/相关簇/回撤刹车
  data/pending_orders_state.json 连亏计数/当日已实现P&L/24h冷却
  data/crypto_freeze_gate.json  币系冻结桥 (L4 单一真相源)
  data/event_risk.json          事件面 level/halt/scale
"""
import json, os, time, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "risk_state.json")
HEALTH = os.path.join(DATA, "data_health.json")  # 洞①: data_health.py 产出的独立闸源(单源, 读-合并)

# v2.0 钦定: 日内亏损上限 = 当日累计亏损(平仓已实现 + 未平仓浮亏)占活读净值 1.5%。
# 比 10pct_circuit(10% 熔断) 更细一层日内日闸: 先到 1.5% 先停新腿, 10% 是更硬熔断线。
DAILY_LOSS_CAP_PCT = 1.5


def build_daily_loss_cap_block(now_ts):
    """v2.0 日内亏损上限闸(1.5% 钦定, @chief 终审 re-scope 二选一取"真桥 risk_state + 挂单链 reader")。

    与 data_health 不同: 分子分母全在本体温表已读源里, 值直接算进 state 本体随 json.dump 落盘,
    天然无 clobber(单源自产, 不存在独立脚本竞争 risk_state 本体)。
      当日亏损 = -(平仓已实现亏损 day_realized_pnl + 未平仓浮亏 _tmp_mt5snap.positions.profit 合计)
      分母     = 活读净值 _tmp_mt5snap.account.equity (@chief 20% 安全垫分母同挂活读线, 不用 peak_equity)
      breached = 当日亏损 >= cap; data_unreliable = 浮亏源过期/净值缺失 → reader 从严 0 开
    reader = run_trader.py daily_loss_cap_gate(挂单链 CIO 段后, 账户级日闸, 不影响既有持仓管理)。
    """
    cap = DAILY_LOSS_CAP_PCT
    po = _load("pending_orders_state.json")
    today = datetime.date.today().strftime("%Y-%m-%d")
    realized = float(po.get("day_realized_pnl", 0.0)) if po.get("day_realized_date") == today else 0.0
    snap = _load("_tmp_mt5snap.json")
    positions = snap.get("positions") or []
    floating = sum(float((p.get("profit") or 0.0)) for p in positions)
    equity = float((snap.get("account") or {}).get("equity") or 0.0)
    snap_ts = int(snap.get("written_at") or 0)
    snap_stale = (now_ts - snap_ts) > 1800

    if not equity:
        # 活读净值缺失: 分母挂不上 → 数据不可靠, 字段在位(不是 null)但 action 从严, reader 拦新腿
        return {
            "cap_pct": cap, "daily_loss_pct": 0.0, "progress_pct": 0.0,
            "equity": 0.0, "realized_loss_today": round(max(0.0, -realized), 2),
            "floating_loss_today": 0.0, "breached": False, "data_unreliable": True,
            "source": "分母活读净值缺失(_tmp_mt5snap.account.equity=0) → 数据不可靠, 从严",
            "action": "DEGRADE_数据不可靠, 新腿 0 开(活读净值挂不上, 同 SOP 数据旧快照从严)",
        }

    daily_loss = max(0.0, -(realized + floating))  # 亏损取正(已实现+浮亏, 正=当天在亏)
    daily_loss_pct = daily_loss / equity * 100.0
    progress_pct = daily_loss_pct / cap * 100.0
    breached = daily_loss_pct >= cap
    data_unreliable = snap_stale
    if data_unreliable:
        action = "DEGRADE_浮亏源过期(>1循环), 从严新腿 0 开"
    elif breached:
        action = "BREACHED 当日亏损 >= 1.5% 上限, 全品种新腿 0 开(账户级日闸, 既有持仓照管)"
    else:
        action = "OK 日内亏损在上限内, 新腿放行"
    return {
        "cap_pct": cap,
        "daily_loss_pct": round(daily_loss_pct, 4),
        "progress_pct": round(progress_pct, 2),  # breached 时 >100, 保留真实超幅给实拉
        "equity": round(equity, 2),
        "realized_loss_today": round(max(0.0, -realized), 2),
        "floating_loss_today": round(max(0.0, -floating), 2),
        "breached": breached,
        "data_unreliable": data_unreliable,
        "source": "pending_orders.day_realized_pnl(平仓销账) + _tmp_mt5snap.positions 浮亏; 分母=活读净值(@chief 安全垫分母同挂)",
        "action": action,
        "consumer": "run_trader.daily_loss_cap_gate(挂单链 CIO 段后, 账户级日闸)",
    }


def _load(name, path=None):
    p = path if path else os.path.join(DATA, name)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {}


def build_data_health_block(now_ts):
    """洞①读-合并 + 洞③故障态: 从独立 data_health.json 取 data_health 块, 消 clobber。

    write_risk_state 每轮整份 json.dump 覆盖 risk_state.json, 若 data_health 只由
    data_health.py 直接写本体, 下轮会被盖没(实读 21:31 已证)。现在改成: 本函数
    每轮重建 state 前读独立 data_health.json 并 merge 进 state['data_health']。

    洞③ fail-open 兜底: 读不到 / ts 距本轮 > max_age_s(1循环) → 不静默放行,
    把整批标 data_unreliable=True + 受影响品种 tier 升级为 red(当日禁开单), 同 SOP 数据旧快照从严。
    """
    h = _load("data_health.json", HEALTH)
    if not h or not isinstance(h, dict) or "symbols" not in h:
        # 洞③ 读不到独立闸源: 从严——数据不可靠, 全品种观望, 不静默放行
        return {"ts": now_ts, "source": None, "symbols": {}, "summary": {},
                "data_unreliable": True,
                "note": "data_health.json 缺失/不可读 → 整批按数据不可靠观望(洞③ fail-open 从严)"}
    max_age = int(h.get("max_age_s", 1800) or 1800)
    h_ts = int(h.get("ts", 0) or 0)
    # [2026-11-04 chief L1 · L6 数据管道格] 生产者源冻结标志: data_health.py 按米快照 mtime 自标 stale=True
    # (快照池冻结时, ts 恒新但源是 7 天旧数据 — 光看 ts 判不出)。读方同样整批升 data_unreliable,
    # tier 保持原值 0 漂移(同 10-26 L5 洞③语义修), note 诚实报"源冻结"。
    src_stale = bool(h.get("stale"))
    stale = (now_ts - h_ts) > max_age or src_stale
    block = dict(h)
    if stale:
        # 洞③ 过期(独立源距体温表 > max_age_s 没刷新): 数据源陈旧, 从严整批保守 0 开。
        # [2026-10-26 L5 洞③语义修, rd_decisions #62] 不再把 9 个 green 品种误升 red:
        #   (a) "数据源旧" ≠ "品种数据坏", 全市场升 red 是谎报, 且让 risk_state.data_health
        #       tier 分布与独立源漂移, 打穿 a 格 loop-2 "0 漂移" 验收 (loop2_probe 实读抓到 10红 vs 独立9绿1红);
        #   (b) 读侧开单行为 100% 不变: 改前"全 red + data_unreliable"读侧整批 0 开,
        #       改后"tier 保持 + data_unreliable"读侧整批 0 开, 净效果相同 (fail-closed 从严保留)。
        # 只标 data_unreliable=True, tier 保持独立源原值 (0 漂移), note 说明是"源旧保守"非"品种红"。
        block["data_unreliable"] = True
        block["stale"] = True
        block["note"] = ("data_health.json 源旧(距 ts %d > %ds) → 整批保守 0 开(data_unreliable, 读侧整批拦);"
                         " 品种 tier 保持独立源原值(0 漂移), 不谎报全红; data_unreliable 在源旧期恒 True"
                         " (data_health 米=盘窗/分析频率, 跟不上 30min 体温表, 属预期保守非故障)"
                         % (now_ts - h_ts, max_age))
        if src_stale:
            block["note"] += (" [11-04 源冻结实报: 生产者按米快照 mtime 自标 stale(source_age_s=%s),"
                              " 快照池停写, 待 30min 循环快照刷新步复写]" % h.get("source_age_s"))
    else:
        block["data_unreliable"] = False
        block["stale"] = False
    return block


def main():
    now_ts = int(time.time())
    gov = _load("governor_state.json")
    po = _load("pending_orders_state.json")
    freeze = _load("crypto_freeze_gate.json")
    er = _load("event_risk.json")
    # [L4 2026-10-26] 退役冻结闸数据源合并(同币系冻结桥模式: gate 文件→risk_state 字段, 循环读方 hook 归研发 stage 包)
    # 真咬合双保险已挂既有闸源: pending_orders_state.symbol_pause(3支, 循环 hook 10-13 兼容读) + edge_tracker scale=0(0生成0放大)
    retire = _load("retire_freeze_gate.json")
    # [L5 2026-11-03 clobber 持久修, L4 指派码格] L4 连亏/冷却锁独立写位(洞①同型 读-合并):
    # D 侧此前每轮整份重建 risk_state.json, consec/24h 只从 pending_orders_state 单源取,
    # L4 桥接进本体的锁下拍必被冲回(11-03 实锤: 桥 consec=3 被冲回 consec=2/active=false, 只咬一拍)。
    # 现 L4 锁走独立闸源 l4_consec_bridge.json (producer=L4), 本轮读-合并, 从严取 max/min:
    #   consec = max(po侧, L4侧); cooldown_until = max(po侧, L4侧); scale 再 cap(只泄压不加息)。
    # 桥缺失=行为与旧版完全一致(0 副作用); 桥不可读=标 unreadable, 读侧可按从严处理。
    l4b = _load("l4_consec_bridge.json")
    l4b_present = bool(l4b)
    l4b_readable = l4b_present and isinstance(l4b, dict)
    l4b_consec = int(l4b.get("consec_losses", 0) or 0) if l4b_readable and l4b.get("active") else 0
    l4b_until = int(l4b.get("cooldown_until", 0) or 0) if l4b_readable and l4b.get("active") else 0
    l4b_scale_cap = l4b.get("scale_cap") if l4b_readable and l4b.get("active") else None

    # 当日已实现P&L (销账口径: 只算平仓 deal, 浮盈不计)
    day_date = po.get("day_realized_date")
    today = datetime.date.today().strftime("%Y-%m-%d")
    daily_pnl = float(po.get("day_realized_pnl", 0.0)) if day_date == today else 0.0

    # -10% 熔断进度: 当日已实现亏损 占 净值的百分比 (L1 日级闸, 用户钦定10%)
    equity = float(gov.get("peak_equity") or 1000.0)
    circuit_pct = max(0.0, -daily_pnl) / equity * 100.0 if equity > 0 else 0.0

    # 连亏 / 冷却 [11-03 clobber 持久修: L4 桥 l4_consec_bridge.json 读-合并, 从严取 max,
    # 锁到期自然失效(cooldown_until 过点即 False), 无需额外撤销步骤]
    consec_po = int(po.get("consec_losses", 0) or 0)
    cooldown_until_po = int(po.get("cooldown_until", 0) or 0)
    consec = max(consec_po, l4b_consec)
    cooldown_until = max(cooldown_until_po, l4b_until)
    in_cooldown = cooldown_until > int(time.time())

    # 币系冻结桥
    frozen = bool(freeze.get("active", False))
    freeze_until = freeze.get("until_ts")

    # 新单缩放 = min(回撤刹车scale, 事件面scale) —— 只泄压不加息
    scale = min(float(gov.get("risk_scale", 1.0) or 1.0),
                float(er.get("new_entry_scale", 1.0) or 1.0))
    if in_cooldown or er.get("level") in ("HIGH", "HALT") \
            or bool(er.get("halt_new_entries")) or circuit_pct >= 100:
        scale = 0.0
    # [11-03 clobber 持久修] L4 桥 scale_cap: 只泄压不加息, L4 锁再压一道底
    if l4b_scale_cap is not None:
        scale = min(scale, float(l4b_scale_cap))

    state = {
        "ts": int(time.time()),
        "beijing": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "heat": {
            "live": float(gov.get("live_heat", 0.0)),
            "latent": float(gov.get("latent_heat", 0.0)),
            "cluster": float(gov.get("cluster_heat", 0.0)),
            "cluster_side": gov.get("cluster_side"),
        },
        "net_dir": gov.get("net_dir", 0.0),
        "net_side": gov.get("net_side"),
        "clusters": {"crypto_cluster_max_pos": 4,
                     "crypto_cluster_heat": float(gov.get("cluster_heat", 0.0))},
        "drawdown_brake_scale": {
            "dd_pct": gov.get("dd_pct", 0.0),
            "state": gov.get("dd_state", "normal"),
            "scale": float(gov.get("risk_scale", 1.0)),
        },
        "daily_realized_pnl": daily_pnl,
        "10pct_circuit_progress": round(min(100.0, circuit_pct), 2),
        "consec_losses": consec,
        "24h_cooldown": {"active": in_cooldown, "until_ts": cooldown_until,
                         "trigger": "consec_losses>=3 -> 24h 账户冷却"},
        # [11-03 clobber 持久修] L4 桥审计位: 双源值全摊开, 读侧一眼看清锁来自谁
        "l4_consec_bridge": {
            "present": l4b_present, "readable": l4b_readable,
            "active": (bool(l4b.get("active")) if l4b_readable else None),
            "l4_consec_losses": l4b_consec, "l4_cooldown_until": l4b_until,
            "l4_scale_cap": l4b_scale_cap,
            "po_consec_losses": consec_po, "po_cooldown_until": cooldown_until_po,
            "merged_consec_losses": consec, "merged_until": cooldown_until,
            "note": "L4 独立写位(producer=L4 risk-officer), D 侧每轮读-合并取从严值; 桥缺失=行为同旧版; 锁过期自动失效"},
        "coin_freeze": {"active": frozen, "until_ts": freeze_until,
                        "source": freeze.get("source", "")},
        # [L4 2026-10-26] 退役冻结桥(WFO DIV 族主动退役, @chief 裁定a): scope=3支新腿0开, POLUSD 排除(币系轴),
        # 不置 halt_new_entries(全市场 HALT 误伤金银线, 币系冻结同规矩). 读方 hook 由研发 stage 包落.
        "retire_freeze": {"active": bool(retire.get("active", False)),
                          "scope_symbols": retire.get("scope_symbols", []),
                          "exclude_symbols": retire.get("exclude_symbols", []),
                          "until_ts": retire.get("until_ts"),
                          "source": retire.get("source", "")},
        "event_level": er.get("level"),
        "halt_new_entries": bool(er.get("halt_new_entries", False)),
        "new_entry_scale": round(scale, 3),
        # 洞①读-合并 + 洞②reader + 洞③故障态: data_health 块每轮从独立 json 读合并, 消 clobber。
        # 读方(event_guard / 挂单三部)按 tier 判: red=该品种新腿 0 开(品种级硬闸), yellow=仓位再×0.5。
        "data_health": build_data_health_block(now_ts),
        # v2.0 日内亏损上限闸(1.5% 钦定, @chief 终审二选一取"真桥 risk_state + 挂单链 reader")。
        # 单源自产: 分子=平仓销账(pending_orders)+浮亏(_tmp_mt5snap.positions), 分母=活读净值; 随本体落盘, 无 clobber。
        # reader = run_trader.daily_loss_cap_gate(挂单链 CIO 段后, 账户级日闸, 不影响既有持仓管理)。
        "daily_loss_cap": build_daily_loss_cap_block(now_ts),
        "data_health_producer": "tools/data_health.py(独立 data_health.json 单源, 本体温表每轮读-合并)",
        "data_health_consumers": ["event_guard.read_risk_state()", "30min全链挂单三部品种级0开闸"],
        "policy": "只泄压不加息: 本文件只允许降 new_entry_scale / 停开新单, 绝不放大仓位; "
                  "币系冻结=品种类限制, 不置全市场 halt_new_entries (金银 MED 0.5x 线不受影响)",
        "consumers": ["portfolio_governor(第13部门)", "event_guard.py(事件快通道)",
                      "30min全链挂单三部 new_entry_scale 缩放"],
        # [2026-11-03 L5 consec 白名单格] 喂源口径审计位: 系统 mags / 排除 mags 摊开, B 段一段读齐
        "consec_magic_whitelist": _load("consec_magic_whitelist.json") or {},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print("[OK] risk_state.json 已落盘:", OUT)
    print(json.dumps(state, ensure_ascii=False)[:500])


if __name__ == "__main__":
    main()
