"""
Goldstrategy Guild v10.2 — 终极进化引擎
融合所有学习成果: 记忆+自适应+订单流+日历+渐进止盈

@status: EXPERIMENT — 实验分支: 渐进止盈+订单流+5连败冷却
"""
import sys,os,time,json,warnings
import numpy as np,pandas as pd
from datetime import datetime
warnings.filterwarnings('ignore')
BASE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,BASE)

# ═══════ 审度司 ═══════
MAX_LOT=0.01; MAX_TRADES=8; MAX_LOSS=5.0
COOLDOWN_2L=1800; COOLDOWN_3L=14400; COOLDOWN_5L=86400

CORR_GROUPS=[["BTCUSD","ETHUSD"],["EURUSD","GBPUSD","GBPJPY","USDJPY"],["XAUUSD"]]
WD=["XAUUSD","EURUSD","GBPUSD","USDJPY","GBPJPY","BTCUSD","ETHUSD"]
WE=["BTCUSD","ETHUSD"]
def gs(): return WD if datetime.now().weekday()<5 else WE

SESS={s:[(0,23)] for s in WD+WE}
def ins(s):
    h=datetime.now().hour
    for a,b in SESS.get(s,[(0,23)]):
        if a<=h<b: return True
    return False

# ═══════ 经济日历 (硬编码重大事件) ═══════
HIGH_IMPACT_EVENTS={
    "NFP":("美国非农",1),         # 每月第一个周五 20:30
    "CPI":("美国CPI",2),          # 每月 20:30
    "FOMC":("美联储利率决议",3),  # 每6周,通常在18:00
    "GDP":("美国GDP",4),         # 每季度
    "NFP_EU":("欧元区非农",5),
}
# 高危事件前/后不开单(分钟)
EVENT_BUFFER=30

def is_high_impact_event():
    """检测当前是否在重大经济事件附近 (日历过滤)"""
    n=datetime.now()
    # 非农: 每月第一个周五 20:30 GMT+8
    if n.weekday()==4 and n.day<=7:
        hh=n.hour*60+n.minute
        nfp_time=20*60+30
        evt_minutes=nfp_time  # 20:30
        # 20:00~21:00
        if abs(hh-evt_minutes)<=EVENT_BUFFER:
            return True,f"NFP {n.strftime('%m/%d')}"
    
    # CPI: 每月 20:30
    if n.day<=15:
        hh=n.hour*60+n.minute
        cpi_time=20*60+30
        if abs(hh-cpi_time)<=EVENT_BUFFER:
            return True,f"CPI {n.strftime('%m/%d')}"
    
    return False,""

# ═══════ 指标 ═══════
def catr(h,l):
    if len(h)<15: return float(np.mean(h[-5:]-l[-5:]))
    tr=np.maximum(h[1:]-l[1:],np.maximum(abs(h[1:]-l[:-1]),abs(l[1:]-h[:-1])))
    return float(pd.Series(tr).ewm(span=14).mean().iloc[-1])

