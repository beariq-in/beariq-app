import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
import pandas as pd
import numpy as np
import requests, os
from datetime import datetime, timedelta

st.set_page_config(page_title="BearIQ — India Fear-Greed Index",page_icon="B",layout="wide",initial_sidebar_state="expanded")
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

# ── BROAD UNIVERSE FOR BREADTH + HIGHS/LOWS ─────────────────────────────
BROAD_100 = [
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","SBIN",
    "BHARTIARTL","ITC","KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI",
    "SUNPHARMA","TITAN","BAJFINANCE","ULTRACEMCO","WIPRO","ONGC","NTPC",
    "TATAMOTORS","ADANIENT","HCLTECH","POWERGRID","M&M","NESTLEIND",
    "TATASTEEL","TECHM","COALINDIA","DRREDDY","DIVISLAB","BAJAJFINSV",
    "CIPLA","BRITANNIA","BPCL","EICHERMOT","GRASIM","HINDALCO",
    "INDUSINDBK","JSWSTEEL","APOLLOHOSP","ADANIPORTS","SBILIFE",
    "TATACONSUM","LTIM","BAJAJ-AUTO","HEROMOTOCO","HDFCLIFE","SHRIRAMFIN",
    "VEDL","SIEMENS","DLF","GODREJCP","MARICO","DABUR","NAUKRI",
    "HAVELLS","MUTHOOTFIN","OFSS","LUPIN","TORNTPHARM","AUROPHARMA",
    "BANDHANBNK","FEDERALBNK","BIOCON","BALKRISIND","COLPAL","PERSISTENT",
    "TVSMOTOR","CHOLAFIN","TRENT","ZOMATO","IRCTC","MPHASIS","COFORGE",
    "LTTS","KPITTECH","TATAELXSI","DIXON","KAYNES","ZYDUSLIFE","ALKEM",
    "CANBK","BANKINDIA","UNIONBANK","PNB","IDFCFIRSTB","RECLTD","PFC",
    "NHPC","SJVN","TATAPOWER","ADANIGREEN","ASHOKLEY","APOLLOTYRE",
    "GODREJPROP","OBEROIRLTY","PRESTIGE","PHOENIXLTD","BANKBARODA",
]

def load_key():
    for p in [os.path.join(os.path.expanduser("~"),"Desktop","BearIQ","config.txt"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)),"config.txt"),"config.txt"]:
        if os.path.exists(p):
            k=open(p).read().strip()
            if k: return k
    return None

def groq(prompt,key,n=800):
    if not key: return "API key not found."
    try:
        r=requests.post(GROQ_URL,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},
            json={"model":GROQ_MODEL,"messages":[{"role":"user","content":prompt}],"temperature":0.5,"max_tokens":n},timeout=25)
        return r.json()["choices"][0]["message"]["content"] if r.status_code==200 else "Error: "+str(r.status_code)
    except Exception as e: return "Error: "+str(e)

def card(lbl,val,clr,sub="",icon=""):
    return ("<div class='card'><div style='font-size:0.68rem;color:#445566;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px'>"+icon+" "+lbl+"</div>"
        +"<div style='font-size:1.9rem;font-weight:900;color:"+clr+";margin:4px 0'>"+str(val)+"</div>"
        +(("<div style='font-size:0.75rem;color:#445566;margin-top:4px'>"+sub+"</div>") if sub else "")+"</div>")

def score_to_100(val, low, high, invert=False):
    """Normalize any value to 0-100 scale"""
    if high==low: return 50
    score=((val-low)/(high-low))*100
    score=max(0,min(100,score))
    return round(100-score if invert else score, 1)

# ── COMPONENT FETCHERS ───────────────────────────────────────────────────

@st.cache_data(ttl=60)
def comp1_nifty_momentum():
    """Component 1: Nifty vs 125-day MA"""
    try:
        t=yf.Ticker("^NSEI")
        # Use 2y to ensure enough data for 125-day MA
        h=t.history(period="2y",interval="1d")
        if h.empty: return 50,"N/A",0
        c=h["Close"].dropna()
        if len(c)<130: return 50,"N/A",0
        curr=float(c.iloc[-1])
        ma125=float(c.rolling(125).mean().iloc[-1])
        if ma125==0 or pd.isna(ma125): return 50,round(curr,0),0
        pct_diff=round(((curr-ma125)/ma125)*100,2)
        # Range: -5% below MA = extreme fear (0), +5% above = extreme greed (100)
        score=score_to_100(pct_diff,-10,10)
        return score,round(curr,0),pct_diff
    except Exception as e:
        return 50,"N/A",0

