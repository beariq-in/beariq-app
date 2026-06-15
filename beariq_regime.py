import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
import pandas as pd
import numpy as np
import requests, os, json
from datetime import datetime, timedelta

st.set_page_config(page_title="BearIQ — Market Regime Engine",page_icon="B",layout="wide",initial_sidebar_state="expanded")
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
REGIME_STATE_FILE=os.path.join(os.path.expanduser("~"),"Desktop","BearIQ","regime_state.json")

# ── REGIME DEFINITIONS ────────────────────────────────────────────────────
REGIMES={
    "PANIC":          {"icon":"🔴","color":"#ff0000","bg":"#1a0000","desc":"Extreme fear — rapid selling across market"},
    "EUPHORIC":       {"icon":"🟢","color":"#00ff88","bg":"#001a08","desc":"Extreme greed — market dangerously overconfident"},
    "COMPRESSION":    {"icon":"⚡","color":"#aa44ff","bg":"#0d0020","desc":"Volatility squeeze — explosive move imminent"},
    "TRENDING BEAR":  {"icon":"🐻","color":"#ff4444","bg":"#140000","desc":"Strong downtrend — puts working well"},
    "TRENDING BULL":  {"icon":"🐂","color":"#44ff88","bg":"#001400","desc":"Strong uptrend — avoid puts"},
    "VOLATILE RANGE": {"icon":"🌊","color":"#ff8800","bg":"#1a0800","desc":"High volatility — no clear direction"},
    "CHOPPY":         {"icon":"〰️","color":"#ffdd00","bg":"#141000","desc":"Random movement — theta killing puts"},
    "TRANSITIONAL":   {"icon":"⚖️","color":"#4488ff","bg":"#00081a","desc":"Mixed signals — wait for clarity"},
}

PUT_SIGNALS={
    "PANIC":          {"action":"BOOK PROFITS","clr":"#ffdd00","detail":"Puts already profitable — consider booking. Bounce likely near panic extremes."},
    "EUPHORIC":       {"action":"STRONG PUT ENTRY","clr":"#ff0000","detail":"Market overconfident. Best regime to build put positions. Smart money selling."},
    "COMPRESSION":    {"action":"PREPARE — WAIT","clr":"#aa44ff","detail":"Explosive move coming. Check Bear Score direction. Enter puts if Bear Score > 60."},
    "TRENDING BEAR":  {"action":"HOLD PUTS","clr":"#ff4444","detail":"Trend is your friend. Hold puts, trail stop loss. Add on bounces."},
    "TRENDING BULL":  {"action":"AVOID PUTS","clr":"#44ff88","detail":"Trend against puts. Wait for regime change. Only hedge if Bear Score > 75."},
    "VOLATILE RANGE": {"action":"QUICK TRADES ONLY","clr":"#ff8800","detail":"Tight stop loss. Don't hold overnight. Range trades only."},
    "CHOPPY":         {"action":"AVOID — WAIT","clr":"#ffdd00","detail":"Theta eating premium. Wait for clear regime. Stand aside."},
    "TRANSITIONAL":   {"action":"SMALL SIZE ONLY","clr":"#4488ff","detail":"Mixed signals. Small position if any. Wait for confirmation."},
}

def load_key():
    for p in [os.path.join(os.path.expanduser("~"),"Desktop","BearIQ","config.txt"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)),"config.txt"),"config.txt"]:
        if os.path.exists(p):
            k=open(p).read().strip()
            if k: return k
    return None

def groq(prompt,key,n=700):
    if not key: return "API key not found."
    try:
        r=requests.post(GROQ_URL,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},
            json={"model":GROQ_MODEL,"messages":[{"role":"user","content":prompt}],"temperature":0.4,"max_tokens":n},timeout=25)
        return r.json()["choices"][0]["message"]["content"] if r.status_code==200 else "Error"
    except: return "Error"

def card(lbl,val,clr,sub="",icon=""):
    return ("<div class='card'><div style='font-size:0.68rem;color:#445566;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px'>"+icon+" "+lbl+"</div>"
        +"<div style='font-size:1.9rem;font-weight:900;color:"+clr+";margin:4px 0'>"+str(val)+"</div>"
        +(("<div style='font-size:0.75rem;color:#445566;margin-top:4px'>"+sub+"</div>") if sub else "")+"</div>")

