import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf
from datetime import datetime
import requests, os, json, time
# ─── EXPIRY + VIX-ADJUSTED BSM PRICING (BearIQ) ───────────────────
import math as _math, calendar as _cal
from datetime import timedelta as _td

def get_nifty_weekly_expiry():
    """NIFTY weekly expiry = next Tuesday (NSE rule since Sep 2025)"""
    today=datetime.now()
    d=today
    # If today is Tuesday before 3:30pm, today is expiry; else next Tuesday
    days_ahead=(1-today.weekday())%7  # 1=Tuesday
    if days_ahead==0 and today.hour>=16: days_ahead=7
    elif days_ahead==0: days_ahead=0
    exp=today+_td(days=days_ahead)
    return exp.replace(hour=15,minute=30,second=0,microsecond=0)

def get_monthly_expiry_tuesday(year,month):
    """Last Tuesday of month = monthly expiry"""
    last=_cal.monthrange(year,month)[1]
    d=datetime(year,month,last)
    while d.weekday()!=1: d-=_td(days=1)
    return d

def get_banknifty_expiry():
    """BANKNIFTY = monthly only (last Tuesday). No weekly since Nov 2024."""
    today=datetime.now()
    exp=get_monthly_expiry_tuesday(today.year,today.month)
    # If this month's expiry passed, use next month
    if (exp.date()-today.date()).days<0:
        nm=today.month+1 if today.month<12 else 1
        ny=today.year if today.month<12 else today.year+1
        exp=get_monthly_expiry_tuesday(ny,nm)
    return exp.replace(hour=15,minute=30,second=0,microsecond=0)

def get_expiry_for(instrument):
    """Returns (expiry_date, days_to_expiry, label) for instrument"""
    if instrument=="BANKNIFTY":
        exp=get_banknifty_expiry()
    else:
        exp=get_nifty_weekly_expiry()
    days=max((exp.date()-datetime.now().date()).days,0)
    label=exp.strftime("%d %b %Y")
    return exp,days,label

def bsm_put(S,K,days,vol,r=0.065,vix=15):
    """VIX-adjusted Black-Scholes put premium"""
    T=max(days/365,0.002)
    vix_impl=vix/100
    vix_mult=max(vix/15,1.0)
    eff=max((0.4*vol+0.6*vix_impl)*vix_mult,0.12)
    sig=min(eff,1.0)
    def nc(x): return 0.5*(1+_math.erf(x/_math.sqrt(2)))
    try:
        d1=(_math.log(S/K)+(r+0.5*sig**2)*T)/(sig*_math.sqrt(T))
        d2=d1-sig*_math.sqrt(T)
        return max(round(K*_math.exp(-r*T)*nc(-d2)-S*nc(-d1),1),0.5)
    except: return max(round(S*0.008),1)

def get_index_vol(ticker,fallback=0.14):
    """Historical vol for index"""
    try:
        h=yf.Ticker(ticker).history(period="60d",interval="1d")
        if h.empty: return fallback
        rets=h["Close"].pct_change().dropna()
        return round(float(rets.std()*_math.sqrt(252)),3) if len(rets)>=5 else fallback
    except: return fallback

def get_live_vix_val():
    try:
        h=yf.Ticker("^INDIAVIX").history(period="1d",interval="5m")
        return round(float(h["Close"].iloc[-1]),2) if not h.empty else 15
    except: return 15
# ──────────────────────────────────────────────────────────────────


st.set_page_config(page_title="BearIQ 3.0",page_icon="B",layout="wide",initial_sidebar_state="expanded")
st.markdown("""<style>
.stApp{background-color:#070b14;color:#e0e0e0}
[data-testid="stSidebar"]{background-color:#0a0f1e;border-right:1px solid #1a2840}
[data-testid="collapsedControl"]{display:block !important;visibility:visible !important;color:#ff4444 !important}
.card{background:#0d1626;border:1px solid #1a3050;border-radius:14px;padding:18px;text-align:center;margin-bottom:10px}
.ai-box{background:#00081a;border:1px solid #1a4080;border-left:4px solid #3388ff;border-radius:12px;padding:20px;margin:10px 0}
.section-title{font-size:0.82rem;font-weight:800;color:#3388cc;text-transform:uppercase;letter-spacing:3px;border-bottom:1px solid #1a2840;padding-bottom:8px;margin:22px 0 14px 0}
.stButton>button{background:#0a1830;color:#4488ff;border:1px solid #2255aa;border-radius:8px;font-weight:700;width:100%;padding:10px}
</style>""",unsafe_allow_html=True)

GROQ_URL="https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL="llama-3.3-70b-versatile"
NIFTY50=["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","SBIN","WIPRO","AXISBANK","LT","BAJFINANCE","MARUTI","TATAMOTORS","SUNPHARMA","ONGC","NTPC","POWERGRID","ULTRACEMCO","TATASTEEL","ADANIENT","HCLTECH","DIVISLAB","CIPLA","BHARTIARTL","GRASIM","TITAN","TECHM","BPCL","COALINDIA","APOLLOHOSP","HINDALCO"]
SECTORS={"BANK":{"ticker":"^NSEBANK","name":"Banking","icon":"🏦"},"IT":{"ticker":"^CNXIT","name":"IT","icon":"💻"},"AUTO":{"ticker":"^CNXAUTO","name":"Auto","icon":"🚗"},"PHARMA":{"ticker":"^CNXPHARMA","name":"Pharma","icon":"💊"},"METAL":{"ticker":"^CNXMETAL","name":"Metal","icon":"⚙️"},"FMCG":{"ticker":"^CNXFMCG","name":"FMCG","icon":"🛒"},"REALTY":{"ticker":"^CNXREALTY","name":"Realty","icon":"🏠"},"ENERGY":{"ticker":"^CNXENERGY","name":"Energy","icon":"⚡"}}

def load_key():
    for p in [os.path.join(os.path.expanduser("~"),"Desktop","BearIQ","config.txt"),os.path.join(os.path.dirname(os.path.abspath(__file__)),"config.txt"),"config.txt"]:
        if os.path.exists(p):
            k=open(p).read().strip()
            if k: return k
    return None

def groq(prompt,key,n=700):
    if not key: return "API key not found."
    try:
        r=requests.post(GROQ_URL,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},json={"model":GROQ_MODEL,"messages":[{"role":"user","content":prompt}],"temperature":0.5,"max_tokens":n},timeout=25)
        return r.json()["choices"][0]["message"]["content"] if r.status_code==200 else "Error "+str(r.status_code)
    except Exception as e: return "Error: "+str(e)

def card(lbl,val,clr,sub="",icon=""):
    return "<div class='card'><div style='font-size:0.68rem;color:#445566;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px'>"+icon+" "+lbl+"</div><div style='font-size:1.9rem;font-weight:900;color:"+clr+";margin:4px 0'>"+str(val)+"</div>"+(("<div style='font-size:0.75rem;color:#445566;margin-top:4px'>"+sub+"</div>") if sub else "")+"</div>"

def get_atm(price,step): return round(price/step)*step

@st.cache_data(ttl=60)
def fetch_market():
    tickers={"nifty":"^NSEI","banknifty":"^NSEBANK","finnifty":"NIFTY_FIN_SERVICE.NS","midcap":"^NSEMDCP50","vix":"^INDIAVIX","dow":"YM=F","crude":"CL=F","gold":"GC=F","usd_inr":"USDINR=X"}
    out={}
    for name,ticker in tickers.items():
        try:
            t=yf.Ticker(ticker)
            d=t.history(period="5d",interval="1d")
            h5=t.history(period="1d",interval="5m")
            h1m=t.history(period="1d",interval="1m")
            hhr=t.history(period="2d",interval="60m")
            if d.empty: continue
            c=d["Close"]
            prev=c.iloc[-2] if len(c)>1 else c.iloc[-1]
            p5=c.iloc[-5] if len(c)>4 else prev
            # Use most recent 1m data for live price if available
            if not h1m.empty and len(h1m)>0:
                curr=round(h1m["Close"].iloc[-1],2)
            elif not h5.empty and len(h5)>0:
                curr=round(h5["Close"].iloc[-1],2)
            else:
                curr=round(c.iloc[-1],2)
            pct1=round(((curr-prev)/prev)*100,2) if prev else 0
            pct5d=round(((curr-p5)/p5)*100,2) if p5 else 0
            m5=round(((h5["Close"].iloc[-1]-h5["Close"].iloc[-4])/h5["Close"].iloc[-4])*100,3) if not h5.empty and len(h5)>4 else 0
            m15=round(((h5["Close"].iloc[-1]-h5["Close"].iloc[-7])/h5["Close"].iloc[-7])*100,3) if not h5.empty and len(h5)>7 else 0
            vspd=round(((hhr["Close"].iloc[-1]-hhr["Close"].iloc[-2])/hhr["Close"].iloc[-2])*100,2) if not hhr.empty and len(hhr)>1 else 0
            out[name]={"price":curr,"pct_1d":pct1,"pct_2d":0,"pct_5d":pct5d,"mom_5m":m5,"mom_15m":m15,"vix_speed":vspd,
                        "prev_high":round(d["High"].iloc[-2],2) if len(d)>1 else curr,
                        "prev_low":round(d["Low"].iloc[-2],2) if len(d)>1 else curr,
                        "prev_close":round(prev,2)}
        except: pass
    return out

@st.cache_data(ttl=60)
def fetch_sectors():
    out={}
    for key,info in SECTORS.items():
        try:
            t=yf.Ticker(info["ticker"])
            d=t.history(period="5d",interval="1d")
            h=t.history(period="1d",interval="15m")
            if d.empty: continue
            c=d["Close"]; curr=c.iloc[-1]; prev=c.iloc[-2] if len(c)>1 else curr; p5=c.iloc[-5] if len(c)>=5 else prev
            p1d=round(((curr-prev)/prev)*100,2) if prev else 0
            p5d=round(((curr-p5)/p5)*100,2) if p5 else 0
            spd=round(((h["Close"].iloc[-1]-h["Close"].iloc[-4])/h["Close"].iloc[-4])*100,3) if not h.empty and len(h)>4 else 0
            status="DANGER" if p1d<-1.5 else "WEAK" if p1d<-0.5 else "NEUTRAL" if p1d<0.3 else "STRONG"
            out[key]={"name":info["name"],"icon":info["icon"],"price":round(curr,2),"pct_1d":p1d,"pct_5d":p5d,"detr_speed":spd,"status":status}
        except: pass
    return out