@st.cache_data(ttl=300)
def comp2_highs_lows():
    """Component 2: 52-week Highs vs Lows ratio"""
    try:
        tickers=[s+".NS" for s in BROAD_100[:60]]
        batch=yf.download(tickers,period="260d",interval="1d",group_by="ticker",progress=False,threads=True)
        highs=0; lows=0; total=0
        for sym in BROAD_100[:60]:
            try:
                ticker=sym+".NS"
                df=batch[ticker] if ticker in batch.columns.get_level_values(0) else None
                if df is None or df.empty: continue
                c=df["Close"].dropna()
                if len(c)<20: continue
                curr=c.iloc[-1]
                h52=c.max(); l52=c.min()
                # within 2% of 52W high = new high
                if curr>=(h52*0.98): highs+=1
                # within 2% of 52W low = new low
                if curr<=(l52*1.02): lows+=1
                total+=1
            except: pass
        if total==0: return 50,0,0,0
        # More highs = greed, more lows = fear
        net=highs-lows
        # Net range roughly -60 to +60
        score=score_to_100(net,-30,30)
        return score,highs,lows,total
    except: return 50,0,0,0

@st.cache_data(ttl=60)
def comp3_breadth():
    """Component 3: Advance-Decline Ratio"""
    try:
        tickers=[s+".NS" for s in BROAD_100]
        batch=yf.download(tickers,period="3d",interval="1d",group_by="ticker",progress=False,threads=True)
        adv=0; dec=0
        for sym in BROAD_100:
            try:
                ticker=sym+".NS"
                df=batch[ticker] if ticker in batch.columns.get_level_values(0) else None
                if df is None or df.empty: continue
                c=df["Close"].dropna()
                if len(c)<2: continue
                pct=((c.iloc[-1]-c.iloc[-2])/c.iloc[-2])*100
                if pct>0.25: adv+=1
                elif pct<-0.25: dec+=1
            except: pass
        total=adv+dec
        if total==0: return 50,0,0
        ad_ratio=adv/dec if dec>0 else 5.0
        # A/D ratio 0.2=extreme fear, 3.0=extreme greed
        score=score_to_100(ad_ratio,0.2,3.0)
        return score,adv,dec
    except: return 50,0,0

@st.cache_data(ttl=300)
def comp4_vix():
    """Component 4: VIX Level vs 20-day average + Trend"""
    try:
        t=yf.Ticker("^INDIAVIX")
        h=t.history(period="60d",interval="1d")
        h5=t.history(period="1d",interval="5m")
        if h.empty: return 50,15,15,0
        curr=h5["Close"].iloc[-1] if not h5.empty else h["Close"].iloc[-1]
        ma20=h["Close"].rolling(20).mean().iloc[-1]
        pct_above=((curr-ma20)/ma20)*100
        # VIX 30% above 20MA = extreme fear, 30% below = extreme greed
        score=score_to_100(pct_above,-30,30,invert=True)
        return score,round(curr,2),round(ma20,2),round(pct_above,1)
    except: return 50,15,15,0

@st.cache_data(ttl=300)
def comp5_safe_haven():
    """Component 5: Gold vs Nifty 20-day performance"""
    try:
        gold=yf.Ticker("GC=F").history(period="30d",interval="1d")
        nifty=yf.Ticker("^NSEI").history(period="30d",interval="1d")
        if gold.empty or nifty.empty or len(gold)<20 or len(nifty)<20:
            return 50,0,0,0
        gold_ret=((gold["Close"].iloc[-1]-gold["Close"].iloc[-20])/gold["Close"].iloc[-20])*100
        nifty_ret=((nifty["Close"].iloc[-1]-nifty["Close"].iloc[-20])/nifty["Close"].iloc[-20])*100
        # Gold outperforming = fear
        # When gold_ret - nifty_ret is very positive = fear
        # When very negative = greed
        diff=gold_ret-nifty_ret
        # Range -10 to +10
        score=score_to_100(diff,-8,8,invert=True)
        return score,round(gold_ret,2),round(nifty_ret,2),round(diff,2)
    except: return 50,0,0,0