# ── MARKET DATA ENGINE ────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def fetch_market_data():
    """Fetch all required data for regime detection"""
    data={}
    try:
        # Nifty daily (60 days for MA calculations)
        nd=yf.Ticker("^NSEI")
        nifty_d=nd.history(period="60d",interval="1d")
        nifty_5m=nd.history(period="1d",interval="5m")

        if not nifty_d.empty:
            data["nifty_close"]=nifty_d["Close"]
            data["nifty_high"]=nifty_d["High"]
            data["nifty_low"]=nifty_d["Low"]
            data["nifty_open"]=nifty_d["Open"]
            data["nifty_curr"]=round(float(nifty_5m["Close"].iloc[-1]) if not nifty_5m.empty else float(nifty_d["Close"].iloc[-1]),2)
            data["nifty_open_today"]=round(float(nifty_5m["Open"].iloc[0]) if not nifty_5m.empty else float(nifty_d["Open"].iloc[-1]),2)
            data["nifty_high_today"]=round(float(nifty_5m["High"].max()) if not nifty_5m.empty else float(nifty_d["High"].iloc[-1]),2)
            data["nifty_low_today"]=round(float(nifty_5m["Low"].min()) if not nifty_5m.empty else float(nifty_d["Low"].iloc[-1]),2)
            data["nifty_prev_close"]=round(float(nifty_d["Close"].iloc[-2]) if len(nifty_d)>1 else float(nifty_d["Close"].iloc[-1]),2)

        # BankNifty
        bn=yf.Ticker("^NSEBANK")
        bank_d=bn.history(period="30d",interval="1d")
        bank_5m=bn.history(period="1d",interval="5m")
        if not bank_d.empty:
            data["bank_curr"]=round(float(bank_5m["Close"].iloc[-1]) if not bank_5m.empty else float(bank_d["Close"].iloc[-1]),2)
            data["bank_prev"]=round(float(bank_d["Close"].iloc[-2]) if len(bank_d)>1 else float(bank_d["Close"].iloc[-1]),2)

        # VIX
        vt=yf.Ticker("^INDIAVIX")
        vix_d=vt.history(period="30d",interval="1d")
        vix_5m=vt.history(period="1d",interval="5m")
        if not vix_d.empty:
            data["vix_curr"]=round(float(vix_5m["Close"].iloc[-1]) if not vix_5m.empty else float(vix_d["Close"].iloc[-1]),2)
            data["vix_prev"]=round(float(vix_d["Close"].iloc[-2]) if len(vix_d)>1 else float(vix_d["Close"].iloc[-1]),2)
            data["vix_ma20"]=round(float(vix_d["Close"].rolling(20).mean().iloc[-1]),2) if len(vix_d)>=20 else data["vix_curr"]
            data["vix_series"]=vix_d["Close"]

    except Exception as e:
        pass
    return data

# ── INDICATOR CALCULATIONS ────────────────────────────────────────────────
def calc_efficiency_ratio(close_series, period=10):
    """
    Kaufman Efficiency Ratio
    1.0 = perfect trend, 0.0 = pure chop
    """
    try:
        c=close_series.dropna()
        if len(c)<period+1: return 0.5
        net_move=abs(float(c.iloc[-1])-float(c.iloc[-period-1]))
        path=sum(abs(float(c.iloc[i])-float(c.iloc[i-1])) for i in range(-period,0))
        return round(net_move/path,3) if path>0 else 0.5
    except: return 0.5

def calc_atr(high,low,close,period=14):
    """Average True Range"""
    try:
        tr=pd.DataFrame({
            'hl':high-low,
            'hc':(high-close.shift(1)).abs(),
            'lc':(low-close.shift(1)).abs()
        }).max(axis=1)
        return float(tr.ewm(span=period).mean().iloc[-1])
    except: return 0

def calc_bb_width(close,period=20):
    """
    Bollinger Band Width normalized
    <0.85 = compression forming
    <0.70 = strong squeeze
    """
    try:
        c=close.dropna()
        if len(c)<period+20: return 1.0
        ma=c.rolling(period).mean()
        std=c.rolling(period).std()
        width=(ma+2*std-ma+2*std)/(ma)*100  # simplified: 4*std/ma
        width_series=(4*std/ma)*100
        current=float(width_series.iloc[-1])
        avg_width=float(width_series.rolling(20).mean().iloc[-1])
        return round(current/avg_width,3) if avg_width>0 else 1.0
    except: return 1.0

def calc_ma(close,period):
    try:
        c=close.dropna()
        if len(c)<period: return float(c.iloc[-1])
        return round(float(c.rolling(period).mean().iloc[-1]),2)
    except: return 0

def calc_atr_declining(vix_series,periods=5):
    """Check if VIX (volatility proxy) is declining"""
    try:
        v=vix_series.dropna()
        if len(v)<periods: return False
        return float(v.iloc[-1])<float(v.iloc[-periods])
    except: return False

def calc_intraday_er(open_p,high_p,low_p,close_p):
    """
    Intraday Efficiency Ratio
    |Close-Open| / (High-Low)
    """
    try:
        rng=high_p-low_p
        if rng==0: return 0.5
        return round(abs(close_p-open_p)/rng,3)
    except: return 0.5