@st.cache_data(ttl=60)
def fetch_ad():
    """
    Professional A/D using 130+ stock universe
    Batch download for speed — same data as Market Breadth system
    """
    # Full NSE broad universe — same as beariq_breadth.py
    BROAD_UNIVERSE = [
        "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","SBIN",
        "BHARTIARTL","ITC","KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI",
        "SUNPHARMA","TITAN","BAJFINANCE","ULTRACEMCO","WIPRO","ONGC","NTPC",
        "TATAMOTORS","ADANIENT","HCLTECH","POWERGRID","M&M","NESTLEIND",
        "TATASTEEL","TECHM","COALINDIA","DRREDDY","DIVISLAB","BAJAJFINSV",
        "CIPLA","BRITANNIA","BPCL","EICHERMOT","GRASIM","HINDALCO",
        "INDUSINDBK","JSWSTEEL","APOLLOHOSP","ADANIPORTS","SBILIFE",
        "TATACONSUM","LTIM","BAJAJ-AUTO","HEROMOTOCO","HDFCLIFE","SHRIRAMFIN",
        "VEDL","SIEMENS","DLF","GODREJCP","MARICO","DABUR","NAUKRI",
        "HAVELLS","BERGEPAINT","MUTHOOTFIN","OFSS","LUPIN","TORNTPHARM",
        "AUROPHARMA","BANDHANBNK","FEDERALBNK","BIOCON","BALKRISIND",
        "COLPAL","PERSISTENT","TVSMOTOR","ASTRAL","CHOLAFIN","TRENT",
        "ZOMATO","IRCTC","MPHASIS","COFORGE","LTTS","KPITTECH","TATAELXSI",
        "DIXON","KAYNES","ZYDUSLIFE","ALKEM","IPCALAB","NATCOPHARM",
        "CANBK","BANKINDIA","UNIONBANK","INDIANB","PNB","IDFCFIRSTB",
        "RECLTD","PFC","IRFC","NHPC","SJVN","TATAPOWER","ADANIGREEN",
        "ASHOKLEY","ESCORTS","APOLLOTYRE","MRF","GODREJPROP","OBEROIRLTY",
        "PRESTIGE","PHOENIXLTD","SOBHA","BRIGADE","BANKBARODA","AUBANK",
        "MOTHERSON","BOSCHLTD","ABCAPITAL","MFSL","HDFCAMC","EDELWEISS",
        "PIIND","INDHOTEL","BERGEPAINT","PAGEIND","MCDOWELL-N","DMART",
    ]
    adv=0; dec=0; unch=0
    try:
        # Batch download — much faster than individual fetches
        tickers=[s+".NS" for s in BROAD_UNIVERSE]
        batch=yf.download(tickers,period="3d",interval="1d",
                         group_by="ticker",progress=False,threads=True)
        for sym in BROAD_UNIVERSE:
            try:
                ticker=sym+".NS"
                df=batch[ticker] if ticker in batch.columns.get_level_values(0) else None
                if df is None or df.empty: continue
                c=df["Close"].dropna()
                if len(c)<2: continue
                p=((c.iloc[-1]-c.iloc[-2])/c.iloc[-2])*100
                if p>0.25: adv+=1
                elif p<-0.25: dec+=1
                else: unch+=1
            except: pass
    except:
        # Fallback to smaller set if batch fails
        for stock in BROAD_UNIVERSE[:40]:
            try:
                t=yf.Ticker(stock+".NS")
                h=t.history(period="3d",interval="1d")
                if len(h)>=2:
                    c=h["Close"]
                    p=((c.iloc[-1]-c.iloc[-2])/c.iloc[-2])*100
                    if p>0.25: adv+=1
                    elif p<-0.25: dec+=1
                    else: unch+=1
            except: pass
    tot=adv+dec+unch
    ratio=round(adv/dec,2) if dec>0 else 5.0
    return {"advances":adv,"declines":dec,"unchanged":unch,
            "total":tot,"ad_ratio":ratio,
            "ad_pct":round((adv/tot)*100) if tot>0 else 50}

@st.cache_data(ttl=300)
def fetch_ohlc():
    try:
        t=yf.Ticker("^NSEI")
        h=t.history(period="6mo",interval="1d")
        return h if not h.empty else None
    except: return None

def calc_score(mkt,secs,ad,ohlc):
    s=0; bd={}; warns=[]
    # VIX (25pts)
    vp=mkt.get("vix",{}).get("price",15); vd=mkt.get("vix",{}).get("pct_1d",0); vs=mkt.get("vix",{}).get("vix_speed",0)
    vpts=12 if vp>24 else 8 if vp>20 else 5 if vp>18 else 2 if vp>16 else 0
    vpts+=8 if vd>10 else 5 if vd>5 else 3 if vd>2 else 0
    vpts+=5 if vs>2 else 2 if vs>1 else 0
    vpts=min(vpts,25); s+=vpts; bd["VIX Level+Speed"]=vpts
    if vd>5: warns.append("VIX spiking +"+str(vd)+"%")
    if vs>2: warns.append("VIX accelerating fast")
    # A/D (20pts)
    ar=ad.get("ad_ratio",1.0)
    apts=20 if ar<0.3 else 15 if ar<0.6 else 8 if ar<1.0 else 3 if ar<1.5 else 0
    s+=apts; bd["Advance-Decline"]=apts
    if ar<0.3: warns.append("A/D DANGER: "+str(ar)+" extreme weakness")
    elif ar<0.6: warns.append("A/D weak: "+str(ar)+" bearish breadth")
    # Sectors (20pts)
    dang=[k for k,v in secs.items() if v.get("status")=="DANGER"]
    weak=[k for k,v in secs.items() if v.get("status") in ["DANGER","WEAK"]]
    spts=min(len(dang)*5,12)+min(len(weak)*2,8); spts=min(spts,20)
    s+=spts; bd["Sector Weakness"]=spts
    if len(dang)>=3: warns.append(str(len(dang))+" sectors in DANGER")
    # Nifty momentum (15pts)
    n1=mkt.get("nifty",{}).get("pct_1d",0); n5=mkt.get("nifty",{}).get("pct_5d",0)
    n5m=mkt.get("nifty",{}).get("mom_5m",0); n15=mkt.get("nifty",{}).get("mom_15m",0)
    mpts=6 if n1<-1.5 else 4 if n1<-0.8 else 2 if n1<-0.3 else 0
    mpts+=5 if n5<-3 else 3 if n5<-1.5 else 1 if n5<-0.5 else 0
    mpts+=2 if n5m<-0.2 else 0; mpts+=2 if n15<-0.3 else 0
    mpts=min(mpts,15); s+=mpts; bd["Nifty Momentum"]=mpts
    if n5m<-0.2: warns.append("Nifty momentum shift in 5min")
    # Bank divergence (10pts)
    b1=mkt.get("banknifty",{}).get("pct_1d",0); div=b1-n1
    bpts=10 if div<-1.5 else 6 if div<-0.8 else 3 if div<-0.3 else 0
    s+=bpts; bd["BankNifty Divergence"]=bpts
    if div<-1.5: warns.append("BankNifty severely weaker — institutional selling")
    # Global (10pts)
    dw=mkt.get("dow",{}).get("pct_1d",0); cr=mkt.get("crude",{}).get("pct_1d",0); fx=mkt.get("usd_inr",{}).get("pct_1d",0)
    gpts=5 if dw<-1.5 else 3 if dw<-0.5 else 0
    gpts+=3 if cr>2 else 0; gpts+=2 if fx>0.5 else 0; gpts=min(gpts,10)
    s+=gpts; bd["Global Cues"]=gpts
    if dw<-1: warns.append("Dow falling "+str(dw)+"%")
    # Technical (10pts)
    tpts=0
    if ohlc is not None and len(ohlc)>=20:
        c=ohlc["Close"]; ma20=c.rolling(20).mean().iloc[-1]; ma50=c.rolling(50).mean().iloc[-1] if len(c)>=50 else ma20; curr=c.iloc[-1]
        d2=c.diff(); g=d2.clip(lower=0).rolling(14).mean(); l=(-d2.clip(upper=0)).rolling(14).mean()
        rsi=(100-(100/(1+g/l))).iloc[-1]
        tpts+=5 if rsi<35 else 3 if rsi<45 else 0
        tpts+=3 if curr<ma50 else 2 if curr<ma20 else 0
        tpts+=2 if ma20<ma50 else 0
        if ma20<ma50: warns.append("Death Cross active")
    tpts=min(tpts,10); s+=tpts; bd["Technical"]=tpts
    return min(s,100), bd, warns

def zone(score):
    if score<=20: return "CALM","#00ff88","Stand aside"
    elif score<=40: return "CAUTION","#ffdd00","Selective hedging only"
    elif score<=60: return "ALERT","#ff8800","Bear positions recommended"
    elif score<=80: return "DANGER","#ff4444","Aggressive put buying"
    else: return "CRASH MODE","#ff0000","Maximum bearish"

def trend(v,s,b):
    if v<-b*2: return "STRONG BEAR","#ff2222"
    elif v<-b: return "BEARISH","#ff6644"
    elif v>b*2: return "STRONG BULL","#00ff66"
    elif v>b: return "BULLISH","#44ff88"
    else: return "NEUTRAL","#ffdd00"

def weakest(secs):
    if not secs: return None,None
    k=min(secs,key=lambda x:secs[x].get("pct_1d",0))
    return k,secs[k]

with st.sidebar:
    st.markdown("<div style='text-align:center;padding:16px 0 8px 0'><div style='font-size:2rem;font-weight:900;color:#ff4444;letter-spacing:4px'>BearIQ</div><div style='font-size:0.6rem;color:#334455;letter-spacing:2px'>EARLY WARNING INTELLIGENCE 3.0</div></div>",unsafe_allow_html=True)
    st.markdown("---")
    page=st.radio("",["Early Warning System",],label_visibility="collapsed")
    st.markdown("---")
    min_conf=st.slider("Min Signal Confidence %",40,85,55)
    auto_ai=st.toggle("Auto AI Analysis",value=True)
    if st.button("REFRESH NOW"): st.cache_data.clear(); st.rerun()
    st.markdown("---")
    now_ts=datetime.now().strftime("%d %b %Y  %I:%M:%S %p")
    st.markdown("<div style='font-size:0.68rem;color:#334455;text-align:center'>"+now_ts+"<br>Auto-refresh: 60s<br>BearIQ 3.0</div>",unsafe_allow_html=True)