@st.cache_data(ttl=300)
def comp6_rupee():
    """Component 6: Rupee Strength (India-specific innovation!)"""
    try:
        t=yf.Ticker("USDINR=X")
        h=t.history(period="60d",interval="1d")
        h5=t.history(period="1d",interval="5m")
        if h.empty: return 50,84,84,0
        curr=h5["Close"].iloc[-1] if not h5.empty else h["Close"].iloc[-1]
        ma20=h["Close"].rolling(20).mean().iloc[-1]
        pct_above=((curr-ma20)/ma20)*100
        # USD/INR 2% above 20MA = rupee very weak = extreme fear
        # USD/INR 2% below 20MA = rupee strong = extreme greed
        score=score_to_100(pct_above,-2,2,invert=True)
        return score,round(curr,2),round(ma20,2),round(pct_above,2)
    except: return 50,84,84,0

@st.cache_data(ttl=300)
def comp7_crude_fear():
    """Component 7: Crude Oil Fear Factor"""
    try:
        crude=yf.Ticker("CL=F").history(period="30d",interval="1d")
        nifty=yf.Ticker("^NSEI").history(period="30d",interval="1d")
        if crude.empty or nifty.empty: return 50,0,0
        crude_pct=((crude["Close"].iloc[-1]-crude["Close"].iloc[-5])/crude["Close"].iloc[-5])*100
        nifty_pct=((nifty["Close"].iloc[-1]-nifty["Close"].iloc[-5])/nifty["Close"].iloc[-5])*100
        crude_price=round(crude["Close"].iloc[-1],2)
        # Rising crude + falling nifty = stagflation fear = extreme fear
        # Rising crude alone = mild fear
        # Falling crude + rising nifty = greed
        combo=crude_pct-nifty_pct
        score=score_to_100(combo,-8,8,invert=True)
        return score,crude_price,round(crude_pct,2)
    except: return 50,0,0

# ── HISTORICAL TREND ─────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_fg_trend():
    """Approximate 5-day historical trend using Nifty + VIX proxy"""
    try:
        nifty=yf.Ticker("^NSEI").history(period="15d",interval="1d")
        vix=yf.Ticker("^INDIAVIX").history(period="15d",interval="1d")
        gold=yf.Ticker("GC=F").history(period="15d",interval="1d")
        usd=yf.Ticker("USDINR=X").history(period="15d",interval="1d")
        if any(x.empty for x in [nifty,vix,gold,usd]): return []
        # Get common dates
        dates=nifty.index[-7:]
        trend=[]
        for i,dt in enumerate(dates):
            if i<1: continue
            try:
                # Simplified proxy score for historical
                n_idx=list(nifty.index).index(dt)
                v_idx=list(vix.index).index(dt) if dt in vix.index else -1
                nifty_pct=((nifty["Close"].iloc[n_idx]-nifty["Close"].iloc[n_idx-1])/nifty["Close"].iloc[n_idx-1])*100
                vix_val=vix["Close"].iloc[v_idx] if v_idx>=0 else 15
                # Simple proxy
                proxy_score=50+(nifty_pct*5)-(max(0,vix_val-15)*2)
                proxy_score=max(0,min(100,proxy_score))
                trend.append({"date":dt.strftime("%d %b"),"score":round(proxy_score,1)})
            except: pass
        return trend[-5:] if len(trend)>=2 else []
    except: return []

# ── SCORE TO LABEL ────────────────────────────────────────────────────────
def score_label(score):
    if score<=20:   return "EXTREME FEAR","#ff0000","#1a0000"
    elif score<=35: return "FEAR","#ff4444","#140000"
    elif score<=50: return "MILD FEAR","#ff8800","#140800"
    elif score<=60: return "NEUTRAL","#ffdd00","#141000"
    elif score<=75: return "MILD GREED","#88ff00","#0a1400"
    elif score<=90: return "GREED","#00ff44","#001a08"
    else:           return "EXTREME GREED","#00ff88","#001a10"

