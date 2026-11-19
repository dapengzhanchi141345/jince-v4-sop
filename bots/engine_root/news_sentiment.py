"""
NewsSentiment — 新闻情感分析模块
用NewsAPI获取实时新闻 + VADER情感打分
集成到Gen3引擎作为市场情绪过滤
"""
import os,json,requests,time
from datetime import datetime,timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

BASE=os.path.join(os.path.dirname(os.path.abspath(__file__)),"data")
CACHE_FILE=os.path.join(BASE,"news_cache.json")
API_KEY="demo"  # NewsAPI免费key, 注册后替换

class NewsSentiment:
    def __init__(self):
        self.sia=SentimentIntensityAnalyzer()
        self.cache={}
        self._load_cache()
    
    def _load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE,'r',encoding='utf-8') as f: self.cache=json.load(f)
            except: self.cache={}
    
    def _save_cache(self):
        os.makedirs(BASE,exist_ok=True)
        with open(CACHE_FILE,'w',encoding='utf-8') as f: json.dump(self.cache,f,indent=2)
    
    def fetch_news(self,query,page_size=5):
        """获取新闻标题并返回情感得分"""
        today=datetime.now().strftime("%Y-%m-%d")
        cache_key=f"{query}_{today}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            url=f"https://newsapi.org/v2/everything?q={query}&language=en&pageSize={page_size}&apiKey={API_KEY}"
            # 如果API_KEY是demo, 返回模拟数据
            if API_KEY=="demo":
                result=self._simulate(query)
            else:
                resp=requests.get(url,timeout=10)
                if resp.status_code==200:
                    articles=resp.json().get("articles",[])
                    if articles:
                        texts=[a["title"] for a in articles[:page_size]]
                        scores=[self.sia.polarity_scores(t)["compound"] for t in texts]
                        avg_score=sum(scores)/len(scores) if scores else 0
                        result={"score":round(avg_score,3),"count":len(scores),"texts":texts[:3]}
                    else:
                        result=self._simulate(query)
                else:
                    result=self._simulate(query)
        except:
            result=self._simulate(query)
        
        self.cache[cache_key]=result
        self._save_cache()
        return result
    
    def _simulate(self,query):
        """API不可用时模拟数据"""
        sim_data={
            "bitcoin":0.25,"btc":0.25,"crypto":0.15,"ethereum":0.20,
            "gold":0.10,"xau":0.10,"silver":0.05,
            "usd":-0.10,"eur":0.05,"gbp":0.02,"jpy":-0.05,
            "inflation":-0.30,"fed":-0.15,"rate":-0.10,
            "stock":0.10,"market":0.05,"economy":-0.05,
        }
        base=0.0
        for k,v in sim_data.items():
            if k in query.lower():
                base=v
                break
        # 加一些随机变化
        import random
        base+=random.uniform(-0.15,0.15)
        return {"score":round(base,3),"count":3,"texts":["[模拟数据] 新闻API未配置"]}
    
    def get_market_sentiment(self):
        """获取综合市场情绪"""
        queries={
            "BTCUSD":["bitcoin","btc","crypto"],
            "ETHUSD":["ethereum","eth","crypto"],
            "XAUUSD":["gold","xau","precious metals"],
            "EURUSD":["euro","eur","ecb"],
            "GBPUSD":["pound","gbp","boe"],
            "USDJPY":["japan yen","jpy","boj"],
            "GBPJPY":["pound","gbp","japan"],
        }
        result={}
        for sym,keywords in queries.items():
            scores=[]
            for kw in keywords:
                data=self.fetch_news(kw,3)
                scores.append(data["score"])
            avg=sum(scores)/len(scores) if scores else 0
            result[sym]={
                "score":avg,
                "label":"positive" if avg>0.2 else ("negative" if avg<-0.2 else "neutral"),
                "strength":abs(avg)
            }
        return result
    
    def should_skip_for_news(self,sym,direction):
        """基于新闻情绪判断是否跳过"""
        sentiment=self.get_market_sentiment()
        s=sentiment.get(sym,{})
        score=s.get("score",0)
        label=s.get("label","neutral")
        
        # 新闻情绪强烈相反 → 跳过
        if direction=="BUY" and label=="negative" and abs(score)>0.3:
            return True,f"NewsNeg({score})"
        if direction=="SELL" and label=="positive" and abs(score)>0.3:
            return True,f"NewsPos({score})"
        
        return False,""

if __name__=="__main__":
    ns=NewsSentiment()
    print("=== 市场情绪 ===")
    sentiment=ns.get_market_sentiment()
    for sym,data in sentiment.items():
        bar="+" if data["score"]>0 else ""
        print(f"{sym}: {data['label']:>8} ({bar}{data['score']:.3f})")
    
    print()
    print("=== 跳过检查 ===")
    for sym in ["BTCUSD","XAUUSD","EURUSD"]:
        skip,reason=ns.should_skip_for_news(sym,"BUY")
        print(f"{sym} BUY: {'SKIP' if skip else 'OK'} {reason}")
        skip,reason=ns.should_skip_for_news(sym,"SELL")
        print(f"{sym} SELL: {'SKIP' if skip else 'OK'} {reason}")