api=load_key()
now_str=datetime.now().strftime("%d %b %Y  %I:%M %p")

with st.spinner("Loading live market data..."):
    MKT=fetch_market()
    SECS=fetch_sectors()
    AD=fetch_ad()
    OHLC=fetch_ohlc()

# ── ALL GLOBAL VARS ──────────────────────────────────
SCORE,BREAKDOWN,WARNS=calc_score(MKT,SECS,AD,OHLC)
ZN,ZCLR,ZMSG=zone(SCORE)

NP   = MKT.get("nifty",{}).get("price",24000)
BP   = MKT.get("banknifty",{}).get("price",55000)
FP   = MKT.get("finnifty",{}).get("price",24000)
MP   = MKT.get("midcap",{}).get("price",12000)
VIXP = MKT.get("vix",{}).get("price",15)
VIX1D= MKT.get("vix",{}).get("pct_1d",0)
VSPD = MKT.get("vix",{}).get("vix_speed",0)
N1D  = MKT.get("nifty",{}).get("pct_1d",0)
N5D  = MKT.get("nifty",{}).get("pct_5d",0)
N5M  = MKT.get("nifty",{}).get("mom_5m",0)
N15M = MKT.get("nifty",{}).get("mom_15m",0)
B1D  = MKT.get("banknifty",{}).get("pct_1d",0)
B5M  = MKT.get("banknifty",{}).get("mom_5m",0)
DOW1D= MKT.get("dow",{}).get("pct_1d",0)
CRD  = MKT.get("crude",{}).get("pct_1d",0)

ADV  = AD.get("advances",0)
DEC  = AD.get("declines",0)
UNC  = AD.get("unchanged",0)
ATOT = AD.get("total",1)
RATIO= AD.get("ad_ratio",1.0)
ADPCT= AD.get("ad_pct",50)

DANG_SECS=[k for k,v in SECS.items() if v.get("status")=="DANGER"]
WEAK_SECS=[k for k,v in SECS.items() if v.get("status") in ["DANGER","WEAK"]]
WK,WS=weakest(SECS)

if "lr" not in st.session_state: st.session_state["lr"]=time.time()
elapsed=time.time()-st.session_state["lr"]
if elapsed>60: st.session_state["lr"]=time.time(); st.cache_data.clear(); st.rerun()
secs_left=max(0,int(60-elapsed))

if page=="Early Warning System":
    st.markdown("<div style='font-size:1.6rem;font-weight:800;color:#e0e0e0;border-bottom:1px solid #1a2840;padding-bottom:12px;margin-bottom:20px'>EARLY WARNING SYSTEM <span style='font-size:0.82rem;color:#445566'>"+now_str+" | Refresh in "+str(secs_left)+"s</span></div>",unsafe_allow_html=True)
    c1,c2,c3,c4,c5,c6=st.columns(6)
    for col,nm,lb,ic in zip([c1,c2,c3,c4,c5,c6],["nifty","banknifty","vix","crude","usd_inr","gold"],["NIFTY","BANKNIFTY","VIX","CRUDE","USD/INR","GOLD"],["📊","🏦","😱","🛢","💵","🥇"]):
        with col:
            if nm in MKT:
                p=MKT[nm]["price"]; pc=MKT[nm]["pct_1d"]
                clr="#ff4444" if pc<-0.5 else "#ff8800" if pc<0 else "#00ff88" if pc>0.5 else "#ffdd00"
                st.markdown(card(lb,str(p),clr,("+" if pc>=0 else "")+str(pc)+"%",ic),unsafe_allow_html=True)
    sc1,sc2=st.columns([1,1])
    with sc1:
        fig=go.Figure(go.Indicator(mode="gauge+number",value=SCORE,domain={"x":[0,1],"y":[0,1]},
            gauge={"axis":{"range":[0,100],"tickcolor":"#334455"},"bar":{"color":ZCLR,"thickness":0.3},
                   "bgcolor":"#0d1626","steps":[{"range":[0,20],"color":"#001108"},{"range":[20,40],"color":"#111800"},{"range":[40,60],"color":"#180a00"},{"range":[60,80],"color":"#1a0000"},{"range":[80,100],"color":"#0a0010"}],
                   "threshold":{"line":{"color":ZCLR,"width":5},"thickness":0.8,"value":SCORE}},
            number={"font":{"color":ZCLR,"size":52},"suffix":"/100"}))
        fig.update_layout(paper_bgcolor="#070b14",height=280,margin=dict(l=10,r=10,t=20,b=10))
        st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False},key="gauge_chart")
    with sc2:
        h="<div style='padding:16px'>"
        h+="<div style='font-size:0.7rem;color:#445566;letter-spacing:3px;margin-bottom:6px'>BEARIQ EARLY WARNING ZONE</div>"
        h+="<div style='font-size:3.2rem;font-weight:900;color:"+ZCLR+";margin-bottom:14px'>"+ZN+"</div>"
        h+="<div style='background:#0d1626;border-left:4px solid "+ZCLR+";border-radius:8px;padding:12px;margin-bottom:12px'>"
        h+="<div style='color:#ccddee;font-weight:600;margin-bottom:4px'>"+ZMSG+"</div>"
        h+="<div style='color:#334455;font-size:0.78rem'>A/D: "+str(RATIO)+" | VIX: "+str(VIXP)+" | Warnings: "+str(len(WARNS))+"</div></div>"
        if WARNS:
            h+="<div style='font-size:0.72rem;color:#ff8800;font-weight:700;margin-bottom:6px'>ACTIVE WARNINGS</div>"
            for w in WARNS[:4]: h+="<div style='background:#1a0800;border-left:3px solid #ff6600;border-radius:4px;padding:5px 10px;margin-bottom:4px;color:#ffaa66;font-size:0.8rem'>⚠ "+w+"</div>"
        else: h+="<div style='background:#001a08;border-left:3px solid #00ff66;border-radius:4px;padding:8px 12px;color:#66ff88;font-size:0.85rem'>✅ No active warnings</div>"
        h+="</div>"
        st.markdown(h,unsafe_allow_html=True)
    st.markdown("<div class='section-title'>SCORE BREAKDOWN</div>",unsafe_allow_html=True)
    maxp={"VIX Level+Speed":25,"Advance-Decline":20,"Sector Weakness":20,"Nifty Momentum":15,"BankNifty Divergence":10,"Global Cues":10,"Technical":10}
    labels=list(BREAKDOWN.keys()); values=list(BREAKDOWN.values())
    colors=["#ff2222" if v>=maxp.get(l,10)*0.8 else "#ff8800" if v>=maxp.get(l,10)*0.4 else "#ffdd00" if v>0 else "#1a2840" for l,v in zip(labels,values)]
    fig2=go.Figure(go.Bar(y=labels,x=values,orientation="h",marker_color=colors,text=[str(v)+"/"+str(maxp.get(l,10)) for l,v in zip(labels,values)],textposition="outside",textfont={"color":"#556677","size":11}))
    fig2.update_layout(paper_bgcolor="#070b14",plot_bgcolor="#0d1626",xaxis={"gridcolor":"#1a2840","tickfont":{"color":"#445566"},"range":[0,28]},yaxis={"tickfont":{"color":"#aabbcc"}},height=300,margin=dict(l=10,r=60,t=10,b=10),showlegend=False)
    st.plotly_chart(fig2,use_container_width=True,config={"displayModeBar":False},key="breakdown_chart")
    st.markdown("<div class='section-title'>VIX LIVE MONITOR</div>",unsafe_allow_html=True)
    vl1,vl2,vl3,vl4=st.columns(4)
    with vl1: st.markdown(card("VIX LEVEL",str(VIXP),"#ff4444" if VIXP>20 else "#ff8800" if VIXP>17 else "#00ff88"),unsafe_allow_html=True)
    with vl2: st.markdown(card("VIX 1-DAY",("+" if VIX1D>=0 else "")+str(VIX1D)+"%","#ff4444" if VIX1D>3 else "#ff8800" if VIX1D>1 else "#00ff88"),unsafe_allow_html=True)
    with vl3: st.markdown(card("VIX SPEED",("+" if VSPD>=0 else "")+str(VSPD)+"%/hr","#ff4444" if VSPD>1 else "#ffaa00" if VSPD>0 else "#00ff88","Rate of change"),unsafe_allow_html=True)
    with vl4:
        vs="SPIKE — PUTS NOW" if VIXP>22 and VIX1D>8 else "RISING — CAUTION" if VIXP>18 and VIX1D>2 else "NORMAL"
        vc="#ff3333" if "SPIKE" in vs else "#ff8800" if "RISING" in vs else "#00ff88"
        st.markdown(card("VIX SIGNAL",vs,vc),unsafe_allow_html=True)