def put_signal(score):
    if score<=20:   return "CAUTION — Book profits on puts. Bounce likely near!","#ffdd00"
    elif score<=35: return "HOLD puts. Market fearful but may continue.","#ff8800"
    elif score<=50: return "WATCH — Mild fear. Follow Bear Score for confirmation.","#ff8800"
    elif score<=60: return "STAND ASIDE — Neutral market. Wait for fear.","#ffdd00"
    elif score<=75: return "PREPARE — Greed building. Start watching for put entry.","#ff4444"
    elif score<=90: return "BUY PUTS — Market greedy. Smart money exiting quietly.","#ff2222"
    else:           return "STRONG PUT SIGNAL — Extreme greed = crash risk HIGH!","#ff0000"

# ── SIDEBAR ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div style='text-align:center;padding:14px 0 8px'><div style='font-size:2rem;font-weight:900;color:#ff4444;letter-spacing:4px'>BearIQ</div><div style='font-size:0.6rem;color:#334455;letter-spacing:2px'>INDIA FEAR-GREED INDEX</div></div>",unsafe_allow_html=True)
    st.markdown("---")
    auto_ai=st.toggle("AI Interpretation",value=True)
    show_detail=st.toggle("Show Component Details",value=True)
    if st.button("REFRESH NOW"): st.cache_data.clear(); st.rerun()
    st.markdown("---")
    st.markdown("""<div style='background:#0d1626;border:1px solid #1a2840;border-radius:10px;padding:14px;font-size:0.75rem;color:#445566'>
    <div style='color:#3388cc;font-weight:800;margin-bottom:8px'>7 COMPONENTS</div>
    1. Nifty Momentum<br>
    2. 52W Highs vs Lows<br>
    3. Advance-Decline<br>
    4. India VIX<br>
    5. Gold vs Nifty<br>
    6. Rupee Strength ⭐<br>
    7. Crude Oil Fear ⭐<br>
    <div style='margin-top:8px;color:#223344'>⭐ India-specific innovation</div>
    </div>""",unsafe_allow_html=True)
    st.markdown("---")
    ts=datetime.now().strftime("%d %b %Y  %I:%M %p")
    st.markdown(f"<div style='font-size:0.65rem;color:#334455;text-align:center'>{ts}<br>All data via yFinance (Free)<br>India's first F&O Fear-Greed</div>",unsafe_allow_html=True)

api=load_key()
now_str=datetime.now().strftime("%d %b %Y  %I:%M %p")

st.markdown(f"<div style='font-size:1.6rem;font-weight:800;color:#e0e0e0;border-bottom:1px solid #1a2840;padding-bottom:12px;margin-bottom:20px'>INDIA F&O FEAR-GREED INDEX <span style='font-size:0.82rem;color:#445566'>{now_str}</span></div>",unsafe_allow_html=True)

# ── FETCH ALL 7 COMPONENTS ────────────────────────────────────────────────
prog=st.progress(0)
status=st.empty()

status.markdown("<div style='color:#334455;font-size:0.8rem'>Fetching Nifty momentum...</div>",unsafe_allow_html=True)
s1,nifty_curr,nifty_ma_diff=comp1_nifty_momentum()
prog.progress(14)

status.markdown("<div style='color:#334455;font-size:0.8rem'>Fetching 52-week highs vs lows (60 stocks)...</div>",unsafe_allow_html=True)
s2,highs,lows,total_scanned=comp2_highs_lows()
prog.progress(28)

status.markdown("<div style='color:#334455;font-size:0.8rem'>Fetching advance-decline breadth (100+ stocks)...</div>",unsafe_allow_html=True)
s3,adv,dec=comp3_breadth()
prog.progress(42)

status.markdown("<div style='color:#334455;font-size:0.8rem'>Fetching India VIX...</div>",unsafe_allow_html=True)
s4,vix_curr,vix_ma,vix_pct_above=comp4_vix()
prog.progress(56)

status.markdown("<div style='color:#334455;font-size:0.8rem'>Fetching Gold vs Nifty...</div>",unsafe_allow_html=True)
s5,gold_ret,nifty_ret_20d,gold_nifty_diff=comp5_safe_haven()
prog.progress(70)

status.markdown("<div style='color:#334455;font-size:0.8rem'>Fetching Rupee strength...</div>",unsafe_allow_html=True)
s6,usdinr,usdinr_ma,usdinr_pct=comp6_rupee()
prog.progress(84)

status.markdown("<div style='color:#334455;font-size:0.8rem'>Fetching Crude Oil fear factor...</div>",unsafe_allow_html=True)
s7,crude_price,crude_pct=comp7_crude_fear()
prog.progress(100)