# ── BROAD A/D (fast proxy) ────────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_ad_ratio():
    """Fast A/D from 30 core NSE stocks"""
    stocks=["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","SBIN","WIPRO",
            "AXISBANK","LT","BAJFINANCE","MARUTI","TATAMOTORS","SUNPHARMA",
            "ONGC","NTPC","POWERGRID","TATASTEEL","HCLTECH","DIVISLAB",
            "CIPLA","BHARTIARTL","TITAN","TECHM","COALINDIA","HINDALCO",
            "M&M","NESTLEIND","KOTAKBANK","INDUSINDBK","JSWSTEEL"]
    adv=0;dec=0
    try:
        tickers=[s+".NS" for s in stocks]
        batch=yf.download(tickers,period="3d",interval="1d",group_by="ticker",progress=False,threads=True)
        for sym in stocks:
            try:
                df=batch[sym+".NS"] if sym+".NS" in batch.columns.get_level_values(0) else None
                if df is None or df.empty: continue
                c=df["Close"].dropna()
                if len(c)<2: continue
                p=((c.iloc[-1]-c.iloc[-2])/c.iloc[-2])*100
                if p>0.25: adv+=1
                elif p<-0.25: dec+=1
            except: pass
    except: pass
    return round(adv/dec,2) if dec>0 else (5.0 if adv>0 else 1.0),adv,dec

# ── SCORE CALCULATORS ─────────────────────────────────────────────────────
def calc_panic_score(vix_curr,vix_prev,ad_ratio,nifty_pct_intraday):
    """0-100 panic score"""
    # VIX spike component (35%)
    vix_chg=((vix_curr-vix_prev)/vix_prev)*100 if vix_prev>0 else 0
    vix_spike=min(100,max(0,(vix_chg-2)/18*100)) if vix_chg>2 else 0

    # A/D collapse (30%)
    ad_score=max(0,min(100,(1-ad_ratio)/0.8*100)) if ad_ratio<1 else 0

    # Nifty fall intraday (25%)
    nf=abs(min(0,nifty_pct_intraday))
    nifty_score=min(100,max(0,(nf-0.5)/2.5*100))

    # VIX absolute level (10%)
    vix_lvl=min(100,max(0,(vix_curr-15)/15*100))

    return round(vix_spike*0.35+ad_score*0.30+nifty_score*0.25+vix_lvl*0.10,1)

def calc_euphoria_score(fg_score,ad_ratio,vix_curr,nifty_above_ma20_pct):
    """0-100 euphoria score"""
    # Fear-Greed (35%)
    fg=max(0,min(100,(fg_score-60)/40*100)) if fg_score>60 else 0

    # A/D strength (25%)
    ad=min(100,max(0,(ad_ratio-1.5)/1.5*100)) if ad_ratio>1.5 else 0

    # VIX low (25%)
    vix_s=max(0,min(100,(17-vix_curr)/6*100)) if vix_curr<17 else 0

    # Price above MA20 (15%)
    ma_s=min(100,max(0,(nifty_above_ma20_pct-1)/4*100)) if nifty_above_ma20_pct>1 else 0

    return round(fg*0.35+ad*0.25+vix_s*0.25+ma_s*0.15,1)

def calc_all_regime_scores(er,atr_pct,bb_width_ratio,panic_score,euphoria_score,
                            nifty_curr,ma20,ma50,ad_ratio,intraday_er,vix_curr):
    """Calculate score 0-100 for each regime"""
    scores={}

    # PANIC
    scores["PANIC"]=panic_score

    # EUPHORIC
    scores["EUPHORIC"]=euphoria_score

    # COMPRESSION: BB narrow + ATR declining + low VIX change
    bb_score=max(0,min(100,(1-bb_width_ratio)/0.3*100)) if bb_width_ratio<1.0 else 0
    scores["COMPRESSION"]=round(bb_score*0.6+(max(0,min(100,(20-vix_curr)/10*100))*0.4),1)

    # TRENDING BEAR: ER high + price below MAs + AD weak
    if nifty_curr<ma20 and ma20<ma50:
        trend_strength=min(100,er*130)
        ad_confirm=max(0,min(100,(1-ad_ratio)/0.8*100)) if ad_ratio<1 else 0
        scores["TRENDING BEAR"]=round(trend_strength*0.6+ad_confirm*0.4,1)
    else:
        scores["TRENDING BEAR"]=max(0,min(50,er*60)) if nifty_curr<ma20 else 0

    # TRENDING BULL: ER high + price above MAs + AD strong
    if nifty_curr>ma20 and ma20>ma50:
        trend_strength=min(100,er*130)
        ad_confirm=min(100,max(0,(ad_ratio-1)/2*100)) if ad_ratio>1 else 0
        scores["TRENDING BULL"]=round(trend_strength*0.6+ad_confirm*0.4,1)
    else:
        scores["TRENDING BULL"]=max(0,min(50,er*60)) if nifty_curr>ma20 else 0

    # VOLATILE RANGE: high ATR + low ER
    atr_score=min(100,max(0,(atr_pct-0.8)/1.7*100))
    chop_score=max(0,min(100,(0.50-er)/0.50*100)) if er<0.50 else 0
    scores["VOLATILE RANGE"]=round(atr_score*0.55+chop_score*0.45,1)

    # CHOPPY: very low ER + moderate everything else
    choppy_er=max(0,min(100,(0.35-er)/0.35*100)) if er<0.35 else 0
    scores["CHOPPY"]=round(choppy_er*0.7+(max(0,min(100,(1-intraday_er)/0.7*100))*0.3),1)

    # TRANSITIONAL: catch-all when nothing dominates
    max_others=max(scores.get("PANIC",0),scores.get("EUPHORIC",0),
                   scores.get("COMPRESSION",0),scores.get("TRENDING BEAR",0),
                   scores.get("TRENDING BULL",0),scores.get("VOLATILE RANGE",0),
                   scores.get("CHOPPY",0))
    scores["TRANSITIONAL"]=max(0,60-max_others*0.6)

    return scores