elif page=="Sector Intelligence":
    st.markdown("<div style='font-size:1.6rem;font-weight:800;color:#e0e0e0;border-bottom:1px solid #1a2840;padding-bottom:12px;margin-bottom:20px'>SECTOR INTELLIGENCE DASHBOARD <span style='font-size:0.82rem;color:#445566'>"+now_str+"</span></div>",unsafe_allow_html=True)
    sec_cols=st.columns(4)
    for i,(key,sec) in enumerate(SECS.items()):
        with sec_cols[i%4]:
            p1d=sec.get("pct_1d",0); sts=sec.get("status","NEUTRAL")
            sclr="#ff2222" if sts=="DANGER" else "#ff8800" if sts=="WEAK" else "#ffdd00" if sts=="NEUTRAL" else "#00ff88"
            sbg="#1a0000" if sts=="DANGER" else "#1a0800" if sts=="WEAK" else "#0d1626"
            spd=sec.get("detr_speed",0); p5d=sec.get("pct_5d",0)
            h="<div style='background:"+sbg+";border:2px solid "+sclr+"33;border-left:4px solid "+sclr+";border-radius:12px;padding:16px;margin-bottom:10px'>"
            h+="<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:10px'>"
            h+="<div style='font-size:1.5rem'>"+sec.get("icon","")+"</div>"
            h+="<div style='background:#0a0e1a;color:"+sclr+";padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:800'>"+sts+"</div></div>"
            h+="<div style='color:#ccddee;font-weight:800;font-size:1rem;margin-bottom:6px'>"+sec.get("name","")+"</div>"
            h+="<div style='font-size:1.6rem;font-weight:900;color:"+sclr+"'>"+("+" if p1d>=0 else "")+str(p1d)+"%</div>"
            h+="<div style='display:flex;justify-content:space-between;margin-top:8px'>"
            h+="<span style='color:#445566;font-size:0.75rem'>5D: "+("+" if p5d>=0 else "")+str(p5d)+"%</span>"
            sc2="#ff4444" if spd<-0.1 else "#00ff88"
            h+="<span style='color:"+sc2+";font-size:0.75rem'>15m: "+("+" if spd>=0 else "")+str(spd)+"%</span></div></div>"
            st.markdown(h,unsafe_allow_html=True)
    st.markdown("<div class='section-title'>SECTOR PERFORMANCE CHART</div>",unsafe_allow_html=True)
    if SECS:
        sn=[v["icon"]+" "+v["name"] for v in SECS.values()]
        s1d=[v.get("pct_1d",0) for v in SECS.values()]
        s5d=[v.get("pct_5d",0) for v in SECS.values()]
        bc=["#ff2222" if p<-1.5 else "#ff8800" if p<-0.5 else "#ffdd00" if p<0 else "#00ff88" for p in s1d]
        fig3=go.Figure()
        fig3.add_trace(go.Bar(name="Today %",x=sn,y=s1d,marker_color=bc,opacity=0.9))
        fig3.add_trace(go.Bar(name="5-Day %",x=sn,y=s5d,marker_color="#334455",opacity=0.6))
        fig3.add_hline(y=0,line_color="#334455",line_width=1)
        fig3.update_layout(barmode="group",paper_bgcolor="#070b14",plot_bgcolor="#0d1626",xaxis={"tickfont":{"color":"#778899"}},yaxis={"title":"% Change","gridcolor":"#1a2840","tickfont":{"color":"#556677"}},height=320,margin=dict(l=10,r=10,t=10,b=10),legend={"bgcolor":"#0d1626","font":{"color":"#aabbcc"}},hovermode="x unified")
        st.plotly_chart(fig3,use_container_width=True,config={"displayModeBar":False},key="sector_chart")
    st.markdown("<div class='section-title'>AI SECTOR DEEP ANALYSIS</div>",unsafe_allow_html=True)
    if api:
        sec_data=chr(10).join([v["icon"]+" "+v["name"]+": today="+str(v.get("pct_1d",0))+"% 5day="+str(v.get("pct_5d",0))+"% status="+v.get("status","") for v in SECS.values()])
        p_sec=("BearIQ sector intelligence analyst.\n\nLIVE SECTOR DATA:\n"+sec_data+"\nNifty: "+str(NP)+"("+str(N1D)+"%) VIX: "+str(VIXP)+"\n\nGive complete sector analysis (NO trade calls):\n1.WEAKEST SECTOR: Why is it weakest? What is causing this?\n2.SECTORS LIKELY TO FALL MORE: Which 2-3 and why?\n3.SECTORS LIKELY TO RECOVER FIRST: Which 1-2 and why?\n4.SECTOR ROTATION: Is money moving somewhere?\n5.MARKET BREADTH CONCLUSION: What does this sector picture tell us?\n6.KEY LEVELS: Important price levels to watch in weakest sectors")
        with st.spinner("AI analyzing all 8 sectors..."): sec_ai=groq(p_sec,api,900)
        st.markdown("<div class='ai-box'><div style='font-size:0.7rem;color:#3388ff;font-weight:800;letter-spacing:2px;margin-bottom:12px'>BEARIQ AI — COMPLETE SECTOR INTELLIGENCE</div><div style='color:#ccddee;font-size:0.92rem;line-height:1.85'>"+sec_ai.replace("\n","<br>")+"</div></div>",unsafe_allow_html=True)
    else: st.warning("Add Groq API key to config.txt")

elif page=="Advance-Decline Monitor":
    st.markdown("<div style='font-size:1.6rem;font-weight:800;color:#e0e0e0;border-bottom:1px solid #1a2840;padding-bottom:12px;margin-bottom:20px'>ADVANCE-DECLINE MONITOR <span style='font-size:0.82rem;color:#445566'>"+now_str+"</span></div>",unsafe_allow_html=True)
    rclr="#ff0000" if RATIO<0.3 else "#ff4444" if RATIO<0.6 else "#ff8800" if RATIO<1.0 else "#ffdd00" if RATIO<1.5 else "#00ff88"
    rsts="EXTREME DANGER" if RATIO<0.3 else "DANGER" if RATIO<0.6 else "BEARISH" if RATIO<1.0 else "NEUTRAL" if RATIO<1.5 else "BULLISH"
    st.markdown("<div style='background:#0d1626;border:2px solid "+rclr+";border-radius:16px;padding:30px;text-align:center;margin-bottom:20px'><div style='font-size:0.75rem;color:#445566;letter-spacing:3px;margin-bottom:8px'>ADVANCE-DECLINE RATIO</div><div style='font-size:4.5rem;font-weight:900;color:"+rclr+"'>"+str(RATIO)+"</div><div style='font-size:1.3rem;font-weight:800;color:"+rclr+";margin-top:8px'>"+rsts+"</div><div style='color:#445566;margin-top:10px;font-size:0.85rem'>"+str(ADV)+" Advancing | "+str(DEC)+" Declining | "+str(UNC)+" Unchanged</div></div>",unsafe_allow_html=True)
    st.markdown("<div class='section-title'>A/D RATIO LEVELS</div>",unsafe_allow_html=True)
    for rng,sts2,cl2,meaning in [(">2.0","EXTREMELY BULLISH","#00ff88","Almost all stocks rising — very strong"),("1.5-2.0","BULLISH","#44ff88","Majority rising — healthy market"),("1.0-1.5","SLIGHTLY BULLISH","#aaff88","Moderate advances"),("0.6-1.0","BEARISH","#ff8800","More stocks falling — put zone"),("0.3-0.6","DANGER","#ff4444","Significant weakness — buy puts"),("<0.3","EXTREME DANGER","#ff0000","Breadth collapse — maximum bearish")]:
        is_c=(RATIO<0.3 and "<0.3" in rng) or (0.3<=RATIO<0.6 and "0.3" in rng and "0.6" in rng) or (0.6<=RATIO<1.0 and "0.6" in rng and "1.0" in rng) or (1.0<=RATIO<1.5 and "1.0" in rng) or (1.5<=RATIO<2.0 and "1.5" in rng) or (RATIO>=2.0 and ">2.0" in rng)
        bg2="#1a0000" if is_c and RATIO<0.6 else "#0d1626" if is_c else "#070b14"
        h="<div style='background:"+bg2+";border:"+("2px" if is_c else "1px")+" solid "+cl2+"44;border-left:4px solid "+cl2+";border-radius:10px;padding:12px 18px;margin-bottom:8px'>"
        h+="<div style='color:"+cl2+";font-weight:800'>A/D "+rng+" — "+sts2+("  ← YOU ARE HERE" if is_c else "")+"</div>"
        h+="<div style='color:#667788;font-size:0.83rem;margin-top:3px'>"+meaning+"</div></div>"
        st.markdown(h,unsafe_allow_html=True)
    if ATOT>0:
        fig4=go.Figure(go.Bar(x=["Advancing","Declining","Unchanged"],y=[ADV,DEC,UNC],marker_color=["#00ff88","#ff4444","#ffdd00"],text=[str(ADV),str(DEC),str(UNC)],textposition="outside",textfont={"color":"#aabbcc","size":12}))
        fig4.update_layout(paper_bgcolor="#070b14",plot_bgcolor="#0d1626",yaxis={"gridcolor":"#1a2840","tickfont":{"color":"#556677"}},xaxis={"tickfont":{"color":"#aabbcc"}},height=280,margin=dict(l=10,r=10,t=10,b=20),showlegend=False)
        st.plotly_chart(fig4,use_container_width=True,config={"displayModeBar":False},key="ad_chart")
    st.markdown("<div class='section-title'>AI MARKET CONDITION ANALYSIS</div>",unsafe_allow_html=True)
    if api:
        cond="RECOVERING" if RATIO>1.5 and N1D>0.5 else "SLIGHTLY RECOVERING" if RATIO>1.0 and N1D>0 else "EXTREME WEAKNESS" if RATIO<0.3 else "SIGNIFICANT WEAKNESS" if RATIO<0.6 else "MILD WEAKNESS" if RATIO<1.0 else "BALANCED"
        p_ad=("BearIQ market condition analyst.\n\nA/D DATA:\nA/D Ratio: "+str(RATIO)+" ("+rsts+")\nAdvances: "+str(ADV)+" | Declines: "+str(DEC)+" | Condition: "+cond+"\nNifty: "+str(NP)+"(1D:"+str(N1D)+"% 15m:"+str(N15M)+"% 5m:"+str(N5M)+"%)\nBankNifty: "+str(BP)+" | VIX: "+str(VIXP)+"\n\nGive clear market condition assessment:\n1.MARKET CONDITION NOW: Falling, recovering, or sideways? Be very direct.\n2.BREADTH SIGNAL: What does A/D of "+str(RATIO)+" tell us?\n3.WHAT TRADERS SHOULD DO: (recovering=wait/exit puts | falling=hold/add puts | sideways=wait)\n4.NEXT 30 MIN OUTLOOK: What is likely?\n5.KEY TRIGGER TO WATCH: What level changes your view?\n\nIMPORTANT: If recovering say clearly DO NOT buy puts. If falling say clearly consider puts. Simple language, no jargon.")
        with st.spinner("AI analyzing market condition..."): ad_ai=groq(p_ad,api,600)
        bbg="#001a08" if "RECOVERING" in cond else "#1a0000" if "EXTREME" in cond else "#1a0800" if "SIGNIFICANT" in cond else "#0d1626"
        bbrd="#00ff66" if "RECOVERING" in cond else "#ff0000" if "EXTREME" in cond else "#ff6600" if "SIGNIFICANT" in cond else "#ffdd00"
        blbl="MARKET RECOVERING — CAUTION ON PUTS" if "RECOVERING" in cond else "BREADTH COLLAPSE — STRONG BEAR SIGNAL" if "EXTREME" in cond else "MARKET WEAKNESS — BEARISH" if "SIGNIFICANT" in cond else "MARKET MIXED — WAIT"
        st.markdown("<div style='background:"+bbg+";border:2px solid "+bbrd+";border-left:6px solid "+bbrd+";border-radius:14px;padding:20px'><div style='font-size:0.72rem;color:"+bbrd+";font-weight:800;letter-spacing:2px;margin-bottom:10px'>BEARIQ AI — "+blbl+"</div><div style='color:#ccddee;font-size:0.92rem;line-height:1.85'>"+ad_ai.replace("\n","<br>")+"</div></div>",unsafe_allow_html=True)
    else: st.warning("Add Groq API key")