prog.empty(); status.empty()

# ── FINAL SCORE ────────────────────────────────────────────────────────────
final_score=round((s1+s2+s3+s4+s5+s6+s7)/7,1)
label,fg_color,fg_bg=score_label(final_score)
put_msg,put_clr=put_signal(final_score)

# ── MAIN GAUGE ────────────────────────────────────────────────────────────
g1,g2=st.columns([1,1])
with g1:
    # Semicircle gauge
    gauge_fig=go.Figure(go.Indicator(
        mode="gauge+number",
        value=final_score,
        domain={"x":[0,1],"y":[0,1]},
        gauge={
            "axis":{"range":[0,100],"tickcolor":"#445566","tickfont":{"color":"#445566"}},
            "bar":{"color":fg_color,"thickness":0.28},
            "bgcolor":"#0d1626",
            "bordercolor":"#1a2840",
            "steps":[
                {"range":[0,20],"color":"#1a0000"},
                {"range":[20,35],"color":"#140000"},
                {"range":[35,50],"color":"#141000"},
                {"range":[50,65],"color":"#141400"},
                {"range":[65,80],"color":"#0a1400"},
                {"range":[80,100],"color":"#001a08"},
            ],
            "threshold":{"line":{"color":fg_color,"width":5},"thickness":0.8,"value":final_score}
        },
        number={"font":{"color":fg_color,"size":64},"suffix":""}
    ))
    gauge_fig.update_layout(
        paper_bgcolor="#070b14",height=320,
        margin=dict(l=20,r=20,t=30,b=10),
        annotations=[
            {"text":"0<br>EXTREME<br>FEAR","x":0.02,"y":0.1,"showarrow":False,"font":{"color":"#ff2222","size":9},"align":"center"},
            {"text":"50<br>NEUTRAL","x":0.5,"y":-0.05,"showarrow":False,"font":{"color":"#ffdd00","size":9},"align":"center"},
            {"text":"100<br>EXTREME<br>GREED","x":0.98,"y":0.1,"showarrow":False,"font":{"color":"#00ff88","size":9},"align":"center"},
        ]
    )
    st.plotly_chart(gauge_fig,use_container_width=True,config={"displayModeBar":False},key="fg_gauge")

with g2:
    st.markdown(f"""
    <div style='padding:20px'>
        <div style='font-size:0.72rem;color:#445566;letter-spacing:3px;margin-bottom:8px'>INDIA F&O FEAR-GREED</div>
        <div style='font-size:3rem;font-weight:900;color:{fg_color};margin-bottom:4px'>{label}</div>
        <div style='font-size:4rem;font-weight:900;color:{fg_color};margin-bottom:16px'>{final_score}/100</div>
        <div style='background:{fg_bg};border:2px solid {fg_color}44;border-left:5px solid {fg_color};border-radius:10px;padding:14px;margin-bottom:16px'>
            <div style='font-size:0.7rem;color:{fg_color};font-weight:800;letter-spacing:2px;margin-bottom:6px'>PUT TRADING SIGNAL</div>
            <div style='color:#ccddee;font-size:0.92rem;line-height:1.5'>{put_msg}</div>
        </div>
        <div style='display:grid;grid-template-columns:repeat(2,1fr);gap:8px'>
            <div style='background:#0d1626;border-radius:8px;padding:10px;text-align:center'>
                <div style='color:#445566;font-size:0.65rem'>COMPONENTS</div>
                <div style='color:#4488ff;font-weight:800;font-size:1.1rem'>7 Active</div>
            </div>
            <div style='background:#0d1626;border-radius:8px;padding:10px;text-align:center'>
                <div style='color:#445566;font-size:0.65rem'>STOCKS SCANNED</div>
                <div style='color:#4488ff;font-weight:800;font-size:1.1rem'>{total_scanned}+</div>
            </div>
        </div>
    </div>""",unsafe_allow_html=True)

# ── 7 COMPONENT CARDS ─────────────────────────────────────────────────────
st.markdown("<div class='section-title'>7 COMPONENTS — INDIA FEAR-GREED BREAKDOWN</div>",unsafe_allow_html=True)