# ── SIGNAL STABILITY ENGINE ───────────────────────────────────────────────
def load_regime_state():
    try:
        if os.path.exists(REGIME_STATE_FILE):
            with open(REGIME_STATE_FILE,"r") as f: return json.load(f)
    except: pass
    return {"current_regime":"TRANSITIONAL","candidate":"TRANSITIONAL","count":0,"last_updated":""}

def save_regime_state(state):
    try:
        with open(REGIME_STATE_FILE,"w") as f: json.dump(state,f)
    except: pass

def apply_stability(scores,state):
    """
    Anti-whipsaw logic:
    Regime must score highest 2 consecutive times
    New regime needs > 60% confidence
    Exit threshold is 15% lower than entry
    """
    dominant=max(scores,key=scores.get)
    dominant_score=scores[dominant]
    current=state.get("current_regime","TRANSITIONAL")
    candidate=state.get("candidate","TRANSITIONAL")
    count=state.get("count",0)

    # Sort all regimes by score
    sorted_regimes=sorted(scores.items(),key=lambda x:x[1],reverse=True)
    primary=sorted_regimes[0]
    secondary=sorted_regimes[1] if len(sorted_regimes)>1 else ("TRANSITIONAL",30)

    # Check if new dominant emerges
    if dominant!=current and dominant_score>62:
        if dominant==candidate:
            count+=1
            if count>=2:
                # Confirmed regime change
                current=dominant
                count=0
        else:
            candidate=dominant
            count=1
    elif dominant==current:
        count=0
        candidate=current

    # Hysteresis: only exit current if score drops below (entry-15)
    curr_score=scores.get(current,0)
    if curr_score<45 and dominant!=current and dominant_score>62:
        current=dominant
        count=0

    state={"current_regime":current,"candidate":candidate,"count":count,
           "last_updated":datetime.now().strftime("%H:%M:%S")}
    save_regime_state(state)
    confidence=min(round(scores.get(current,50),1),98)
    secondary_regime=secondary[0] if secondary[1]>40 and secondary[0]!=current else None
    secondary_score=round(secondary[1],1) if secondary_regime else 0
    return current,confidence,secondary_regime,secondary_score,state

# ── SIDEBAR ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div style='text-align:center;padding:14px 0 8px'><div style='font-size:2rem;font-weight:900;color:#ff4444;letter-spacing:4px'>BearIQ</div><div style='font-size:0.6rem;color:#334455;letter-spacing:2px'>MARKET REGIME ENGINE</div></div>",unsafe_allow_html=True)
    st.markdown("---")
    auto_ai=st.toggle("AI Interpretation",value=True)
    show_scores=st.toggle("Show All Regime Scores",value=True)
    show_indicators=st.toggle("Show Raw Indicators",value=True)
    fg_manual=st.number_input("Fear-Greed Score (from localhost:8505)",min_value=0,max_value=100,value=50,step=1)
    st.caption("Enter current Fear-Greed score manually")
    if st.button("REFRESH NOW"): st.cache_data.clear(); st.rerun()
    st.markdown("---")
    ts=datetime.now().strftime("%d %b %Y  %I:%M %p")
    st.markdown(f"<div style='font-size:0.65rem;color:#334455;text-align:center'>{ts}<br>Auto-refresh: 60s<br>Stability: 2-period filter</div>",unsafe_allow_html=True)

api=load_key()
now_str=datetime.now().strftime("%d %b %Y  %I:%M %p")

st.markdown(f"<div style='font-size:1.6rem;font-weight:800;color:#e0e0e0;border-bottom:1px solid #1a2840;padding-bottom:12px;margin-bottom:20px'>MARKET REGIME ENGINE <span style='font-size:0.82rem;color:#445566'>{now_str}</span></div>",unsafe_allow_html=True)

# ── FETCH ALL DATA ─────────────────────────────────────────────────────────
with st.spinner("Fetching market data and calculating regime..."):
    mkt=fetch_market_data()
    ad_ratio,adv,dec=get_ad_ratio()