elif page=="Smart Signal Engine":
    st.markdown("<div style='font-size:1.6rem;font-weight:800;color:#e0e0e0;border-bottom:1px solid #1a2840;padding-bottom:12px;margin-bottom:20px'>SMART SIGNAL ENGINE <span style='font-size:0.82rem;color:#445566'>"+now_str+" | Score: "+str(SCORE)+"/100</span></div>",unsafe_allow_html=True)
    km1,km2,km3,km4=st.columns(4)
    with km1: st.markdown(card("BEAR SCORE",str(SCORE)+"/100",ZCLR,ZN,"🎯"),unsafe_allow_html=True)
    with km2: st.markdown(card("A/D RATIO",str(RATIO),"#ff4444" if RATIO<0.6 else "#ff8800" if RATIO<1.0 else "#00ff88",str(ADV)+"↑ "+str(DEC)+"↓","📊"),unsafe_allow_html=True)
    with km3: st.markdown(card("VIX",str(VIXP),"#ff4444" if VIXP>20 else "#ff8800" if VIXP>17 else "#00ff88",("+" if VIX1D>=0 else "")+str(VIX1D)+"%","😱"),unsafe_allow_html=True)
    with km4: st.markdown(card("DANGER SECTORS",str(len(DANG_SECS))+"/8","#ff4444" if len(DANG_SECS)>=4 else "#ff8800" if len(DANG_SECS)>=2 else "#00ff88","in danger zone","🔴"),unsafe_allow_html=True)
    sa,sb=st.columns([1,1])
    with sa: test_mode=st.checkbox("TEST MODE — Simulate signal for demo")
    with sb:
        if st.button("SCAN FOR SIGNALS NOW"): st.cache_data.clear(); st.rerun()
    # Build signals list
    sigs=[]
    bear_tfs=sum(1 for x in [N5M,N15M,N1D,N5D] if x<-0.3)
    if VIXP>22 and VIX1D>8 and SCORE>=45: sigs.append({"setup":"VIX EXPLOSION","inst":"BANKNIFTY","price":BP,"pri":"HIGH","conf":min(55+int(VIX1D*3)+int(SCORE/5),92),"acc":71,"reason":"VIX "+str(VIXP)+" spiked +"+str(VIX1D)+"%"})
    elif VIXP>19 and VIX1D>4 and SCORE>=38: sigs.append({"setup":"VIX RISING","inst":"BANKNIFTY","price":BP,"pri":"HIGH","conf":min(55+int(VIX1D*2)+int(SCORE/5),82),"acc":68,"reason":"VIX rising fast +"+str(VIX1D)+"%"})
    if bear_tfs>=3 and N5M<-0.15: sigs.append({"setup":"MOMENTUM CRASH","inst":"NIFTY","price":NP,"pri":"HIGH","conf":min(60+bear_tfs*5+int(SCORE/4),88),"acc":73,"reason":str(bear_tfs)+"/4 timeframes bearish + 5min momentum negative"})
    if RATIO<0.6 and SCORE>=40: sigs.append({"setup":"BREADTH COLLAPSE","inst":"NIFTY","price":NP,"pri":"HIGH","conf":min(65+int((1-RATIO)*30)+int(SCORE/5),90),"acc":69,"reason":"A/D ratio "+str(RATIO)+" — "+str(DEC)+" stocks declining vs "+str(ADV)+" advancing"})
    if len(DANG_SECS)>=3 and SCORE>=40: sigs.append({"setup":"SECTOR COLLAPSE","inst":"BANKNIFTY","price":BP,"pri":"HIGH","conf":min(58+len(DANG_SECS)*5+int(SCORE/5),85),"acc":67,"reason":str(len(DANG_SECS))+" sectors in danger: "+", ".join(DANG_SECS[:3])})
    if B1D<-0.8 and (B1D-N1D)<-0.5 and SCORE>=38: sigs.append({"setup":"BANK BREAKDOWN","inst":"BANKNIFTY","price":BP,"pri":"HIGH","conf":min(55+int(abs(B1D)*8)+int(SCORE/5),86),"acc":68,"reason":"BankNifty "+str(B1D)+"% vs Nifty "+str(N1D)+"% — institutional selling"})
    if DOW1D<-0.8 and SCORE>=38: sigs.append({"setup":"GLOBAL PANIC","inst":"NIFTY","price":NP,"pri":"HIGH","conf":min(55+int(abs(DOW1D)*8)+int(SCORE/5),84),"acc":72,"reason":"Dow fell "+str(DOW1D)+"% — global risk-off"})
    if N5D<-1.5 and N1D<-0.3 and SCORE>=42: sigs.append({"setup":"SUSTAINED BEAR TREND","inst":"NIFTY","price":NP,"pri":"MEDIUM","conf":min(58+int(abs(N5D)*4)+int(SCORE/5),80),"acc":65,"reason":"Nifty down "+str(N5D)+"% in 5 days — sustained pressure"})
    if WS and WS.get("pct_1d",0)<-1.0 and SCORE>=35: sigs.append({"setup":"SECTOR SHORT: "+(WS.get("name","").upper() if WS else ""),"inst":"NIFTY","price":NP,"pri":"MEDIUM","conf":min(55+int(abs(WS.get("pct_1d",0))*8)+int(SCORE/5),78),"acc":63,"reason":(WS.get("icon","") if WS else "")+" "+(WS.get("name","") if WS else "")+" weakest sector at "+(str(WS.get("pct_1d",0)) if WS else "0")+"%"})
    sigs=[s for s in sigs if s["conf"]>=min_conf]
    sigs.sort(key=lambda x:x["conf"],reverse=True)
    if test_mode and not sigs: sigs=[{"setup":"VIX EXPLOSION [TEST]","inst":"BANKNIFTY","price":BP,"pri":"HIGH","conf":78,"acc":71,"reason":"TEST MODE — Demo signal"}]
    if not sigs:
        st.markdown("<div style='background:#0d1626;border:1px solid #1a2840;border-radius:14px;padding:40px;text-align:center;margin:20px 0'><div style='font-size:2rem;font-weight:900;color:"+ZCLR+";margin-bottom:10px'>"+ZN+"</div><div style='color:#445566'>Score: "+str(SCORE)+"/100 — No signals at "+str(min_conf)+"% confidence<br>Lower slider or enable TEST MODE</div></div>",unsafe_allow_html=True)
    else:
        st.markdown("<div style='background:#1a0000;border:2px solid #ff3333;border-radius:10px;padding:12px 20px;margin-bottom:20px'><div style='color:#ff3333;font-size:0.8rem;font-weight:800;letter-spacing:2px'>"+str(len(sigs))+" SIGNAL(S) DETECTED — "+now_str+"</div></div>",unsafe_allow_html=True)
        for det in sigs:
            conf=det["conf"]; pclr="#ff2222" if det["pri"]=="HIGH" else "#ff8800"; pbg="#120000" if det["pri"]=="HIGH" else "#120800"
            step=100 if det["inst"]=="BANKNIFTY" else 50; lot=30 if det["inst"]=="BANKNIFTY" else 65
            atm=get_atm(det["price"],step)
            is_ft="SHORT" in det["setup"]
            if is_ft: strike=int(det["price"]); entry=int(det["price"]); el=entry; eh=entry; t1=round(det["price"]*0.992); t2=round(det["price"]*0.982); sl=round(det["price"]*1.006); ml=round(abs(sl-entry)*lot); mg=round(abs(t2-entry)*lot)
            else:
                strike=atm-step
                _exp,_days,_explabel=get_expiry_for(det["inst"])
                _vix=get_live_vix_val()
                _vol=get_index_vol("^NSEI" if det["inst"]=="NIFTY" else "^NSEBANK")
                entry=bsm_put(det["price"],strike,_days,_vol,vix=_vix)
                el=round(entry*0.88); eh=round(entry*1.12); t1=round(entry*1.55); t2=round(entry*2.3); sl=round(entry*0.5); ml=sl*lot; mg=t2*lot
            rr=round(mg/ml,1) if ml>0 else 0
            tt="PUT BUY" if not is_ft else "FUTURES SHORT"
            h="<div style='background:"+pbg+";border:2px solid "+pclr+"33;border-left:6px solid "+pclr+";border-radius:14px;padding:22px;margin-bottom:16px'>"
            h+="<div style='display:flex;justify-content:space-between;margin-bottom:14px'><div>"
            h+="<div style='font-size:0.7rem;color:"+pclr+";font-weight:800;letter-spacing:2px'>"+det["pri"]+" PRIORITY — "+str(det["acc"])+"% ACCURACY</div>"
            h+="<div style='font-size:1.5rem;font-weight:900;color:#e0e0e0;margin-top:4px'>"+det["setup"]+"</div>"
            h+="<div style='color:#556677;font-size:0.82rem'>"+now_str+"</div></div>"
            h+="<div style='text-align:right'><div style='font-size:2rem;font-weight:900;color:"+pclr+"'>"+str(conf)+"%</div><div style='color:#445566;font-size:0.65rem'>CONFIDENCE</div>"
            h+="<div style='background:#0a0e1a;color:#4488ff;padding:4px 12px;border-radius:20px;font-weight:800;margin-top:4px;font-size:0.8rem'>"+tt+"</div></div></div>"
            h+="<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px'>"
            for lb,vl,vc in [("Instrument",det["inst"],"#4488ff"),("Strike",str(strike)+" PE" if not is_ft else str(strike),"#ffdd00"),("Expiry",_explabel if not is_ft else "—","#00ddff"),("Lot Size",str(lot),"#cc44ff")]:
                h+="<div style='background:#0a0e1a;border-radius:8px;padding:10px;text-align:center'><div style='color:#445566;font-size:0.68rem'>"+lb+"</div><div style='color:"+vc+";font-weight:800;margin-top:4px'>"+vl+"</div></div>"
            h+="</div><div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px'>"
            for lb,vl,vc in [("Entry Zone","Rs "+str(el)+"-"+str(eh),"#ffdd00"),("Target 1","Rs "+str(t1),"#00ff88"),("Target 2","Rs "+str(t2),"#00ff88"),("Stop Loss","Rs "+str(sl),"#ff4444")]:
                h+="<div style='background:#0a0e1a;border-radius:8px;padding:10px;text-align:center'><div style='color:#445566;font-size:0.68rem'>"+lb+"</div><div style='color:"+vc+";font-weight:700;font-size:0.85rem;margin-top:4px'>"+vl+"</div></div>"
            h+="</div><div style='display:flex;gap:10px;margin-bottom:12px'>"
            h+="<div style='background:#0a0e1a;border-radius:8px;padding:10px;flex:1;text-align:center'><div style='color:#445566;font-size:0.68rem'>MAX LOSS (1 LOT)</div><div style='color:#ff4444;font-weight:800;margin-top:4px'>Rs "+str(f"{int(ml):,}")+"</div></div>"
            h+="<div style='background:#0a0e1a;border-radius:8px;padding:10px;flex:1;text-align:center'><div style='color:#445566;font-size:0.68rem'>MAX GAIN (1 LOT)</div><div style='color:#00ff88;font-weight:800;margin-top:4px'>Rs "+str(f"{int(mg):,}")+"</div></div>"
            h+="<div style='background:#0a0e1a;border-radius:8px;padding:10px;flex:1;text-align:center'><div style='color:#445566;font-size:0.68rem'>RISK:REWARD</div><div style='color:#cc44ff;font-weight:800;margin-top:4px'>1:"+str(rr)+"</div></div></div>"
            h+="<div style='background:#0a0e1a;border-radius:6px;padding:8px 12px;color:#556677;font-size:0.82rem;margin-bottom:10px'>📡 "+det["reason"]+"</div>"
            if api and auto_ai:
                verd=groq("BearIQ analyst. Signal: "+det["setup"]+" on "+det["inst"]+" at "+str(round(det["price"],2))+". Trade: "+tt+" "+str(strike)+". Entry: "+str(entry)+" T1: "+str(t1)+" T2: "+str(t2)+" SL: "+str(sl)+". Score: "+str(SCORE)+"/100. A/D: "+str(RATIO)+". VIX: "+str(VIXP)+". Confirm in exactly 5 lines: VERDICT: / REASON: / CONFIDENCE: / BEST ENTRY: / KEY RISK:",api,400)
                vc2="#00ff88" if "High" in verd else "#ffdd00" if "Medium" in verd else "#ff8800"
                h+="<div style='background:#00081a;border:1px solid #1a4080;border-left:3px solid #3388ff;border-radius:8px;padding:14px'>"
                h+="<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'><div style='font-size:0.7rem;color:#3388ff;font-weight:800'>BEARIQ AI VERDICT</div>"
                conf_lbl="HIGH" if "High" in verd else "LOW" if "Low" in verd or "Avoid" in verd else "MEDIUM"
                h+="<div style='background:#000814;color:"+vc2+";padding:3px 12px;border-radius:20px;font-size:0.73rem;font-weight:800'>"+conf_lbl+" CONFIDENCE</div></div>"
                h+="<div style='color:#ccddee;font-size:0.88rem;line-height:1.75'>"+verd.replace("\n","<br>")+"</div>"
                h+="<div style='color:#334455;font-size:0.72rem;margin-top:10px;border-top:1px solid #1a2840;padding-top:8px'>⚠ BearIQ is AI-powered intelligence. Not SEBI advice. Trade at your own risk.</div></div>"
            h+="</div>"
            st.markdown(h,unsafe_allow_html=True)
            if is_ft: prices2=list(range(int(det["price"]*0.94),int(det["price"]*1.06),50)); pnl2=[(det["price"]-x)*lot for x in prices2]
            else: prices2=list(range(int(strike*0.92),int(strike*1.05),50)); pnl2=[(max(0,strike-x)-entry)*lot for x in prices2]
            figp=go.Figure()
            figp.add_hline(y=0,line_color="#334455",line_width=1,line_dash="dash")
            figp.add_trace(go.Scatter(x=prices2,y=pnl2,mode="lines",line={"color":"#4488ff","width":2.5},fill="tozeroy",fillcolor="rgba(68,136,255,0.08)",name="P&L"))
            figp.add_vline(x=det["price"],line_color="#ffdd00",line_width=2,line_dash="dot",annotation_text="Spot",annotation_font_color="#ffdd00")
            figp.update_layout(paper_bgcolor="#070b14",plot_bgcolor="#0d1626",xaxis={"title":"Expiry Price","gridcolor":"#1a2840","tickfont":{"color":"#445566"}},yaxis={"title":"P&L (Rs)","gridcolor":"#1a2840","tickfont":{"color":"#445566"},"tickformat":",.0f"},height=260,margin=dict(l=10,r=10,t=10,b=20))
            st.plotly_chart(figp,use_container_width=True,config={"displayModeBar":False},key="sig_chart_"+det["setup"]+"_"+str(det["conf"]))