components=[
    {"name":"NIFTY MOMENTUM","score":s1,"icon":"📈",
     "detail":f"Nifty {('above' if nifty_ma_diff>=0 else 'below')} 125-day MA by {abs(nifty_ma_diff)}%",
     "what":"Nifty vs 125-day moving average"},
    {"name":"52W HIGHS vs LOWS","score":s2,"icon":"📊",
     "detail":f"{highs} stocks near 52W high vs {lows} near 52W low (of {total_scanned} scanned)",
     "what":"New highs vs new lows ratio"},
    {"name":"ADVANCE-DECLINE","score":s3,"icon":"⬆️",
     "detail":f"{adv} advancing vs {dec} declining today (A/D: {round(adv/dec,2) if dec>0 else '5.0+'})",
     "what":"Market breadth — 100+ stocks"},
    {"name":"INDIA VIX","score":s4,"icon":"😱",
     "detail":f"VIX {vix_curr} vs 20-day avg {vix_ma} ({('+' if vix_pct_above>=0 else '')}{vix_pct_above}%)",
     "what":"Fear gauge vs its own average"},
    {"name":"GOLD vs NIFTY","score":s5,"icon":"🥇",
     "detail":f"Gold 20D: {('+' if gold_ret>=0 else '')}{gold_ret}% vs Nifty 20D: {('+' if nifty_ret_20d>=0 else '')}{nifty_ret_20d}%",
     "what":"Safe haven demand indicator"},
    {"name":"RUPEE STRENGTH ⭐","score":s6,"icon":"💵",
     "detail":f"USD/INR {usdinr} vs 20-day avg {usdinr_ma} ({('+' if usdinr_pct>=0 else '')}{usdinr_pct}%)",
     "what":"India-specific innovation — rupee as fear gauge"},
    {"name":"CRUDE OIL FEAR ⭐","score":s7,"icon":"🛢️",
     "detail":f"Crude ${crude_price} | 5-day change: {('+' if crude_pct>=0 else '')}{crude_pct}%",
     "what":"India-specific — stagflation fear detector"},
]

cols=st.columns(4)
for i,comp in enumerate(components[:4]):
    with cols[i]:
        sc=comp["score"]
        if sc<=35:      clr="#ff4444"; bg="#1a0000"
        elif sc<=50:    clr="#ff8800"; bg="#140800"
        elif sc<=65:    clr="#ffdd00"; bg="#141000"
        else:           clr="#00ff88"; bg="#001a08"
        bar_width=round(sc)
        h=f"<div style='background:{bg};border:1px solid {clr}33;border-left:4px solid {clr};border-radius:12px;padding:14px;height:100%'>"
        h+=f"<div style='font-size:1.2rem;margin-bottom:6px'>{comp['icon']}</div>"
        h+=f"<div style='color:#aabbcc;font-size:0.72rem;font-weight:700;margin-bottom:8px'>{comp['name']}</div>"
        h+=f"<div style='font-size:2rem;font-weight:900;color:{clr};margin-bottom:6px'>{sc}</div>"
        h+=f"<div style='background:#0a0e1a;border-radius:3px;height:5px;margin-bottom:8px'><div style='background:{clr};width:{bar_width}%;height:5px;border-radius:3px'></div></div>"
        if show_detail:
            h+=f"<div style='color:#445566;font-size:0.7rem;line-height:1.5'>{comp['detail']}</div>"
        h+="</div>"
        st.markdown(h,unsafe_allow_html=True)

cols2=st.columns(3)
for i,comp in enumerate(components[4:]):
    with cols2[i]:
        sc=comp["score"]
        if sc<=35:      clr="#ff4444"; bg="#1a0000"
        elif sc<=50:    clr="#ff8800"; bg="#140800"
        elif sc<=65:    clr="#ffdd00"; bg="#141000"
        else:           clr="#00ff88"; bg="#001a08"
        bar_width=round(sc)
        h=f"<div style='background:{bg};border:1px solid {clr}33;border-left:4px solid {clr};border-radius:12px;padding:14px;height:100%'>"
        h+=f"<div style='font-size:1.2rem;margin-bottom:6px'>{comp['icon']}</div>"
        h+=f"<div style='color:#aabbcc;font-size:0.72rem;font-weight:700;margin-bottom:8px'>{comp['name']}</div>"
        h+=f"<div style='font-size:2rem;font-weight:900;color:{clr};margin-bottom:6px'>{sc}</div>"
        h+=f"<div style='background:#0a0e1a;border-radius:3px;height:5px;margin-bottom:8px'><div style='background:{clr};width:{bar_width}%;height:5px;border-radius:3px'></div></div>"
        if show_detail:
            h+=f"<div style='color:#445566;font-size:0.7rem;line-height:1.5'>{comp['detail']}</div>"
        h+="</div>"
        st.markdown(h,unsafe_allow_html=True)