if not mkt or "nifty_close" not in mkt:
    st.error("Market data unavailable. Try refreshing.")
    st.stop()

# ── CALCULATE ALL INDICATORS ───────────────────────────────────────────────
nc=mkt["nifty_close"]
nh=mkt["nifty_high"]
nl=mkt["nifty_low"]

# Efficiency Ratio (10-day)
er=calc_efficiency_ratio(nc,10)

# ATR
atr_val=calc_atr(nh,nl,nc,14)
nifty_curr=mkt["nifty_curr"]
atr_pct=round((atr_val/nifty_curr)*100,3) if nifty_curr>0 else 1.0

# Bollinger Band Width
bb_ratio=calc_bb_width(nc,20)

# Moving Averages
ma20=calc_ma(nc,20)
ma50=calc_ma(nc,50)

# VIX data
vix_curr=mkt.get("vix_curr",15)
vix_prev=mkt.get("vix_prev",15)
vix_ma20=mkt.get("vix_ma20",15)
vix_pct=round(((vix_curr-vix_prev)/vix_prev)*100,2) if vix_prev>0 else 0

# Intraday metrics
nifty_open=mkt.get("nifty_open_today",nifty_curr)
nifty_high=mkt.get("nifty_high_today",nifty_curr)
nifty_low=mkt.get("nifty_low_today",nifty_curr)
nifty_prev=mkt.get("nifty_prev_close",nifty_curr)
nifty_pct_intraday=round(((nifty_curr-nifty_prev)/nifty_prev)*100,2) if nifty_prev>0 else 0
intraday_er=calc_intraday_er(nifty_open,nifty_high,nifty_low,nifty_curr)

# MA distance
nifty_above_ma20=round(((nifty_curr-ma20)/ma20)*100,2) if ma20>0 else 0

# BankNifty
bank_curr=mkt.get("bank_curr",54000)
bank_prev=mkt.get("bank_prev",54000)
bank_pct=round(((bank_curr-bank_prev)/bank_prev)*100,2) if bank_prev>0 else 0

# ── SCORE ALL REGIMES ──────────────────────────────────────────────────────
panic_score=calc_panic_score(vix_curr,vix_prev,ad_ratio,nifty_pct_intraday)
euphoria_score=calc_euphoria_score(fg_manual,ad_ratio,vix_curr,nifty_above_ma20)

all_scores=calc_all_regime_scores(
    er,atr_pct,bb_ratio,panic_score,euphoria_score,
    nifty_curr,ma20,ma50,ad_ratio,intraday_er,vix_curr
)

# ── APPLY STABILITY ENGINE ─────────────────────────────────────────────────
state=load_regime_state()
current_regime,confidence,secondary_regime,secondary_score,new_state=apply_stability(all_scores,state)

reg=REGIMES[current_regime]
put=PUT_SIGNALS[current_regime]

# ── MAIN REGIME DISPLAY ────────────────────────────────────────────────────
main1,main2=st.columns([1,1])

with main1:
    st.markdown(f"""
    <div style='background:{reg["bg"]};border:3px solid {reg["color"]};border-radius:20px;padding:30px;text-align:center;min-height:280px;display:flex;flex-direction:column;justify-content:center'>
        <div style='font-size:4rem;margin-bottom:8px'>{reg["icon"]}</div>
        <div style='font-size:0.72rem;color:#445566;letter-spacing:3px;margin-bottom:8px'>CURRENT MARKET REGIME</div>
        <div style='font-size:2.2rem;font-weight:900;color:{reg["color"]};margin-bottom:8px'>{current_regime}</div>
        <div style='color:#aabbcc;font-size:0.88rem;margin-bottom:16px'>{reg["desc"]}</div>
        <div style='display:flex;justify-content:center;gap:16px'>
            <div style='background:#0a0e1a;border-radius:10px;padding:10px 20px'>
                <div style='color:#445566;font-size:0.65rem'>CONFIDENCE</div>
                <div style='color:{reg["color"]};font-size:1.8rem;font-weight:900'>{confidence}%</div>
            </div>
            <div style='background:#0a0e1a;border-radius:10px;padding:10px 20px'>
                <div style='color:#445566;font-size:0.65rem'>STABILITY</div>
                <div style='color:#4488ff;font-size:1.8rem;font-weight:900'>{new_state["count"]}/2</div>
            </div>
        </div>
    </div>""",unsafe_allow_html=True)