elif page=="Multi-Timeframe Trends":
    st.markdown("<div style='font-size:1.6rem;font-weight:800;color:#e0e0e0;border-bottom:1px solid #1a2840;padding-bottom:12px;margin-bottom:20px'>MULTI-TIMEFRAME TREND ANALYSIS <span style='font-size:0.82rem;color:#445566'>"+now_str+"</span></div>",unsafe_allow_html=True)
    for idx_nm,mk in [("NIFTY 50","nifty"),("BANKNIFTY","banknifty"),("FINNIFTY","finnifty"),("MIDCAP NIFTY","midcap")]:
        if mk not in MKT: continue
        idx=MKT[mk]
        tfs={"5 MIN":(idx.get("mom_5m",0),0.1),"15 MIN":(idx.get("mom_15m",0),0.2),"TODAY":(idx.get("pct_1d",0),0.5),"5 DAY":(idx.get("pct_5d",0),1.0),"1 WEEK":(idx.get("pct_1w",0) if "pct_1w" in idx else idx.get("pct_5d",0)*1.2,1.5),"1 MONTH":(idx.get("pct_1mo",0) if "pct_1mo" in idx else idx.get("pct_5d",0)*2,2.0)}
        st.markdown("<div class='section-title'>"+idx_nm+" TREND MATRIX</div>",unsafe_allow_html=True)
        tf_cols=st.columns(6)
        bear_count=0
        for col,(lb,(pv,th)) in zip(tf_cols,tfs.items()):
            with col:
                tn,tc=trend(pv,None,th)
                if "BEAR" in tn: bear_count+=1
                h="<div style='background:#0d1626;border:1px solid "+tc+"44;border-top:3px solid "+tc+";border-radius:10px;padding:12px;text-align:center;margin-bottom:10px'>"
                h+="<div style='color:#445566;font-size:0.65rem;letter-spacing:2px;margin-bottom:6px'>"+lb+"</div>"
                h+="<div style='color:"+tc+";font-weight:900;font-size:0.88rem;margin-bottom:4px'>"+tn+"</div>"
                h+="<div style='color:"+tc+";font-size:1.1rem;font-weight:800'>"+("+" if pv>=0 else "")+str(round(pv,2))+"%</div></div>"
                st.markdown(h,unsafe_allow_html=True)
        if api and auto_ai:
            tf_summary=" | ".join([lb+":"+("+" if pv>=0 else "")+str(round(pv,2))+"%" for lb,(pv,th) in tfs.items()])
            p_tf=("BearIQ trend analyst.\n"+idx_nm+" trends: "+tf_summary+"\nBearish timeframes: "+str(bear_count)+"/6. Current: "+str(idx["price"])+"\nIn 3 sentences: 1)Overall trend conclusion 2)Best F&O strategy 3)Key level to watch")
            with st.spinner("AI analyzing "+idx_nm+"..."): tf_ai=groq(p_tf,api,300)
            st.markdown("<div style='background:#00081a;border:1px solid #1a4080;border-left:3px solid #3388ff;border-radius:8px;padding:12px 16px;margin-bottom:20px'><div style='font-size:0.68rem;color:#3388ff;font-weight:800;margin-bottom:6px'>AI — "+idx_nm+"</div><div style='color:#ccddee;font-size:0.88rem;line-height:1.7'>"+tf_ai.replace("\n","<br>")+"</div></div>",unsafe_allow_html=True)
        st.markdown("---")