# ── COMPONENT RADAR CHART ─────────────────────────────────────────────────
st.markdown("<div class='section-title'>COMPONENT RADAR — FEAR vs GREED BALANCE</div>",unsafe_allow_html=True)
labels=[c["name"].replace(" ⭐","") for c in components]
values=[c["score"] for c in components]
values_closed=values+[values[0]]
labels_closed=labels+[labels[0]]

radar=go.Figure()
radar.add_trace(go.Scatterpolar(
    r=values_closed,theta=labels_closed,fill="toself",
    fillcolor=f"rgba({','.join(['255,68,68' if final_score<50 else '0,255,136'])},0.15)",
    line={"color":fg_color,"width":2},name="Fear-Greed"
))
radar.add_trace(go.Scatterpolar(
    r=[50]*len(labels_closed),theta=labels_closed,
    line={"color":"#334455","width":1,"dash":"dash"},
    name="Neutral (50)"
))
radar.update_layout(
    polar={"radialaxis":{"range":[0,100],"tickfont":{"color":"#445566"},"gridcolor":"#1a2840"},
           "angularaxis":{"tickfont":{"color":"#aabbcc"},"gridcolor":"#1a2840"},
           "bgcolor":"#0d1626"},
    paper_bgcolor="#070b14",height=380,
    legend={"font":{"color":"#aabbcc"},"bgcolor":"#0d1626"},
    margin=dict(l=60,r=60,t=30,b=30)
)
st.plotly_chart(radar,use_container_width=True,config={"displayModeBar":False},key="radar_chart")

# ── HISTORICAL TREND ──────────────────────────────────────────────────────
st.markdown("<div class='section-title'>FEAR-GREED TREND (5-DAY PROXY)</div>",unsafe_allow_html=True)
trend=get_fg_trend()
if trend:
    trend_dates=[t["date"] for t in trend]
    trend_scores=[t["score"] for t in trend]
    trend_scores.append(final_score)
    trend_dates.append("Today")
    colors=[fg_color if s==final_score else ("#ff4444" if s<50 else "#00ff88") for s in trend_scores]
    tf=go.Figure()
    tf.add_hline(y=50,line_color="#334455",line_width=1,line_dash="dash",annotation_text="Neutral",annotation_font_color="#445566")
    tf.add_hline(y=25,line_color="rgba(255,34,34,0.13)",line_width=1,line_dash="dot",annotation_text="Fear Zone",annotation_font_color="#ff4444")
    tf.add_hline(y=75,line_color="rgba(0,255,136,0.13)",line_width=1,line_dash="dot",annotation_text="Greed Zone",annotation_font_color="#00ff88")
    tf.add_trace(go.Scatter(x=trend_dates,y=trend_scores,mode="lines+markers+text",
        line={"color":fg_color,"width":3},marker={"color":colors,"size":12},
        text=[str(s) for s in trend_scores],textposition="top center",
        textfont={"color":"#ccddee","size":11}))
    tf.update_layout(paper_bgcolor="#070b14",plot_bgcolor="#0d1626",
        xaxis={"tickfont":{"color":"#aabbcc"},"gridcolor":"#1a2840"},
        yaxis={"range":[0,100],"tickfont":{"color":"#556677"},"gridcolor":"#1a2840"},
        height=260,margin=dict(l=10,r=10,t=20,b=20),showlegend=False)
    st.plotly_chart(tf,use_container_width=True,config={"displayModeBar":False},key="trend_chart")
else:
    st.info("Historical trend available after market data loads fully.")

