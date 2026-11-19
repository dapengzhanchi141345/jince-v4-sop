"""风控位·换网分级冻结闸(确定性,不烧key,不碰MT5 live交易动作,只读tick/持仓/挂单判状态)。
探活三通道(按@chief口径分开,不拿外网空就说全系统断):
  ① MT5价源(broker专线)  ② 外网出口(判断岗/LLM吃它)  ③ GitHub(仅代码推,不伤交易)
分级->交易闸动作:
  LEVEL_2 价源断   : 全冻结(禁开+禁撤+禁改SL),只留痕
  LEVEL_1 价源活/外网断: 禁开新单(方向研判冻结在旧盘口窗+判断岗429), 已有单可管理(撤/改SL走专线),留痕
  LEVEL_0 全活    : 交易闸按常规双闸
开单主路径(L884)读 data/risk_freeze_state.json 决定禁不禁开单。本脚本只产 state,不改开单循环。
"""
import json, os, re, datetime, urllib.request, urllib.error, threading
# 注意: 不在顶层 import MetaTrader5 — Windows 上无终端/无外网时该 import 本身会阻塞~55s,
# 必须放进 probe_mt5 的 daemon worker 里惰性导入(那里有 10s join 封顶 + os._exit 硬退), 主线程不被拖.
mt5 = None

BASE=os.path.dirname(os.path.abspath(__file__))
DATA=os.path.join(BASE,'data')

def _net_probe(url, timeout_s):
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as r:
            return True
    except Exception:
        return False

def probe_external(timeout=8):
    """外网出口探测. 硬封顶: Windows 外网断时 urlopen 的 DNS getaddrinfo 不受 timeout=8 约束能卡~30s,
    套 daemon 线程 join(timeout_s) 封顶, 主线程不被拖(钩子每30min跑不能白等)."""
    if timeout is None: timeout = 8
    box = {}
    def _run():
        try: box['r'] = _net_probe("https://api.ipify.org", timeout)
        except Exception: box['r'] = False
    t = threading.Thread(target=_run, name="extprobe", daemon=True); t.start()
    t.join(min(timeout+4, 14))
    if t.is_alive(): return False   # 超时=按外网断处理(已封顶, 不join卡住的worker)
    return box.get('r', False)

def probe_github(timeout=8):
    """GitHub 可达探测. 同 probe_external 的硬封顶逻辑(Windows DNS 会卡)."""
    if timeout is None: timeout = 8
    box = {}
    def _run():
        try: box['r'] = _net_probe("https://github.com", timeout)
        except Exception: box['r'] = False
    t = threading.Thread(target=_run, name="ghprobe", daemon=True); t.start()
    t.join(min(timeout+4, 14))
    if t.is_alive(): return False
    return box.get('r', False)

def probe_dst_freeze():
    """DST挂单簿冻结令(risk_officer 11-02生死测定死前): 读 resolve_session_window.py 的 SERVER_PENDING_VERIFY.
    True = 挂单钟点行为层未验 -> 无论网络几级, 挂新单全禁(只撤/改已有单). 读不到 flag 默认 True(fail-closed)."""
    try:
        import pathlib
        p = pathlib.Path(BASE)/"multi_agent/research/strategy_rd/resolve_session_window.py"
        src = p.read_text(encoding='utf-8')
        m = re.search(r"SERVER_PENDING_VERIFY\s*=\s*(True|False)", src)
        return (m.group(1)=="True") if m else True
    except Exception:
        return True

def _probe_mt5_inner():
    """worker 内惰性 import MetaTrader5(顶层不 import, 否则 Windows 无终端时 import 本身卡~55s 拖主线程)."""
    import MetaTrader5 as _mt5
    live=False; bid=None
    try:
        ok=_mt5.initialize()
        if ok:
            t=_mt5.symbol_info_tick('XAUUSD')
            if t and t.bid and t.bid>0:
                # [2026-10-10] tick 新鲜度判活: 只看 bid>0 会把 8.6h 前的旧 tick 误判活(实测今晨价源停更后 bid 一直 4194.42 不动).
                # 券商 tick 时间戳停更 >30min = 行情源死 -> 价源按断(LEVEL_2 全冻结), 别拿旧价当活价放行.
                import time as _time_mod
                age = _time_mod.time() - t.time
                if age > 1800:
                    live=False  # 旧 tick: 不算活, bid 仍记上留痕但不放行
                else:
                    live=True
                bid=round(t.bid,2)
            ps=_mt5.positions_get() or []
            os_=[o for o in (_mt5.orders_get() or [])]
            manage=live  # 价源活=trader context活=撤/改SL可发
        else:
            manage=False; ps=[]; os_=[]
    except Exception:
        live=False; manage=False; ps=[]; os_=0
    return live,bid,manage,len(ps),len(os_)