elif page=="AI Market Intelligence":
    st.markdown("<div style='font-size:1.6rem;font-weight:800;color:#e0e0e0;border-bottom:1px solid #1a2840;padding-bottom:12px;margin-bottom:20px'>AI MARKET INTELLIGENCE <span style='font-size:0.82rem;color:#445566'>"+now_str+"</span></div>",unsafe_allow_html=True)
    if not api: st.error("Groq API key not found in config.txt!"); st.stop()
    s1,s2,s3,s4,s5=st.columns(5)
    with s1: st.markdown(card("BEAR SCORE",str(SCORE)+"/100",ZCLR,ZN,"🎯"),unsafe_allow_html=True)
    with s2: st.markdown(card("A/D RATIO",str(RATIO),"#ff4444" if RATIO<0.6 else "#ff8800" if RATIO<1.0 else "#00ff88",str(ADV)+"↑ "+str(DEC)+"↓","📊"),unsafe_allow_html=True)
    with s3: st.markdown(card("VIX",str(VIXP),"#ff4444" if VIXP>20 else "#ffaa00","","😱"),unsafe_allow_html=True)
    with s4: st.markdown(card("WEAK SECTORS",str(len(WEAK_SECS))+"/8","#ff4444" if len(WEAK_SECS)>=5 else "#ff8800" if len(WEAK_SECS)>=3 else "#00ff88","","🔴"),unsafe_allow_html=True)
    with s5: st.markdown(card("WARNINGS",str(len(WARNS)),"#ff4444" if len(WARNS)>=4 else "#ff8800" if len(WARNS)>=2 else "#00ff88","active","⚠️"),unsafe_allow_html=True)
    st.markdown("<div class='section-title'>COMPLETE AI MARKET BRIEFING</div>",unsafe_allow_html=True)
    if st.button("GET FULL AI MARKET BRIEFING"):
        sec_sum=" | ".join([v["icon"]+" "+v["name"]+":"+str(v.get("pct_1d",0))+"%" for v in SECS.values()])
        wk_name=WS.get("icon","")+" "+WS.get("name","") if WS else "N/A"
        p_brief=("BearIQ senior market intelligence AI.\n\nLIVE DATA:\nScore: "+str(SCORE)+"/100 ("+ZN+")\nNifty: "+str(NP)+"("+str(N1D)+"%) BankNifty: "+str(BP)+" FinNifty: "+str(FP)+" Midcap: "+str(MP)+"\nVIX: "+str(VIXP)+"("+str(VIX1D)+"%) VIX Speed: "+str(VSPD)+"%/hr\nA/D: "+str(RATIO)+" ("+str(ADV)+" up, "+str(DEC)+" down)\nSectors: "+sec_sum+"\nWeakest: "+wk_name+"\nDow: "+str(DOW1D)+"% Crude: "+str(CRD)+"%\nWarnings: "+", ".join(WARNS[:5])+"\n\nGive complete professional F&O briefing:\n1.MARKET OVERVIEW (2-3 sentences what is happening)\n2.BEAR SCORE ANALYSIS (why "+str(SCORE)+"/100)\n3.KEY RISK FACTORS (top 3 risks today)\n4.SECTOR ANALYSIS (which to avoid, which to watch)\n5.BEST BEARISH TRADE (exact instrument, strike, entry, target, SL)\n6.CONFIDENCE % for bearish trades today\n7.KEY LEVELS to watch next 2 hours\n8.DISCLAIMER (brief risk warning)")
        with st.spinner("AI generating complete market briefing..."): brief=groq(p_brief,api,1200)
        st.markdown("<div class='ai-box'><div style='font-size:0.72rem;color:#3388ff;font-weight:800;letter-spacing:2px;margin-bottom:12px'>BEARIQ AI COMPLETE MARKET BRIEFING — "+now_str+"</div><div style='color:#ccddee;font-size:0.93rem;line-height:1.85'>"+brief.replace("\n","<br>")+"</div></div>",unsafe_allow_html=True)
    st.markdown("<div class='section-title'>QUICK AI CHECKS</div>",unsafe_allow_html=True)
    q1,q2=st.columns(2)
    with q1:
        if st.button("AI: Should I buy puts NOW?"):
            r=groq("BearIQ. Score:"+str(SCORE)+"/100. VIX:"+str(VIXP)+". A/D:"+str(RATIO)+". Nifty:"+str(NP)+"("+str(N1D)+"%). Should trader buy puts NOW? Answer in 5 lines with exact strike and reason.",api,300)
            st.markdown("<div class='ai-box'><div style='color:#ccddee;font-size:0.9rem;line-height:1.7'>"+r.replace("\n","<br>")+"</div></div>",unsafe_allow_html=True)
    with q2:
        if st.button("AI: Market in next 1 hour?"):
            r=groq("BearIQ. Nifty:"+str(NP)+"("+str(N1D)+"%), VIX:"+str(VIXP)+", A/D:"+str(RATIO)+", Score:"+str(SCORE)+"/100. Predict next 1 hour direction with 3 reasons and probability %.",api,300)
            st.markdown("<div class='ai-box'><div style='color:#ccddee;font-size:0.9rem;line-height:1.7'>"+r.replace("\n","<br>")+"</div></div>",unsafe_allow_html=True)