# ── PUT STRATEGY GUIDE ────────────────────────────────────────────────────
st.markdown("<div class='section-title'>HOW TO USE FEAR-GREED FOR PUT TRADING</div>",unsafe_allow_html=True)
guide_data=[
    ("0-20","EXTREME FEAR","#ff0000","Caution — avoid new puts. Market panicking. Look for put profit booking."),
    ("21-35","FEAR","#ff4444","Hold existing puts. Watch for stabilization before new entry."),
    ("36-50","MILD FEAR","#ff8800","Neutral-bearish. Combine with Bear Score for confirmation."),
    ("51-65","NEUTRAL","#ffdd00","Stand aside. Market balanced. Wait for greed to develop."),
    ("66-75","MILD GREED","#88ff00","Watch carefully. Greed building. Prepare put positions."),
    ("76-90","GREED","#00ff44","Good put entry zone! Market overconfident. Smart money selling."),
    ("91-100","EXTREME GREED","#00ff88","BEST PUT ENTRY! Crash risk very high. Market at peak overconfidence."),
]
for zone,name,clr,desc in guide_data:
    active=" border:2px solid "+clr+";" if zone.split("-")[0]<=str(int(final_score))<=zone.split("-")[1] else " border:1px solid #1a2840;"
    active_badge="<span style='background:"+clr+";color:#000;padding:2px 8px;border-radius:20px;font-size:0.65rem;font-weight:800;margin-left:8px'>CURRENT</span>" if zone.split("-")[0]<=str(int(final_score))<=zone.split("-")[1] else ""
    h=f"<div style='display:grid;grid-template-columns:0.6fr 1.2fr 3fr;gap:12px;align-items:center;background:#0d1626;{active}border-radius:8px;padding:10px 16px;margin-bottom:6px'>"
    h+=f"<div style='color:{clr};font-weight:800;font-size:1rem'>{zone}</div>"
    h+=f"<div style='color:{clr};font-weight:700;font-size:0.85rem'>{name}{active_badge}</div>"
    h+=f"<div style='color:#556677;font-size:0.82rem'>{desc}</div></div>"
    st.markdown(h,unsafe_allow_html=True)

# ── AI INTERPRETATION ─────────────────────────────────────────────────────
if api and auto_ai:
    st.markdown("<div class='section-title'>AI FEAR-GREED INTERPRETATION</div>",unsafe_allow_html=True)
    comp_summary="\n".join([f"- {c['name']}: {c['score']}/100 — {c['detail']}" for c in components])
    p=(f"BearIQ India Fear-Greed Index analyst.\n\n"
       f"INDIA FEAR-GREED SCORE: {final_score}/100 — {label}\n\n"
       f"7 COMPONENTS:\n{comp_summary}\n\n"
       f"Market data:\n"
       f"- Nifty: {nifty_curr}\n"
       f"- VIX: {vix_curr} ({('+' if vix_pct_above>=0 else '')}{vix_pct_above}% vs 20MA)\n"
       f"- USD/INR: {usdinr}\n"
       f"- Crude: ${crude_price}\n"
       f"- A/D Ratio: {round(adv/dec,2) if dec>0 else '5+'}\n\n"
       f"Give F&O trader interpretation:\n"
       f"1. FEAR-GREED READING: What {final_score}/100 means for market right now\n"
       f"2. KEY DRIVER: Which component is most significant and why\n"
       f"3. DIVERGENCE: Any component diverging from the overall score?\n"
       f"4. PUT STRATEGY: Exactly what put trader should do now\n"
       f"5. WATCH FOR: What change in this index would trigger action\n"
       f"6. CONFIDENCE: Overall confidence in current reading (%)\n\n"
       f"Be direct. Use exact numbers. For F&O traders only.")
    with st.spinner("AI analyzing India Fear-Greed Index..."): ai_r=groq(p,api,700)
    st.markdown(f"<div class='ai-box'><div style='font-size:0.7rem;color:#3388ff;font-weight:800;margin-bottom:12px'>BEARIQ AI — FEAR-GREED INTERPRETATION</div><div style='color:#ccddee;font-size:0.92rem;line-height:1.85'>{ai_r.replace(chr(10),'<br>')}</div></div>",unsafe_allow_html=True)

st.markdown("<div style='background:#0d1626;border:1px solid #1a2840;border-radius:8px;padding:10px 14px;color:#334455;font-size:0.72rem;margin-top:10px'>⚠ India's first F&O Fear-Greed Index by BearIQ. All data via yFinance (free). For research purposes only. Not SEBI registered advice. Fear-Greed is a sentiment indicator — combine with Bear Score for best results.</div>",unsafe_allow_html=True)