def probe_mt5(timeout_s=10):
    """带线程硬超时: MT5 无外网/重连时 initialize() 会阻塞(旧版挂满~60s), 10s 不返回=按价源断(LEVEL_2)处理, 闸快速返回.
    用 daemon 线程 + 结果容器, 超时主线程不被拖(卡住的 worker 是 daemon, 进程退出时自清, 不 join)."""
    box = {}
    def _run():
        try:
            box['res'] = _probe_mt5_inner()
        except Exception:
            box['res'] = (False, None, False, 0, 0)
    t = threading.Thread(target=_run, name="mt5probe", daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return False, None, False, 0, 0   # 超时: 价源按断(LEVEL_2)处理, 全冻结只留痕
    return box.get('res', (False, None, False, 0, 0))


def load_intraday_policy():
    """10-07 用户令'松闸加快日内交易': 持久参数, 全链循环不碰此文件(手写),
    重算时读到就生效: 价源活时允许开日内单(12h内必平), 外网断不再自动禁开; 币系仍冻.
    缺失/读失败=默认关(fail-closed 回旧行为)."""
    try:
        p = json.load(open(os.path.join(DATA, 'intraday_policy.json'), encoding='utf-8'))
        return p if p.get("enabled") else {}
    except Exception:
        return {}

def main():
    mt5_live,bid,manage,np_,no_=probe_mt5()
    ext=probe_external(); gh=probe_github(); dst=probe_dst_freeze()
    intraday=load_intraday_policy()
    now=int(datetime.datetime.now().timestamp())
    if not mt5_live:
        lvl=2; action={"ban_open":True,"ban_cancel":True,"ban_modify_sl":True,"manage_existing":False}
        note="价源(broker专线)断:全冻结,只留痕,撤/改SL都做不了(连不上MT5)"
    elif not ext and intraday:
        # 10-07 用户令: 外网断不再自动禁开新单 — 价源活即可开日内单(本地tick足够),
        # 日内铁线12h必平/禁overnight写进state持久保留; 币系仍冻(币系开单由
        # crypto_freeze_gate/risk_state.coin_freeze 单独管, 此处只管新单闸不禁币系之外的FX/金/G10).
        lvl=1; action={"ban_open":False,"ban_cancel":False,"ban_modify_sl":False,"manage_existing":manage}
        note="价源活/外网断: 日内策略生效(10-07用户令松闸) — 允许开日内单(%dh必平,禁overnight), 方向研判缺新外网数据则降级半仓, 撤/改SL照旧"%intraday.get("hold_max_hours",12)
    elif not ext:
        lvl=1; action={"ban_open":True,"ban_cancel":False,"ban_modify_sl":False,"manage_existing":manage}
        note="价源活/外网断(换网后常态):禁开新单(方向研判冻结在旧盘口窗+判断岗429),已有单撤/改SL走专线可执行"
    else:
        lvl=0; action={"ban_open":False,"ban_cancel":False,"ban_modify_sl":False,"manage_existing":manage}
        note="全活:交易闸按常规双闸"
        if intraday:
            note+=" | 日内策略: %dh必平禁overnight"%intraday.get("hold_max_hours",12)
    # DST挂单簿冻结令(risk_officer 11-02生死测): 管币系+隔夜持仓, 但日内FX/金/G10单可过(10-07用户令"松闸加快日内").
    if dst:
        if intraday and intraday.get("intraday_only"):
            # 日内策略生效时, DST 只冻币系+禁overnight, 不冻日内FX/金/G10单
            action["ban_open"]=False  # 日内单放行(币系由coin_freeze单独管)
            note+=" | DST: 币系冻(11-02 NFP), 日内FX/金/G10放行(12h必平禁overnight)"
            lvl_note_ext=" (DST币系冻, 日内松)"
        else:
            action["ban_open"]=True
            if lvl==0:
                note="全活但DST挂单簿冻结令仍生效(SERVER_PENDING_VERIFY=True, 11-02生死测定死前): 禁开新单, 只撤/改已有单"
                lvl_note_ext=" (DST冻结叠加)"
            else:
                lvl_note_ext=""
    else:
        lvl_note_ext=""
    state={"level":lvl,"mt5_live":mt5_live,"external_live":ext,"github_live":gh,"xau_bid":bid,
           "dst_freeze":dst,"positions":np_,"pending_orders":no_,"ts":now,"note":note,
           "policy":{"open_new_order":(not action["ban_open"]),
                     "cancel_existing":not action["ban_cancel"],
                     "modify_sl":not action["ban_modify_sl"],
                     "manage_existing_only":(lvl==1)}}
    # 日内铁线持久(每轮重算都带上, 不被冲掉)
    if intraday:
        state["intraday_only"]=intraday.get("intraday_only",True)
        state["hold_max_hours"]=intraday.get("hold_max_hours",12)
        state["coin_freeze"]=intraday.get("coin_freeze",True)
        state["intraday_note"]=intraday.get("note","")
    open(os.path.join(DATA,'risk_freeze_state.json'),'w',encoding='utf-8').write(json.dumps(state,ensure_ascii=False,indent=1))
    # 留痕
    v={"ts":now,"sym":"ALL","decision":"RISK-NET-GATE","gate":"risk-network","level":lvl,
       "dst_freeze":dst,"channels":{"mt5":mt5_live,"external":ext,"github":gh},"xau_bid":bid,
       "reason":note,"data":"MT5+urllib实拉%d 换网分级冻结闸(含DST挂单簿冻结令并进口径)"%now}
    with open(os.path.join(DATA,'veto_log.jsonl'),'a',encoding='utf-8') as f:
        f.write(json.dumps(v,ensure_ascii=False)+"\n")
    print("LEVEL=%d | dst_freeze=%s | mt5=%s(外网=%s/github=%s) | bid=%s 持仓=%d 挂单=%d"%(lvl,dst,mt5_live,ext,gh,bid,np_,no_))
    print("ACTION:",json.dumps(action,ensure_ascii=False))
    print("NOTE:",note,flush=True)
    # 硬退: MT5 在 worker 线程里起的是非 daemon 线程, 解释器正常退出时会 threading._shutdown join 它拖满~55s;
    # state+留痕+stdout 已全部落盘, 直接 os._exit(0) 强退不 join, 钩子(每30min跑)不白等.
    os._exit(0)

if __name__=="__main__":
    main()