def cadx(h,l,c):
    if len(c)<28: return 0
    p=14; tr=np.maximum(h[1:]-l[1:],np.maximum(abs(h[1:]-c[:-1]),abs(l[1:]-c[:-1])))
    u=h[1:]-h[:-1]; d=l[:-1]-l[1:]
    pdi=100*pd.Series(np.where((u>d)&(u>0),u,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
    mdi=100*pd.Series(np.where((d>u)&(d>0),d,0)).ewm(span=p).mean()/(pd.Series(tr).ewm(span=p).mean()+1e-10)
    return float((100*abs(pdi-mdi)/(pdi+mdi+1e-10)).ewm(span=p).mean().iloc[-1])

# ═══════ VOI/OIR 订单流 (用tick数据近似) ═══════
def calc_order_flow(sym):
    """计算买卖不平衡指标: >0 = 买压, <0 = 卖压"""
    import MetaTrader5 as mt5
    ticks=mt5.copy_ticks_from(sym,datetime.now(),200)
    if ticks is None or len(ticks)<50: return 0
    
    # 看价格变化方向推断买卖压力
    last_prices=[t[3] for t in ticks[-50:]]  # bid
    changes=np.diff(last_prices)
    up=sum(1 for c in changes if c>0)
    down=sum(1 for c in changes if c<0)
    total=up+down
    if total==0: return 0
    return (up-down)/total  # -1~1, >0=买压

# ═══════ 记忆系统 ═══════
MEM_FILE=os.path.join(BASE,"data","v10_memory.json")
class TradeMemory:
    def __init__(self):
        self.mem={}; self.load()
    def load(self):
        if os.path.exists(MEM_FILE):
            try:
                with open(MEM_FILE,'r',encoding='utf-8') as f: self.mem=json.load(f)
            except: self.mem={}
    def save(self):
        os.makedirs(os.path.dirname(MEM_FILE),exist_ok=True)
        with open(MEM_FILE,'w',encoding='utf-8') as f: json.dump(self.mem,f,indent=2)
    def record(self,sym,conditions,profit):
        if sym not in self.mem: self.mem[sym]=[]
        self.mem[sym].append({**conditions,"profit":round(profit,2),"time":datetime.now().isoformat()})
        if len(self.mem[sym])>500: self.mem[sym]=self.mem[sym][-500:]
        self.save()
    def should_skip(self,sym,conditions):
        if sym not in self.mem or len(self.mem[sym])<15: return False
        recent=self.mem[sym][-80:]
        closed=[t for t in recent if t.get("profit",0)!=0]
        if len(closed)<8: return False
        adx=conditions.get("adx",0); dr=conditions.get("direction","")
        zt=conditions.get("zone",""); tf=conditions.get("trend","")
        rg=conditions.get("regime","")
        hits=[]
        for t in closed:
            score=0
            if t.get("direction")==dr: score+=2
            if t.get("zone")==zt: score+=1
            if t.get("trend")==tf: score+=1
            if t.get("regime")==rg: score+=2
            if abs(t.get("adx",0)-adx)<4: score+=2
            if score>=5: hits.append(t)
        if len(hits)<3: return False
        wins=sum(1 for t in hits if t.get("profit",0)>0)
        if wins/len(hits)<0.20: return True
        last5=[t for t in closed[-5:] if t.get("close_reason")=="SL"]
        if len(last5)==5: return True
        return False
    def get_stats(self,sym):
        if sym not in self.mem: return {"trades":0,"wr":0,"profit":0}
        closed=[t for t in self.mem[sym] if t.get("profit") is not None and t.get("profit")!=0]
        if not closed: return {"trades":0,"wr":0,"profit":0}
        wins=sum(1 for t in closed if t.get("profit",0)>0)
        total=sum(t.get("profit",0) for t in closed)
        return {"trades":len(closed),"wr":round(wins/len(closed)*100,1),"profit":round(total,2)}

OPT_CFG={
    "BTCUSD":{"sl":1.2,"rr":2.2,"adx":18,"fast":12,"slow":26,"zm":1.0},
    "ETHUSD":{"sl":1.5,"rr":2.0,"adx":16,"fast":10,"slow":20,"zm":1.0},
    "XAUUSD":{"sl":1.5,"rr":2.5,"adx":22,"fast":14,"slow":28,"zm":1.2},
    "EURUSD":{"sl":0.5,"rr":2.0,"adx":14,"fast":8,"slow":16,"zm":0.8},
    "GBPUSD":{"sl":0.5,"rr":2.0,"adx":14,"fast":8,"slow":16,"zm":0.8},
    "USDJPY":{"sl":0.5,"rr":2.0,"adx":14,"fast":8,"slow":16,"zm":0.8},
    "GBPJPY":{"sl":0.5,"rr":2.5,"adx":14,"fast":8,"slow":16,"zm":0.8},
}
MAGIC={"BTCUSD":20261020,"ETHUSD":20261021,"XAUUSD":20261022,
       "EURUSD":20261023,"GBPUSD":20261024,"USDJPY":20261025,"GBPJPY":20261026}

class SDPv102:
    def __init__(self):
        import MetaTrader5 as m; self.m=m; self.sd=None
        self.dp=0.0; self.dt=0; self.cd=0; self.cl=0
        self.td=datetime.now().date(); self._ld=None
        self.mem=TradeMemory()
        self._open_conds={}

    def conn(self):
        m=self.m
        for p in [r"C:\Program Files\TMGM MT5 Terminal\terminal64.exe",
                   r"C:\Program Files\MetaTrader 5\terminal64.exe"]:
            if os.path.exists(p) and m.initialize(path=p): break
        else: m.initialize()
        if not m.login(60043976,password="",server="TradeMaxGlobal-Demo"): return False
        for s in gs(): m.symbol_select(s,True)
        return True

    def check_corr(self,sym):
        for grp in CORR_GROUPS:
            if sym not in grp: continue
            for sib in grp:
                if sib!=sym and self.m.positions_get(symbol=sib): return False
        return True

    def manage_positions_advanced(self):
        """渐进止盈: 0.5R保本→1R锁50%→2R锁75%"""
        m=self.m
        for s in gs():
            p=m.positions_get(symbol=s)
            if not p: continue
            x=p[0]
            e=float(x.price_open); cu=float(x.price_current)
            sd=1 if x.type==0 else -1; d_=(cu-e)*sd; sl=float(x.sl); tp=float(x.tp)
            r_=abs(e-sl)
            if r_<=0: continue
            mult=d_/r_
            
            # 渐进止盈里程碑
            if mult>2.0:
                b=e+1.5*r_*sd  # 锁75%利润
                if (sd==1 and sl<b) or (sd==-1 and sl>b):
                    m.order_send({"action":m.TRADE_ACTION_SLTP,"symbol":s,"position":x.ticket,
                        "sl":round(b,2),"tp":tp})
            elif mult>1.0:
                b=e+0.5*r_*sd  # 锁50%利润
                if (sd==1 and sl<b) or (sd==-1 and sl>b):
                    m.order_send({"action":m.TRADE_ACTION_SLTP,"symbol":s,"position":x.ticket,
                        "sl":round(b,2),"tp":tp})
            elif mult>0.5:
                if (sd==1 and sl<e) or (sd==-1 and sl>e):  # 保本
                    m.order_send({"action":m.TRADE_ACTION_SLTP,"symbol":s,"position":x.ticket,
                        "sl":round(e,2),"tp":tp})

    def analyze(self,sym):
        """终极融合: 记忆+自适应+订单流+日历"""
        m=self.m; c=OPT_CFG[sym]
        
        # ── 经济日历过滤 ──
        evt,_=is_high_impact_event()
        if evt: return None
        
        # ── 订单流感知 ──
        of=calc_order_flow(sym)
        
        # H1数据
        h1=m.copy_rates_from_pos(sym,m.TIMEFRAME_H1,0,60)
        if h1 is None or len(h1)<30: return None
        h1d=pd.DataFrame(h1)
        h1c=h1d["close"].values; h1h=h1d["high"].values; h1l=h1d["low"].values
        cp=h1c[-1]; atr=catr(h1h,h1l)
        adx=cadx(h1h[-30:],h1l[-30:],h1c[-30:])
        if adx<c["adx"]: return None
        
        # 市场状态
        h4_full=m.copy_rates_from_pos(sym,m.TIMEFRAME_H4,0,40)
        h4_adx=0
        if h4_full is not None and len(h4_full)>30:
            h4d_full=pd.DataFrame(h4_full)
            h4_adx=cadx(h4d_full["high"].iloc[-30:].values,h4d_full["low"].iloc[-30:].values,
                        h4d_full["close"].iloc[-30:].values)
        regime="trend"
        if h4_adx<20 and adx<20: regime="ranging"
        if h4_adx>35: regime="strong_trend"
        atr_hist=[]
        for j in range(max(0,30-40),30):
            haj=catr(h1h[max(0,j-14):j+1],h1l[max(0,j-14):j+1])
            atr_hist.append(haj)
        if atr_hist and atr>np.mean(atr_hist)*1.8: regime="volatile"
        
        sl_mult=c["sl"]; rr_mult=c["rr"]
        if regime=="ranging": sl_mult=min(sl_mult*0.7,0.8); rr_mult=max(rr_mult*0.8,1.5)
        elif regime=="strong_trend": sl_mult=max(sl_mult*1.2,1.0); rr_mult=rr_mult*1.2
        elif regime=="volatile": return None
        
        fast_ema=pd.Series(h1c).ewm(span=c["fast"]).mean().iloc[-1]
        slow_ema=pd.Series(h1c).ewm(span=c["slow"]).mean().iloc[-1]
        trend="UP" if fast_ema>slow_ema else "DOWN"
        
        # H4供需区
        h4=m.copy_rates_from_pos(sym,m.TIMEFRAME_H4,0,40)
        if h4 is None or len(h4)<20: return None
        h4d=pd.DataFrame(h4); h4a=catr(h4d["high"].values,h4d["low"].values)
        from strategies.supply_demand import SupplyDemandSMC
        if self.sd is None: self.sd=SupplyDemandSMC({"slb":15,"bmb":2,"bmx":10,"rmn":0.20,"rmx":0.85})
        zo=self.sd.detect_zones(h4d.iloc[-30:])
        price=cp; zm=c["zm"]
        zc=None; zt=None; flip=False
        for z in zo.get("demand",[]):
            if z.strength>=zm and price>z.top and price-z.top<h4a*3: zc,zt=z,"D"; break
        if not zc:
            for z in zo.get("supply",[]):
                if z.strength>=zm and price<z.bottom and z.bottom-price<h4a*3: zc,zt=z,"S"; break
        if not zc:
            for z in zo.get("supply",[]):
                if price>z.top: zc,zt=z,"D"; flip=True; break
        if not zc:
            for z in zo.get("demand",[]):
                if price<z.bottom: zc,zt=z,"S"; flip=True; break
        if not zc: return None
        
        dr="BUY" if trend=="UP" and zt=="D" else "SELL" if trend=="DOWN" and zt=="S" else None
        if not dr: return None
        
        # 订单流增强: 方向与买卖压力一致才做
        if of>0.3 and dr=="SELL": return None  # 买压强却要做空→放弃
        if of<-0.3 and dr=="BUY": return None  # 卖压强却要做多→放弃
        
        conds={
            "direction":dr,"zone":zt,"zone_type":"flip" if flip else "fresh",
            "adx":round(adx,1),"trend":trend,"atr":round(atr,1),
            "regime":regime,"h4_adx":round(h4_adx,1),"orderflow":round(of,2),
            "symbol":sym
        }
        if self.mem.should_skip(sym,conds):
            conds["skipped"]=True; self.mem.record(sym,conds,0); return None
        
        t=m.symbol_info_tick(sym)
        if not t: return None
        entry=t.ask if dr=="BUY" else t.bid
        if dr=="BUY": sl=entry-atr*sl_mult; tp=entry+(entry-sl)*rr_mult
        else: sl=entry+atr*sl_mult; tp=entry-(sl-entry)*rr_mult
        
        return {"sym":sym,"d":dr,"p":entry,"sl":sl,"tp":tp,
                "r":f"V{regime[0].upper()}{'F' if flip else zt}","c":conds}

    def exec(self,sig):
        m=self.m; s=sig["sym"]; c=MAGIC[s]; t=m.symbol_info_tick(s)
        if not t: return False
        p=t.ask if sig["d"]=="BUY" else t.bid
        ot=m.ORDER_TYPE_BUY if sig["d"]=="BUY" else m.ORDER_TYPE_SELL
        sl=round(sig["sl"],2); tp=round(sig["tp"],2)
        for f in [m.ORDER_FILLING_IOC,m.ORDER_FILLING_FOK]:
            r=m.order_send({"action":m.TRADE_ACTION_DEAL,"symbol":s,"volume":MAX_LOT,
                "type":ot,"price":p,"sl":sl,"tp":tp,"deviation":200,
                "magic":c,"comment":"v10.2","type_time":m.ORDER_TIME_GTC,"type_filling":f})
            if r and r.retcode==m.TRADE_RETCODE_DONE:
                self._open_conds[r.order]=sig["c"]; return True
        return False

    def run(self):
        m=self.m
        log=lambda x: print(f"[{datetime.now().strftime('%H:%M:%S')}] {x}",flush=True)
        wd="周末" if datetime.now().weekday()>=5 else "工作日"
        log(f"v10.2 终极进化 | {wd} | {len(gs())}品种")
        log(f"  融合: 记忆+自适应+订单流+日历+渐进止盈")
        
        while True:
            try:
                n=datetime.now()
                if n.date()!=self.td: self.td=n.date(); self.dt=0; self.dp=0.0
                if time.time()<self.cd: time.sleep(5); continue
                
                # 渐进止盈
                self.manage_positions_advanced()
                
                # 平仓记录
                h=m.history_deals_get(n.replace(hour=0,minute=0,second=0),n)
                if h:
                    for d in h[-10:]:
                        if "v10.2" in (d.comment or "") and d.profit!=0 and d.ticket!=self._ld:
                            self._ld=d.ticket
                            cr="TP" if d.profit>0 else "SL"
                            conds=self._open_conds.pop(d.ticket,{})
                            conds["close_reason"]=cr
                            self.mem.record(d.symbol,conds,d.profit)
                            if d.profit<0:
                                self.cl+=1
                                if self.cl>=5: self.cd=time.time()+COOLDOWN_5L
                                elif self.cl>=3: self.cd=time.time()+COOLDOWN_3L
                                elif self.cl>=2: self.cd=time.time()+COOLDOWN_2L
                            else: self.cl=0
                            st=self.mem.get_stats(d.symbol)
                            log(f"[CLOSE] {d.symbol} {'W' if d.profit>0 else 'L'} ${d.profit:.2f} | {st['trades']}笔WR{st['wr']}%")
                
                if self.dt>=MAX_TRADES or time.time()<self.cd: time.sleep(5); continue
                
                # 交易
                for s in gs():
                    if m.positions_get(symbol=s): continue
                    if not ins(s): continue
                    if not self.check_corr(s): continue
                    sig=self.analyze(s)
                    if sig and self.exec(sig):
                        self.dt+=1
                        log(f"[TRADE] {s} {sig['d']} @ ${sig['p']:.2f} | {sig['r']}")
                
                time.sleep(10)
            except KeyboardInterrupt: log("停止"); break
            except Exception as e: log(f"[ERR] {e}"); time.sleep(30)
        m.shutdown()

if __name__=="__main__":
    e=SDPv102()
    if e.conn(): e.run()