elif page=="Rule-Based Decision Engine":
    st.markdown("<div style='font-size:1.6rem;font-weight:800;color:#e0e0e0;border-bottom:1px solid #1a2840;padding-bottom:12px;margin-bottom:20px'>RULE-BASED DECISION ENGINE <span style='font-size:0.82rem;color:#445566'>"+now_str+" | Refresh in "+str(secs_left)+"s</span></div>",unsafe_allow_html=True)
    bear_tfs_r=sum(1 for x in [N5M,N15M,N1D,N5D] if x<-0.3)
    div_r=B1D-N1D
    rules=[]
    if VIXP>22 and VIX1D>8: rules.append({"rule":"VIX SPIKE","status":"FIRE","signal":"BUY PUT","inst":"BANKNIFTY","conf":85,"clr":"#ff0000","reason":"VIX "+str(VIXP)+" spiked +"+str(VIX1D)+"%"})
    elif VIXP>19 and VIX1D>4: rules.append({"rule":"VIX RISING","status":"CAUTION","signal":"WATCH","inst":"BANKNIFTY","conf":58,"clr":"#ff8800","reason":"VIX "+str(VIXP)+" rising fast"})
    else: rules.append({"rule":"VIX NORMAL","status":"SAFE","signal":"NO ACTION","inst":"-","conf":0,"clr":"#00ff88","reason":"VIX "+str(VIXP)+" in normal range"})
    if RATIO<0.3: rules.append({"rule":"BREADTH COLLAPSE","status":"FIRE","signal":"BUY PUT","inst":"NIFTY","conf":88,"clr":"#ff0000","reason":"A/D "+str(RATIO)+" — extreme collapse"})
    elif RATIO<0.6: rules.append({"rule":"BREADTH WEAK","status":"FIRE","signal":"BUY PUT","inst":"NIFTY","conf":72,"clr":"#ff4444","reason":"A/D "+str(RATIO)+" — "+str(DEC)+" declining vs "+str(ADV)})
    elif RATIO<1.0: rules.append({"rule":"BREADTH CAUTIOUS","status":"CAUTION","signal":"WATCH","inst":"-","conf":42,"clr":"#ff8800","reason":"A/D "+str(RATIO)+" mild weakness"})
    else: rules.append({"rule":"BREADTH HEALTHY","status":"SAFE","signal":"NO ACTION","inst":"-","conf":0,"clr":"#00ff88","reason":"A/D "+str(RATIO)+" — breadth OK"})
    if bear_tfs_r>=4: rules.append({"rule":"MOMENTUM COLLAPSE","status":"FIRE","signal":"BUY PUT","inst":"NIFTY","conf":82,"clr":"#ff2222","reason":"All 4 timeframes bearish — puts confirmed"})
    elif bear_tfs_r>=3: rules.append({"rule":"MOMENTUM BEARISH","status":"FIRE","signal":"BUY PUT","inst":"NIFTY","conf":68,"clr":"#ff4444","reason":str(bear_tfs_r)+"/4 timeframes bearish"})
    elif bear_tfs_r>=2: rules.append({"rule":"MOMENTUM MIXED","status":"CAUTION","signal":"WATCH","inst":"-","conf":40,"clr":"#ff8800","reason":str(bear_tfs_r)+"/4 timeframes bearish — wait"})
    else: rules.append({"rule":"MOMENTUM NEUTRAL","status":"SAFE","signal":"NO ACTION","inst":"-","conf":0,"clr":"#00ff88","reason":"Momentum not aligned"})
    if len(DANG_SECS)>=5: rules.append({"rule":"SECTOR MELTDOWN","status":"FIRE","signal":"BUY PUT","inst":"NIFTY","conf":84,"clr":"#ff0000","reason":str(len(DANG_SECS))+"/8 sectors in DANGER"})
    elif len(DANG_SECS)>=3: rules.append({"rule":"SECTOR COLLAPSE","status":"FIRE","signal":"BUY PUT","inst":"BANKNIFTY","conf":70,"clr":"#ff4444","reason":str(len(DANG_SECS))+" sectors in danger"})
    elif len(WEAK_SECS)>=5: rules.append({"rule":"SECTOR WEAK","status":"CAUTION","signal":"WATCH","inst":"-","conf":45,"clr":"#ff8800","reason":str(len(WEAK_SECS))+" sectors weak"})
    else: rules.append({"rule":"SECTOR STABLE","status":"SAFE","signal":"NO ACTION","inst":"-","conf":0,"clr":"#00ff88","reason":"Sectors mostly stable"})
    if div_r<-1.5: rules.append({"rule":"BANK BREAKDOWN","status":"FIRE","signal":"SHORT FUTURES","inst":"BANKNIFTY","conf":78,"clr":"#ff2222","reason":"BankNifty "+str(B1D)+"% vs Nifty "+str(N1D)+"%"})
    elif div_r<-0.8: rules.append({"rule":"BANK WEAK","status":"CAUTION","signal":"WATCH","inst":"BANKNIFTY","conf":52,"clr":"#ff8800","reason":"BankNifty lagging by "+str(round(abs(div_r),2))+"%"})
    else: rules.append({"rule":"BANK NORMAL","status":"SAFE","signal":"NO ACTION","inst":"-","conf":0,"clr":"#00ff88","reason":"BankNifty divergence normal"})
    if DOW1D<-1.5 and SCORE>=40: rules.append({"rule":"GLOBAL SHOCK","status":"FIRE","signal":"BUY PUT","inst":"NIFTY","conf":75,"clr":"#ff4444","reason":"Dow "+str(DOW1D)+"%"})
    elif CRD>2.5 and VIXP>18: rules.append({"rule":"CRUDE+VIX THREAT","status":"FIRE","signal":"BUY PUT","inst":"NIFTY","conf":65,"clr":"#ff6600","reason":"Crude +"+str(CRD)+"% + VIX "+str(VIXP)})
    else: rules.append({"rule":"GLOBAL CALM","status":"SAFE","signal":"NO ACTION","inst":"-","conf":0,"clr":"#00ff88","reason":"Global cues calm"})
    if VSPD>2: rules.append({"rule":"VIX ACCELERATING","status":"FIRE","signal":"BUY PUT NOW","inst":"BANKNIFTY","conf":80,"clr":"#ff0000","reason":"VIX rising "+str(VSPD)+"%/hr — panic"})
    elif VSPD>1: rules.append({"rule":"VIX RISING FAST","status":"CAUTION","signal":"PREPARE","inst":"BANKNIFTY","conf":58,"clr":"#ff8800","reason":"VIX speed +"+str(VSPD)+"%/hr"})
    else: rules.append({"rule":"VIX STABLE","status":"SAFE","signal":"NO ACTION","inst":"-","conf":0,"clr":"#00ff88","reason":"VIX not accelerating"})
    fire=[r for r in rules if r["status"]=="FIRE"]
    caution=[r for r in rules if r["status"]=="CAUTION"]
    safe=[r for r in rules if r["status"]=="SAFE"]
    avg_c=round(sum(r["conf"] for r in fire)/len(fire)) if fire else 0
    fc=len(fire)
    if fc>=5: md="STRONG PUT BUY"; mc="#ff0000"; mb="#1a0000"; mm="Multiple critical rules firing. High probability bear setup. Enter puts now."
    elif fc>=3: md="BUY PUTS"; mc="#ff4444"; mb="#140000"; mm="Several rules firing. Good put opportunity. Use proper SL."
    elif fc>=1: md="CAUTIOUS ENTRY"; mc="#ff8800"; mb="#140800"; mm="Some rules firing. Enter small size, wait for more confirmation."
    elif len(caution)>=3: md="WATCH — WAIT"; mc="#ffdd00"; mb="#141000"; mm="Caution signals but no clear fire. Wait and watch."
    else: md="STAND ASIDE"; mc="#00ff88"; mb="#001408"; mm="No bear rules firing. Market calm. Avoid puts."
    st.markdown("<div style='background:"+mb+";border:3px solid "+mc+";border-radius:16px;padding:30px;text-align:center;margin-bottom:24px'>"
        +"<div style='font-size:0.72rem;color:#445566;letter-spacing:3px;margin-bottom:8px'>BEARIQ RULE ENGINE — MASTER DECISION</div>"
        +"<div style='font-size:2.8rem;font-weight:900;color:"+mc+";margin:10px 0'>"+md+"</div>"
        +"<div style='color:#aabbcc;font-size:0.95rem;margin-top:8px'>"+mm+"</div>"
        +"<div style='display:flex;justify-content:center;gap:30px;margin-top:16px'>"
        +"<div><div style='font-size:2rem;font-weight:900;color:#ff4444'>"+str(fc)+"</div><div style='color:#445566;font-size:0.72rem'>RULES FIRING</div></div>"
        +"<div><div style='font-size:2rem;font-weight:900;color:#ffdd00'>"+str(len(caution))+"</div><div style='color:#445566;font-size:0.72rem'>CAUTION</div></div>"
        +"<div><div style='font-size:2rem;font-weight:900;color:#00ff88'>"+str(len(safe))+"</div><div style='color:#445566;font-size:0.72rem'>SAFE</div></div>"
        +"<div><div style='font-size:2rem;font-weight:900;color:"+mc+"'>"+str(avg_c)+"%</div><div style='color:#445566;font-size:0.72rem'>AVG CONFIDENCE</div></div>"
        +"</div></div>",unsafe_allow_html=True)
    if fire:
        best=max(fire,key=lambda r:r["conf"])
        bi=best["inst"]; bpr=BP if bi=="BANKNIFTY" else NP; bst=100 if bi=="BANKNIFTY" else 50; bl=30 if bi=="BANKNIFTY" else 65
        batm=get_atm(bpr,bst); isft="SHORT" in best["signal"]
        if isft: bstk=int(bpr); ben=int(bpr); bt1=round(bpr*0.992); bt2=round(bpr*0.982); bsl=round(bpr*1.006); bml=round(abs(bsl-ben)*bl); bmg=round(abs(bt2-ben)*bl)
        else: bstk=batm-bst; ben=round(bpr*0.004); bt1=round(ben*1.55); bt2=round(ben*2.3); bsl=round(ben*0.5); bml=bsl*bl; bmg=bt2*bl
        brr=round(bmg/bml,1) if bml>0 else 0
        btt="PUT BUY" if not isft else "FUTURES SHORT"
        st.markdown("<div class='section-title'>BEST TRADE FROM DECISION ENGINE</div>",unsafe_allow_html=True)
        th="<div style='background:#0d0020;border:2px solid #aa44ff;border-left:6px solid #aa44ff;border-radius:14px;padding:22px;margin-bottom:16px'>"
        th+="<div style='font-size:0.72rem;color:#aa44ff;font-weight:800;letter-spacing:2px;margin-bottom:8px'>RULE ENGINE TRADE — "+best["rule"]+" ("+str(best["conf"])+"% CONFIDENCE)</div>"
        th+="<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px'>"
        for lb,vl,vc in [("Instrument",bi,"#4488ff"),("Strike",str(bstk)+" PE" if not isft else str(bstk),"#ffdd00"),("Trade",btt,"#cc44ff"),("Confidence",str(best["conf"])+"%","#ff4444")]:
            th+="<div style='background:#0a0e1a;border-radius:8px;padding:10px;text-align:center'><div style='color:#445566;font-size:0.68rem'>"+lb+"</div><div style='color:"+vc+";font-weight:800;margin-top:4px'>"+vl+"</div></div>"
        th+="</div><div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px'>"
        for lb,vl,vc in [("Entry","Rs "+str(ben),"#ffdd00"),("Target 1","Rs "+str(bt1),"#00ff88"),("Target 2","Rs "+str(bt2),"#00ff88"),("Stop Loss","Rs "+str(bsl),"#ff4444")]:
            th+="<div style='background:#0a0e1a;border-radius:8px;padding:10px;text-align:center'><div style='color:#445566;font-size:0.68rem'>"+lb+"</div><div style='color:"+vc+";font-weight:700;margin-top:4px'>"+vl+"</div></div>"
        th+="</div><div style='display:flex;gap:10px;margin-bottom:12px'>"
        th+="<div style='background:#0a0e1a;border-radius:8px;padding:10px;flex:1;text-align:center'><div style='color:#445566;font-size:0.68rem'>MAX LOSS</div><div style='color:#ff4444;font-weight:800;margin-top:4px'>Rs "+str(f"{int(bml):,}")+"</div></div>"
        th+="<div style='background:#0a0e1a;border-radius:8px;padding:10px;flex:1;text-align:center'><div style='color:#445566;font-size:0.68rem'>MAX GAIN</div><div style='color:#00ff88;font-weight:800;margin-top:4px'>Rs "+str(f"{int(bmg):,}")+"</div></div>"
        th+="<div style='background:#0a0e1a;border-radius:8px;padding:10px;flex:1;text-align:center'><div style='color:#445566;font-size:0.68rem'>RISK:REWARD</div><div style='color:#cc44ff;font-weight:800;margin-top:4px'>1:"+str(brr)+"</div></div></div>"
        if api:
            rns=", ".join([r["rule"] for r in fire])
            rap=groq("BearIQ rule engine. Firing: "+rns+". Trade: "+btt+" "+bi+" "+str(bstk)+". Entry:"+str(ben)+" T1:"+str(bt1)+" T2:"+str(bt2)+" SL:"+str(bsl)+". Score:"+str(SCORE)+"/100 A/D:"+str(RATIO)+" VIX:"+str(VIXP)+". Confirm in 4 lines: VERDICT: / BEST ENTRY TIMING: / KEY RISK: / OVERALL:",api,300)
            th+="<div style='background:#00081a;border:1px solid #1a4080;border-left:3px solid #3388ff;border-radius:8px;padding:14px;margin-top:8px'>"
            th+="<div style='font-size:0.7rem;color:#3388ff;font-weight:800;margin-bottom:6px'>AI CONFIRMATION</div>"
            th+="<div style='color:#ccddee;font-size:0.88rem;line-height:1.7'>"+rap.replace("\n","<br>")+"</div></div>"
        th+="</div>"
        st.markdown(th,unsafe_allow_html=True)
    st.markdown("<div class='section-title'>ALL 7 RULES STATUS</div>",unsafe_allow_html=True)
    hdr="<div style='display:grid;grid-template-columns:2fr 1fr 1.5fr 1.5fr 2.5fr;gap:6px;padding:8px 14px;background:#070b14;border-radius:8px;margin-bottom:6px'>"
    for c3 in ["RULE","STATUS","SIGNAL","INSTRUMENT","REASON"]: hdr+="<span style='color:#334455;font-size:0.68rem;text-transform:uppercase;font-weight:700'>"+c3+"</span>"
    hdr+="</div>"
    st.markdown(hdr,unsafe_allow_html=True)
    for r in rules:
        rc=r["clr"]; rbg="#1a0000" if r["status"]=="FIRE" else "#1a0a00" if r["status"]=="CAUTION" else "#001208"
        row="<div style='display:grid;grid-template-columns:2fr 1fr 1.5fr 1.5fr 2.5fr;gap:6px;padding:10px 14px;background:"+rbg+";border-bottom:1px solid #1a2840;border-left:3px solid "+rc+";border-radius:4px;margin-bottom:4px;align-items:center'>"
        row+="<span style='color:#ccddee;font-weight:700;font-size:0.85rem'>"+r["rule"]+"</span>"
        row+="<span style='color:"+rc+";font-weight:800;font-size:0.82rem'>"+r["status"]+"</span>"
        row+="<span style='color:"+rc+";font-size:0.82rem;font-weight:600'>"+r["signal"]+"</span>"
        row+="<span style='color:#4488ff;font-size:0.82rem'>"+r["inst"]+"</span>"
        row+="<span style='color:#556677;font-size:0.78rem'>"+r["reason"][:60]+"</span>"
        row+="</div>"
        st.markdown(row,unsafe_allow_html=True)
    st.markdown("<div style='background:#0d1626;border:1px solid #1a2840;border-radius:8px;padding:12px;margin-top:16px;color:#334455;font-size:0.75rem'>⚠ Rule-based signals are decision support tools only. Not SEBI registered advice. Always use proper risk management.</div>",unsafe_allow_html=True)