with main2:
    # Put signal
    st.markdown(f"""
    <div style='background:#0d0020;border:2px solid {put["clr"]}44;border-left:5px solid {put["clr"]};border-radius:14px;padding:20px;margin-bottom:12px'>
        <div style='font-size:0.7rem;color:{put["clr"]};font-weight:800;letter-spacing:2px;margin-bottom:8px'>PUT TRADING SIGNAL</div>
        <div style='font-size:1.6rem;font-weight:900;color:{put["clr"]};margin-bottom:10px'>{put["action"]}</div>
        <div style='color:#aabbcc;font-size:0.88rem;line-height:1.6'>{put["detail"]}</div>
    </div>""",unsafe_allow_html=True)

    # Secondary regime
    if secondary_regime:
        sreg=REGIMES[secondary_regime]
        st.markdown(f"""
        <div style='background:#0d1626;border:1px solid {sreg["color"]}44;border-left:3px solid {sreg["color"]};border-radius:10px;padding:14px'>
            <div style='font-size:0.68rem;color:#445566;margin-bottom:4px'>SECONDARY REGIME</div>
            <div style='display:flex;justify-content:space-between;align-items:center'>
                <div><span style='font-size:1.2rem'>{sreg["icon"]}</span> <span style='color:{sreg["color"]};font-weight:800'>{secondary_regime}</span></div>
                <div style='color:{sreg["color"]};font-weight:800'>{secondary_score}%</div>
            </div>
            <div style='color:#445566;font-size:0.75rem;margin-top:4px'>{sreg["desc"]}</div>
        </div>""",unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style='background:#0d1626;border:1px solid #1a2840;border-radius:10px;padding:14px'>
            <div style='font-size:0.68rem;color:#445566;margin-bottom:4px'>SECONDARY REGIME</div>
            <div style='color:#334455'>None dominant — {current_regime} is clearly primary</div>
        </div>""",unsafe_allow_html=True)

    # Quick market snapshot
    st.markdown("<div style='margin-top:12px;display:grid;grid-template-columns:repeat(2,1fr);gap:8px'>",unsafe_allow_html=True)
    snaps=[
        ("NIFTY",str(nifty_curr),("#ff4444" if nifty_pct_intraday<0 else "#00ff88"),("+" if nifty_pct_intraday>=0 else "")+str(nifty_pct_intraday)+"%"),
        ("BANKNIFTY",str(bank_curr),("#ff4444" if bank_pct<0 else "#00ff88"),("+" if bank_pct>=0 else "")+str(bank_pct)+"%"),
        ("VIX",str(vix_curr),("#ff4444" if vix_curr>18 else "#ff8800" if vix_curr>15 else "#00ff88"),("+" if vix_pct>=0 else "")+str(vix_pct)+"%"),
        ("A/D RATIO",str(ad_ratio),("#ff4444" if ad_ratio<0.8 else "#ff8800" if ad_ratio<1.2 else "#00ff88"),str(adv)+" adv / "+str(dec)+" dec"),
    ]
    sc_html="<div style='display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:12px'>"
    for lbl,val,clr,sub in snaps:
        sc_html+=f"<div style='background:#0d1626;border-radius:8px;padding:10px;text-align:center'><div style='color:#445566;font-size:0.65rem'>{lbl}</div><div style='color:{clr};font-weight:800;font-size:0.95rem;margin-top:3px'>{val}</div><div style='color:#445566;font-size:0.68rem'>{sub}</div></div>"
    sc_html+="</div>"
    st.markdown(sc_html,unsafe_allow_html=True)

# ── KEY INDICATORS ─────────────────────────────────────────────────────────
if show_indicators:
    st.markdown("<div class='section-title'>KEY REGIME INDICATORS</div>",unsafe_allow_html=True)
    i1,i2,i3,i4,i5,i6=st.columns(6)
    er_clr="#ff4444" if er<0.30 else "#ff8800" if er<0.45 else "#ffdd00" if er<0.60 else "#00ff88"
    er_lbl="CHOPPY" if er<0.30 else "WEAK" if er<0.45 else "MODERATE" if er<0.60 else "STRONG TREND"
    atr_clr="#00ff88" if atr_pct<0.8 else "#ffdd00" if atr_pct<1.5 else "#ff8800" if atr_pct<2.5 else "#ff4444"
    bb_clr="#aa44ff" if bb_ratio<0.70 else "#ff8800" if bb_ratio<0.85 else "#00ff88"
    bb_lbl="STRONG SQUEEZE" if bb_ratio<0.70 else "COMPRESSION" if bb_ratio<0.85 else "NORMAL"
    ie_clr="#00ff88" if intraday_er>0.65 else "#ffdd00" if intraday_er>0.35 else "#ff4444"
    ie_lbl="DIRECTIONAL" if intraday_er>0.65 else "MIXED" if intraday_er>0.35 else "CHOPPY"
    with i1: st.markdown(card("EFFICIENCY RATIO",str(er),er_clr,er_lbl,"📊"),unsafe_allow_html=True)
    with i2: st.markdown(card("ATR %",str(atr_pct)+"%",atr_clr,("Low" if atr_pct<0.8 else "Moderate" if atr_pct<1.5 else "High" if atr_pct<2.5 else "EXTREME")+" vol","📈"),unsafe_allow_html=True)
    with i3: st.markdown(card("BB WIDTH",str(bb_ratio)+"x",bb_clr,bb_lbl,"🎯"),unsafe_allow_html=True)
    with i4: st.markdown(card("PANIC SCORE",str(panic_score),("#ff0000" if panic_score>70 else "#ff4444" if panic_score>50 else "#ff8800" if panic_score>30 else "#00ff88"),("EXTREME" if panic_score>70 else "HIGH" if panic_score>50 else "LOW")+" panic","😱"),unsafe_allow_html=True)
    with i5: st.markdown(card("INTRADAY ER",str(intraday_er),ie_clr,ie_lbl,"⚡"),unsafe_allow_html=True)
    with i6:
        ma_clr="#ff4444" if nifty_curr<ma50 else "#ff8800" if nifty_curr<ma20 else "#00ff88"
        ma_lbl="Below MA50" if nifty_curr<ma50 else "Below MA20" if nifty_curr<ma20 else "Above MAs"
        st.markdown(card("vs MA20",str(nifty_above_ma20)+"%",ma_clr,ma_lbl,"📉"),unsafe_allow_html=True)

# ── ALL REGIME SCORES ──────────────────────────────────────────────────────
if show_scores:
    st.markdown("<div class='section-title'>ALL REGIME SCORES — COMPLETE PICTURE</div>",unsafe_allow_html=True)
    sorted_scores=sorted(all_scores.items(),key=lambda x:x[1],reverse=True)
    for regime,score in sorted_scores:
        rg=REGIMES[regime]
        is_current=regime==current_regime
        is_secondary=regime==secondary_regime
        bar_w=max(1,round(score))
        border="2px solid "+rg["color"] if is_current else "1px solid "+rg["color"]+"44"
        bg=rg["bg"] if is_current else "#0d1626"
        badge=""
        if is_current: badge=f"<span style='background:{rg['color']};color:#000;padding:2px 10px;border-radius:20px;font-size:0.65rem;font-weight:800;margin-left:8px'>ACTIVE</span>"
        elif is_secondary: badge=f"<span style='background:{rg['color']}44;color:{rg['color']};padding:2px 10px;border-radius:20px;font-size:0.65rem;font-weight:800;margin-left:8px'>SECONDARY</span>"
        h=f"<div style='background:{bg};border:{border};border-radius:10px;padding:12px 18px;margin-bottom:6px'>"
        h+=f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'>"
        h+=f"<div><span style='font-size:1.2rem'>{rg['icon']}</span> <span style='color:{rg['color']};font-weight:800;font-size:0.92rem'>{regime}</span>{badge}</div>"
        h+=f"<div style='color:{rg['color']};font-weight:900;font-size:1.2rem'>{round(score,1)}/100</div></div>"
        h+=f"<div style='background:#0a0e1a;border-radius:4px;height:8px'><div style='background:{rg['color']};width:{bar_w}%;height:8px;border-radius:4px;transition:width 0.3s'></div></div>"
        h+=f"<div style='display:flex;justify-content:space-between;margin-top:4px'><span style='color:#334455;font-size:0.7rem'>{PUT_SIGNALS[regime]['action']}</span><span style='color:#334455;font-size:0.7rem'>{rg['desc']}</span></div>"
        h+="</div>"
        st.markdown(h,unsafe_allow_html=True)

# ── REGIME HISTORY CHART ───────────────────────────────────────────────────
st.markdown("<div class='section-title'>REGIME INDICATOR HISTORY (10-DAY)</div>",unsafe_allow_html=True)
try:
    er_series=[]
    c=mkt["nifty_close"].dropna()
    for i in range(max(0,len(c)-10),len(c)):
        if i>=10:
            sub=c.iloc[max(0,i-11):i+1]
            er_series.append(round(calc_efficiency_ratio(sub,10),3))
        else:
            er_series.append(0.5)

    dates=[str(d)[:10] for d in mkt["nifty_close"].dropna().index[-10:]]
    vix_hist=[round(float(v),2) for v in mkt.get("vix_series",pd.Series([vix_curr]*10)).dropna().tail(10)]

    fig=go.Figure()
    fig.add_trace(go.Scatter(x=dates,y=er_series[-len(dates):],name="Efficiency Ratio",
        line={"color":"#4488ff","width":2},yaxis="y"))
    if vix_hist:
        vix_norm=[v/40 for v in vix_hist]
        fig.add_trace(go.Scatter(x=dates,y=vix_norm[-len(dates):],name="VIX (normalized)",
            line={"color":"#ff4444","width":2,"dash":"dot"},yaxis="y"))
    fig.add_hline(y=0.60,line_color="#00ff88",line_width=1,line_dash="dot",annotation_text="Trending (0.60)",annotation_font_color="#00ff88")
    fig.add_hline(y=0.30,line_color="#ff4444",line_width=1,line_dash="dot",annotation_text="Choppy (0.30)",annotation_font_color="#ff4444")
    fig.update_layout(paper_bgcolor="#070b14",plot_bgcolor="#0d1626",
        xaxis={"tickfont":{"color":"#556677"},"gridcolor":"#1a2840"},
        yaxis={"range":[0,1],"tickfont":{"color":"#556677"},"gridcolor":"#1a2840","title":"ER / VIX norm"},
        height=240,margin=dict(l=10,r=10,t=20,b=20),
        legend={"font":{"color":"#aabbcc"},"bgcolor":"#0d1626"})
    st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False},key="regime_history")
except: st.info("History chart loading...")

# ── REGIME GUIDE ───────────────────────────────────────────────────────────
st.markdown("<div class='section-title'>COMPLETE REGIME GUIDE</div>",unsafe_allow_html=True)
for regime,(rg_info) in REGIMES.items():
    put_info=PUT_SIGNALS[regime]
    is_now=regime==current_regime
    border=f"2px solid {rg_info['color']};" if is_now else f"1px solid #1a2840;"
    bg=rg_info["bg"] if is_now else "#0d1626"
    h=f"<div style='display:grid;grid-template-columns:0.3fr 1.2fr 2fr 2fr;gap:12px;align-items:center;background:{bg};border:{border}border-radius:8px;padding:10px 16px;margin-bottom:6px'>"
    h+=f"<div style='font-size:1.4rem;text-align:center'>{rg_info['icon']}</div>"
    h+=f"<div style='color:{rg_info['color']};font-weight:800'>{regime}</div>"
    h+=f"<div style='color:#556677;font-size:0.82rem'>{rg_info['desc']}</div>"
    h+=f"<div style='color:{put_info['clr']};font-size:0.82rem;font-weight:700'>{put_info['action']}</div>"
    h+="</div>"
    st.markdown(h,unsafe_allow_html=True)

# ── AI INTERPRETATION ──────────────────────────────────────────────────────
if api and auto_ai:
    st.markdown("<div class='section-title'>AI REGIME INTERPRETATION</div>",unsafe_allow_html=True)
    top3=sorted(all_scores.items(),key=lambda x:x[1],reverse=True)[:3]
    top3_str=", ".join([f"{r}:{s}" for r,s in top3])
    p=(f"BearIQ Market Regime analyst.\n\n"
       f"CURRENT REGIME: {current_regime} ({confidence}% confidence)\n"
       f"SECONDARY: {secondary_regime or 'None'} ({secondary_score}%)\n\n"
       f"KEY INDICATORS:\n"
       f"- Efficiency Ratio: {er} ({('TRENDING' if er>0.60 else 'CHOPPY' if er<0.30 else 'MODERATE')})\n"
       f"- ATR %: {atr_pct}% ({('HIGH' if atr_pct>1.5 else 'LOW')} volatility)\n"
       f"- BB Width Ratio: {bb_ratio} ({('COMPRESSION' if bb_ratio<0.85 else 'NORMAL')})\n"
       f"- Panic Score: {panic_score}/100\n"
       f"- Intraday ER: {intraday_er}\n"
       f"- Nifty vs MA20: {nifty_above_ma20}%\n"
       f"- VIX: {vix_curr} ({('+' if vix_pct>=0 else '')}{vix_pct}%)\n"
       f"- A/D Ratio: {ad_ratio} ({adv} adv / {dec} dec)\n"
       f"- Fear-Greed: {fg_manual}/100\n\n"
       f"Top 3 regime scores: {top3_str}\n\n"
       f"Analyze in 4 points:\n"
       f"1. REGIME READING: Why is market in {current_regime} regime right now?\n"
       f"2. KEY DRIVER: Which indicator is most significant?\n"
       f"3. PUT STRATEGY: Exactly what F&O trader should do in this regime?\n"
       f"4. WATCH FOR: What change would signal regime shift?\n\n"
       f"Be direct. Use exact numbers. F&O traders will act on this.")
    with st.spinner("AI analyzing market regime..."): ai_r=groq(p,api,600)
    st.markdown(f"<div class='ai-box'><div style='font-size:0.7rem;color:#3388ff;font-weight:800;margin-bottom:12px'>BEARIQ AI — REGIME INTERPRETATION</div><div style='color:#ccddee;font-size:0.92rem;line-height:1.85'>{ai_r.replace(chr(10),'<br>')}</div></div>",unsafe_allow_html=True)

st.markdown("<div style='background:#0d1626;border:1px solid #1a2840;border-radius:8px;padding:10px 14px;color:#334455;font-size:0.72rem;margin-top:10px'>⚠ Market Regime Engine detects structure — not prediction. Combines Efficiency Ratio, ATR, Bollinger Bands, VIX, A/D Ratio. Not SEBI registered advice.</div>",unsafe_allow_html=True)
