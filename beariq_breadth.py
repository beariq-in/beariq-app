import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import requests, os, json, time

st.set_page_config(page_title="BearIQ — Market Breadth",page_icon="B",layout="wide",initial_sidebar_state="expanded")
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

# ── COMPLETE STOCK UNIVERSES ─────────────────────────
# NSE 500 broad universe for overall market breadth
NSE500_UNIVERSE = [
    # NIFTY 50
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","SBIN","BHARTIARTL","ITC",
    "KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI","SUNPHARMA","TITAN","BAJFINANCE",
    "ULTRACEMCO","WIPRO","ONGC","NTPC","TATAMOTORS","ADANIENT","HCLTECH","POWERGRID",
    "M&M","NESTLEIND","TATASTEEL","TECHM","COALINDIA","DRREDDY","DIVISLAB","BAJAJFINSV",
    "CIPLA","BRITANNIA","BPCL","EICHERMOT","GRASIM","HINDALCO","INDUSINDBK","JSWSTEEL",
    "APOLLOHOSP","ADANIPORTS","SBILIFE","TATACONSUM","LTIM","BAJAJ-AUTO","HEROMOTOCO",
    "HDFCLIFE","SHRIRAMFIN",
    # NIFTY NEXT 50
    "VEDL","SIEMENS","DLF","GODREJCP","MARICO","DABUR","PIIND","INDHOTEL","NAUKRI",
    "ICICIGI","HAVELLS","BERGEPAINT","MUTHOOTFIN","OFSS","LUPIN","TORNTPHARM","AUROPHARMA",
    "BANDHANBNK","FEDERALBNK","BIOCON","MOTHERSON","BALKRISIND","COLPAL","PERSISTENT",
    "MCDOWELL-N","TVSMOTOR","PAGEIND","ASTRAL","ABBOTINDIA","CHOLAFIN","SBICARD",
    "TRENT","DMART","NYKAA","ZOMATO","PAYTM","POLICYBZR","IRCTC","LICI",
    # MIDCAP SELECTIONS
    "VOLTAS","MPHASIS","COFORGE","LTTS","KPITTECH","TATAELXSI","HCLTECH","DIXON",
    "KAYNES","ZYDUSLIFE","ALKEM","IPCALAB","NATCOPHARM","JBCHEPHARM","GRANULES",
    "AARTIIND","DEEPAKNTR","SRF","ATUL","FINPIPE","RATNAMANI","HSCL","GNFC",
    "CANBK","BANKINDIA","UNIONBANK","INDIANB","MAHABANK","J&KBANK","KTKBANK",
    "RECLTD","PFC","IRFC","HUDCO","NHPC","SJVN","CESC","TORNTPOWER","JSL",
    "SAIL","NATIONALUM","HINDZINC","WELCORP","NMDC","MOIL","GMRINFRA","IRB",
    "ASHOKLEY","ESCORTS","TIINDIA","SUNDRMFAST","APOLLOTYRE","MRF","CEATLTD",
    "GODREJPROP","OBEROIRLTY","PRESTIGE","PHOENIXLTD","SOBHA","BRIGADE","MAHLIFE",
    "INOXWIND","SUZLON","RPOWER","TATAPOWER","ADANIGREEN","ADANIPOWER","CESC",
    "ZEEL","PVRINOX","INOXLEISURE","NAZARA","DELTACORP","WESTLIFE","DEVYANI",
    "ABCAPITAL","MFSL","ICICIPRU","HDFCAMC","NIPPONLIFE","MIRAE","EDELWEISS",
]

SECTOR_UNIVERSE = {
    "IT": ["TCS","INFY","WIPRO","HCLTECH","TECHM","LTIM","MPHASIS","COFORGE","PERSISTENT",
           "DIXON","KAYNES","TATAELXSI","LTTS","KPITTECH","ZENSARTECH","NIITTECH",
           "MASTEK","SONATSOFTW","TANLA","INTELLECT","NEWGEN","RATEGAIN","HAPPSTMNDS"],
    "BANK": ["HDFCBANK","ICICIBANK","AXISBANK","KOTAKBANK","SBIN","INDUSINDBK","FEDERALBNK",
             "BANDHANBNK","BANKBARODA","CANBK","BANKINDIA","UNIONBANK","INDIANB","MAHABANK",
             "J&KBANK","KTKBANK","DCBBANK","RBLBANK","YESBANK","IDFCFIRSTB","PNB","AUBANK"],
    "AUTO": ["MARUTI","TATAMOTORS","M&M","BAJAJ-AUTO","HEROMOTOCO","EICHERMOT","TVSMOTOR",
             "ASHOKLEY","BALKRISIND","APOLLOTYRE","MRF","CEATLTD","ESCORTS","TIINDIA",
             "SUNDRMFAST","MOTHERSON","BOSCHLTD","ENDURANCE","SUPRAJIT","GABRIEL"],
    "PHARMA": ["SUNPHARMA","DRREDDY","CIPLA","DIVISLAB","AUROPHARMA","LUPIN","TORNTPHARM",
               "ALKEM","IPCALAB","BIOCON","ZYDUSLIFE","NATCOPHARM","JBCHEPHARM","GRANULES",
               "GLENMARK","LAURUSLABS","AJANTPHARM","ABBOTINDIA","PFIZER","SANOFI"],
    "METAL": ["TATASTEEL","JSWSTEEL","HINDALCO","VEDL","SAIL","NATIONALUM","COALINDIA",
              "NMDC","HINDCOPPER","MOIL","WELCORP","RATNAMANI","APL","JINDALSAW"],
    "FMCG": ["HINDUNILVR","ITC","NESTLEIND","BRITANNIA","DABUR","MARICO","GODREJCP","COLPAL",
             "TATACONSUM","EMAMILTD","JYOTHYLAB","BIKAJI","PATANJALI","VBL","CCL"],
    "REALTY": ["DLF","GODREJPROP","OBEROIRLTY","PRESTIGE","PHOENIXLTD","SOBHA","BRIGADE",
               "MAHLIFE","SUNTECK","KOLTEPATIL","PURVA","ANANTRAJ","INDIABULLS","ELDECO"],
    "ENERGY": ["RELIANCE","ONGC","BPCL","IOC","GAIL","NTPC","POWERGRID","TATAPOWER",
               "ADANIGREEN","ADANIPOWER","CESC","TORNTPOWER","NHPC","SJVN","RECLTD"],
}

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

@st.cache_data(ttl=60)
def calc_breadth(stocks, label="Market"):
    """
    Professional breadth calculation on complete universe
    Returns comprehensive breadth data
    """
    adv=0; dec=0; unch=0
    details=[]
    total_attempted=len(stocks)
    # Batch download for speed
    try:
        tickers=[s+".NS" for s in stocks]
        batch=yf.download(tickers,period="3d",interval="1d",group_by="ticker",progress=False,threads=True)
        for sym in stocks:
            try:
                ticker=sym+".NS"
                if len(tickers)==1:
                    df=batch
                else:
                    df=batch[ticker] if ticker in batch.columns.get_level_values(0) else None
                if df is None or df.empty: continue
                close=df["Close"].dropna()
                if len(close)<2: continue
                curr=close.iloc[-1]; prev=close.iloc[-2]
                pct=round(((curr-prev)/prev)*100,2) if prev and prev>0 else 0
                if pct>0.25: adv+=1; status="ADV"
                elif pct<-0.25: dec+=1; status="DEC"
                else: unch+=1; status="UNC"
                details.append({"sym":sym,"pct":pct,"status":status,"price":round(curr,2)})
            except: pass
    except Exception as e:
        # Fallback: individual fetch if batch fails
        for sym in stocks:
            try:
                t=yf.Ticker(sym+".NS")
                h=t.history(period="3d",interval="1d")
                if len(h)>=2:
                    curr=h["Close"].iloc[-1]; prev=h["Close"].iloc[-2]
                    pct=round(((curr-prev)/prev)*100,2) if prev and prev>0 else 0
                    if pct>0.25: adv+=1; status="ADV"
                    elif pct<-0.25: dec+=1; status="DEC"
                    else: unch+=1; status="UNC"
                    details.append({"sym":sym,"pct":pct,"status":status,"price":round(curr,2)})
            except: pass
    total=adv+dec+unch
    ad_ratio=round(adv/dec,2) if dec>0 else 5.0
    ad_pct=round((adv/total)*100,1) if total>0 else 50
    dec_pct=round((dec/total)*100,1) if total>0 else 50
    # Breadth score 0-100 (0=worst, 100=best for bulls, 50=neutral)
    breadth_score=round(ad_pct)
    # Signal
    if ad_ratio<0.3: signal="EXTREME WEAKNESS"; sig_clr="#ff0000"; bear_signal=True
    elif ad_ratio<0.6: signal="STRONG WEAKNESS"; sig_clr="#ff4444"; bear_signal=True
    elif ad_ratio<0.8: signal="MILD WEAKNESS"; sig_clr="#ff8800"; bear_signal=True
    elif ad_ratio<1.2: signal="NEUTRAL"; sig_clr="#ffdd00"; bear_signal=False
    elif ad_ratio<1.8: signal="MILD STRENGTH"; sig_clr="#44ff88"; bear_signal=False
    else: signal="STRONG BREADTH"; sig_clr="#00ff44"; bear_signal=False
    # Sort details by pct
    details.sort(key=lambda x:x["pct"])
    top_decliners=details[:5]
    top_advancers=sorted(details,key=lambda x:x["pct"],reverse=True)[:5]
    return {
        "advances":adv,"declines":dec,"unchanged":unch,
        "total":total,"total_attempted":total_attempted,
        "ad_ratio":ad_ratio,"ad_pct":ad_pct,"dec_pct":dec_pct,
        "breadth_score":breadth_score,
        "signal":signal,"sig_clr":sig_clr,"bear_signal":bear_signal,
        "top_decliners":top_decliners,"top_advancers":top_advancers,
        "details":details,"label":label,
        "fetched_at":datetime.now().strftime("%I:%M:%S %p")
    }

@st.cache_data(ttl=3600)
def calc_breadth_trend(stocks, days=5):
    """Track breadth over last N days to show trend"""
    trend_data=[]
    try:
        tickers=[s+".NS" for s in stocks[:50]]  # limit for trend
        batch=yf.download(tickers,period="10d",interval="1d",group_by="ticker",progress=False,threads=True)
        # Get date index
        if hasattr(batch.index,"date"):
            dates=sorted(set(batch.index.date))[-days:]
        else:
            dates=[]
        for i in range(1,min(days+1,len(dates))):
            d=dates[i]; pd_=dates[i-1]
            adv=0; dec=0
            for sym in stocks[:50]:
                try:
                    ticker=sym+".NS"
                    df=batch[ticker] if ticker in batch.columns.get_level_values(0) else None
                    if df is None: continue
                    curr_row=df[df.index.date==d]["Close"]
                    prev_row=df[df.index.date==pd_]["Close"]
                    if curr_row.empty or prev_row.empty: continue
                    curr=curr_row.iloc[0]; prev=prev_row.iloc[0]
                    pct=((curr-prev)/prev)*100 if prev and prev>0 else 0
                    if pct>0.25: adv+=1
                    elif pct<-0.25: dec+=1
                except: pass
            total=adv+dec
            if total>0:
                trend_data.append({"date":str(d),"advances":adv,"declines":dec,
                    "ad_ratio":round(adv/dec,2) if dec>0 else 5.0,
                    "ad_pct":round((adv/total)*100,1)})
    except Exception as e: pass
    return trend_data

def detect_divergence(breadth_data, index_pct):
    """
    Detect breadth divergences — most powerful signal
    """
    ad_ratio=breadth_data["ad_ratio"]
    divs=[]
    # Classic divergence: Index up but breadth weak
    if index_pct>0.3 and ad_ratio<0.8:
        divs.append({"type":"BEARISH DIVERGENCE","severity":"HIGH","clr":"#ff2222",
            "msg":"Index rising but "+str(breadth_data["declines"])+" stocks falling vs "+str(breadth_data["advances"])+" rising. Smart money exiting — STRONG PUT SIGNAL."})
    # Index flat but breadth collapsing
    elif abs(index_pct)<0.3 and ad_ratio<0.6:
        divs.append({"type":"HIDDEN WEAKNESS","severity":"HIGH","clr":"#ff4444",
            "msg":"Index appears stable but breadth collapsing. Institutional distribution happening. Puts recommended."})
    # Both index and breadth falling — confirmed bear
    elif index_pct<-0.5 and ad_ratio<0.6:
        divs.append({"type":"CONFIRMED BEAR","severity":"EXTREME","clr":"#ff0000",
            "msg":"Index AND breadth both collapsing. Broad market selling. Maximum bearish signal."})
    # Index down but breadth strong — likely bounce
    elif index_pct<-0.5 and ad_ratio>1.2:
        divs.append({"type":"BULLISH DIVERGENCE","severity":"CAUTION","clr":"#00ff88",
            "msg":"Index falling but majority stocks rising. Likely index-heavy stock drag. Avoid puts — may bounce."})
    # Healthy market
    elif ad_ratio>1.5 and index_pct>0:
        divs.append({"type":"HEALTHY MARKET","severity":"LOW","clr":"#00ff88",
            "msg":"Broad participation in rally. Avoid bearish trades — risk is high for puts."})
    else:
        divs.append({"type":"NO DIVERGENCE","severity":"NEUTRAL","clr":"#ffdd00",
            "msg":"Index and breadth moving together. No special signal. Watch for divergence."})
    return divs

def breadth_trade_signal(breadth_data, index_pct, vix_pct=0):
    """Generate clear trading signal from breadth data"""
    ad_ratio=breadth_data["ad_ratio"]
    adv=breadth_data["advances"]
    dec=breadth_data["declines"]
    total=breadth_data["total"]
    # Signal logic
    if ad_ratio<0.3 and index_pct<-0.5:
        return {"action":"STRONG PUT BUY","clr":"#ff0000","bg":"#1a0000",
            "confidence":88,"reason":"Breadth collapsed ("+str(dec)+" stocks falling vs "+str(adv)+"). Broad selling confirmed."}
    elif ad_ratio<0.6 and (index_pct<0 or vix_pct>3):
        return {"action":"BUY PUTS","clr":"#ff4444","bg":"#140000",
            "confidence":74,"reason":"Weak breadth (A/D: "+str(ad_ratio)+") with "+str(dec)+" decliners. Good put entry."}
    elif ad_ratio<0.8 and index_pct>0.3:
        return {"action":"BUY PUTS (Divergence)","clr":"#ff6600","bg":"#1a0800",
            "confidence":70,"reason":"Index up but breadth weak — classic distribution. Smart money exiting."}
    elif ad_ratio<1.0:
        return {"action":"WATCH — MILD WEAKNESS","clr":"#ff8800","bg":"#1a0a00",
            "confidence":50,"reason":"Slightly more decliners than advancers. Monitor for deterioration."}
    elif ad_ratio>1.5:
        return {"action":"AVOID PUTS","clr":"#00ff88","bg":"#001a08",
            "confidence":0,"reason":"Strong breadth ("+str(adv)+" advancing vs "+str(dec)+" declining). Puts are risky."}
    else:
        return {"action":"STAND ASIDE","clr":"#ffdd00","bg":"#141000",
            "confidence":30,"reason":"Neutral breadth. Wait for clearer direction."}

@st.cache_data(ttl=60)
def get_nifty():
    try:
        t=yf.Ticker("^NSEI")
        h=t.history(period="3d",interval="1d")
        h5=t.history(period="1d",interval="5m")
        if h.empty: return 24000,0
        curr=h5["Close"].iloc[-1] if not h5.empty else h["Close"].iloc[-1]
        prev=h["Close"].iloc[-2] if len(h)>1 else h["Close"].iloc[-1]
        return round(curr,2),round(((curr-prev)/prev)*100,2)
    except: return 24000,0

@st.cache_data(ttl=60)
def get_vix():
    try:
        t=yf.Ticker("^INDIAVIX")
        h=t.history(period="3d",interval="1d")
        h5=t.history(period="1d",interval="5m")
        if h.empty: return 15,0
        curr=h5["Close"].iloc[-1] if not h5.empty else h["Close"].iloc[-1]
        prev=h["Close"].iloc[-2] if len(h)>1 else h["Close"].iloc[-1]
        return round(curr,2),round(((curr-prev)/prev)*100,2)
    except: return 15,0

with st.sidebar:
    st.markdown("<div style='text-align:center;padding:14px 0 8px'><div style='font-size:2rem;font-weight:900;color:#ff4444;letter-spacing:4px'>BearIQ</div><div style='font-size:0.6rem;color:#334455;letter-spacing:2px'>MARKET BREADTH INTELLIGENCE</div></div>",unsafe_allow_html=True)
    st.markdown("---")
    view=st.radio("Select View",[
        "Overall Market (NSE Broad)",
        "IT Sector",
        "Banking Sector",
        "Auto Sector",
        "Pharma Sector",
        "Metal Sector",
        "FMCG Sector",
        "Realty Sector",
        "Energy Sector",
    ],label_visibility="collapsed")
    st.markdown("---")
    show_trend=st.checkbox("Show 5-Day Breadth Trend",value=True)
    show_stocks=st.checkbox("Show Top Movers",value=True)
    auto_ai=st.toggle("AI Interpretation",value=True)
    if st.button("REFRESH BREADTH"): st.cache_data.clear(); st.rerun()
    st.markdown("---")
    ts=datetime.now().strftime("%d %b %Y  %I:%M %p")
    st.markdown("<div style='font-size:0.65rem;color:#334455;text-align:center'>"+ts+"<br>Breadth updates every 60s</div>",unsafe_allow_html=True)

api=load_key()
now_str=datetime.now().strftime("%d %b %Y  %I:%M %p")
nifty_p,nifty_pct=get_nifty()
vix_p,vix_pct=get_vix()

if "Overall" in view:
    universe=NSE500_UNIVERSE; u_label="NSE Broad Market"; u_count=len(NSE500_UNIVERSE)
    sec_key=None
else:
    sec_map={"IT":"IT","Banking":"BANK","Auto":"AUTO","Pharma":"PHARMA","Metal":"METAL","FMCG":"FMCG","Realty":"REALTY","Energy":"ENERGY"}
    for k,v in sec_map.items():
        if k in view: sec_key=v; break
    else: sec_key="IT"
    universe=SECTOR_UNIVERSE.get(sec_key,[]); u_label=view.split(" Sector")[0].strip()+" Sector"; u_count=len(universe)

st.markdown("<div style='font-size:1.6rem;font-weight:800;color:#e0e0e0;border-bottom:1px solid #1a2840;padding-bottom:12px;margin-bottom:20px'>MARKET BREADTH INTELLIGENCE <span style='font-size:0.82rem;color:#445566'>"+now_str+"</span></div>",unsafe_allow_html=True)

# Market context strip
mc1,mc2,mc3,mc4=st.columns(4)
nclr="#ff4444" if nifty_pct<0 else "#00ff88"
vclr="#ff4444" if vix_p>20 else "#ff8800" if vix_p>17 else "#00ff88"
with mc1: st.markdown(card("NIFTY",str(nifty_p),nclr,("+" if nifty_pct>=0 else "")+str(nifty_pct)+"% today","📊"),unsafe_allow_html=True)
with mc2: st.markdown(card("VIX",str(vix_p),vclr,("+" if vix_pct>=0 else "")+str(vix_pct)+"%","😱"),unsafe_allow_html=True)
with mc3: st.markdown(card("UNIVERSE",str(u_count)+" stocks","#4488ff","being analyzed","🔍"),unsafe_allow_html=True)
with mc4: st.markdown(card("VIEW",u_label,"#cc44ff","breadth universe","📈"),unsafe_allow_html=True)

# FETCH BREADTH
with st.spinner("Calculating market breadth for "+str(u_count)+" stocks... Please wait..."):
    breadth=calc_breadth(universe, u_label)

if not breadth or breadth["total"]==0:
    st.error("Breadth calculation failed. Market may be closed or data unavailable.")
    st.stop()

# ── BREADTH DASHBOARD ──
st.markdown("<div class='section-title'>MARKET BREADTH — "+u_label.upper()+"</div>",unsafe_allow_html=True)

# Big A/D display
ratio_clr="#ff0000" if breadth["ad_ratio"]<0.3 else "#ff4444" if breadth["ad_ratio"]<0.6 else "#ff8800" if breadth["ad_ratio"]<0.8 else "#ffdd00" if breadth["ad_ratio"]<1.2 else "#44ff88" if breadth["ad_ratio"]<1.8 else "#00ff44"
st.markdown("<div style='background:#0d1626;border:2px solid "+ratio_clr+";border-radius:16px;padding:24px;margin-bottom:16px'>"
    +"<div style='display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr;gap:16px;align-items:center'>"
    # Advancing
    +"<div style='text-align:center'>"
    +"<div style='font-size:3.5rem;font-weight:900;color:#00ff88'>"+str(breadth["advances"])+"</div>"
    +"<div style='color:#445566;font-size:0.75rem;letter-spacing:2px'>ADVANCING</div>"
    +"<div style='color:#00ff88;font-size:0.85rem;font-weight:700'>"+str(breadth["ad_pct"])+"%</div></div>"
    # Declining
    +"<div style='text-align:center'>"
    +"<div style='font-size:3.5rem;font-weight:900;color:#ff4444'>"+str(breadth["declines"])+"</div>"
    +"<div style='color:#445566;font-size:0.75rem;letter-spacing:2px'>DECLINING</div>"
    +"<div style='color:#ff4444;font-size:0.85rem;font-weight:700'>"+str(breadth["dec_pct"])+"%</div></div>"
    # Unchanged
    +"<div style='text-align:center'>"
    +"<div style='font-size:3.5rem;font-weight:900;color:#ffdd00'>"+str(breadth["unchanged"])+"</div>"
    +"<div style='color:#445566;font-size:0.75rem;letter-spacing:2px'>UNCHANGED</div>"
    +"<div style='color:#334455;font-size:0.85rem'>"+str(breadth["total"])+" total</div></div>"
    # A/D Ratio
    +"<div style='text-align:center;border-left:1px solid #1a2840;padding-left:16px'>"
    +"<div style='font-size:3rem;font-weight:900;color:"+ratio_clr+"'>"+str(breadth["ad_ratio"])+"</div>"
    +"<div style='color:#445566;font-size:0.75rem;letter-spacing:2px'>A/D RATIO</div>"
    +"<div style='color:"+ratio_clr+";font-size:0.85rem;font-weight:700'>"+breadth["signal"]+"</div></div>"
    # Signal
    +"<div style='text-align:center;border-left:1px solid #1a2840;padding-left:16px'>"
    +"<div style='font-size:0.72rem;color:#445566;letter-spacing:2px;margin-bottom:8px'>UNIVERSE</div>"
    +"<div style='color:#ccddee;font-size:0.85rem'>"+str(breadth["total"])+" of "+str(breadth["total_attempted"])+" stocks</div>"
    +"<div style='color:#334455;font-size:0.72rem;margin-top:4px'>fetched at "+breadth["fetched_at"]+"</div>"
    +"</div>"
    +"</div></div>",unsafe_allow_html=True)

adv_pct_v=breadth["ad_pct"]; dec_pct_v=breadth["dec_pct"]; unc_pct_v=round(100-adv_pct_v-dec_pct_v,1)
bar_html="<div style='margin-bottom:16px'>"
bar_html+="<div style='display:flex;justify-content:space-between;margin-bottom:4px'>"
bar_html+="<span style='color:#00ff88;font-size:0.78rem;font-weight:700'>"+str(adv_pct_v)+"% Advancing</span>"
bar_html+="<span style='color:#ffdd00;font-size:0.78rem'>"+str(unc_pct_v)+"% Unchanged</span>"
bar_html+="<span style='color:#ff4444;font-size:0.78rem;font-weight:700'>"+str(dec_pct_v)+"% Declining</span></div>"
bar_html+="<div style='display:flex;border-radius:8px;overflow:hidden;height:24px'>"
bar_html+="<div style='width:"+str(adv_pct_v)+"%;background:#00ff88;opacity:0.8'></div>"
bar_html+="<div style='width:"+str(unc_pct_v)+"%;background:#334455'></div>"
bar_html+="<div style='width:"+str(dec_pct_v)+"%;background:#ff4444;opacity:0.8'></div>"
bar_html+="</div></div>"
st.markdown(bar_html,unsafe_allow_html=True)

st.markdown("<div class='section-title'>DIVERGENCE DETECTION</div>",unsafe_allow_html=True)
divs=detect_divergence(breadth,nifty_pct)
for div in divs:
    sev_bg="#1a0000" if div["severity"] in ["EXTREME","HIGH"] else "#0d1626"
    bw="3px" if div["severity"] in ["EXTREME","HIGH"] else "1px"
    st.markdown("<div style='background:"+sev_bg+";border:"+bw+" solid "+div["clr"]+"44;border-left:5px solid "+div["clr"]+";border-radius:12px;padding:16px 20px;margin-bottom:10px'>"
        +"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'>"
        +"<div style='color:"+div["clr"]+";font-weight:800;font-size:1rem'>"+div["type"]+"</div>"
        +"<div style='background:#0a0e1a;color:"+div["clr"]+";padding:3px 12px;border-radius:20px;font-size:0.75rem;font-weight:800'>"+div["severity"]+"</div></div>"
        +"<div style='color:#ccddee;font-size:0.9rem;line-height:1.6'>"+div["msg"]+"</div>"
        +"</div>",unsafe_allow_html=True)

st.markdown("<div class='section-title'>BREADTH TRADING SIGNAL</div>",unsafe_allow_html=True)
sig=breadth_trade_signal(breadth,nifty_pct,vix_pct)
st.markdown("<div style='background:"+sig["bg"]+";border:2px solid "+sig["clr"]+";border-radius:14px;padding:24px;text-align:center;margin-bottom:16px'>"
    +"<div style='font-size:0.72rem;color:#445566;letter-spacing:3px;margin-bottom:8px'>BREADTH SIGNAL — "+u_label.upper()+"</div>"
    +"<div style='font-size:2rem;font-weight:900;color:"+sig["clr"]+";margin-bottom:12px'>"+sig["action"]+"</div>"
    +"<div style='color:#aabbcc;font-size:0.9rem'>"+sig["reason"]+"</div>"
    +("<div style='margin-top:12px'><div style='color:#445566;font-size:0.7rem'>CONFIDENCE</div><div style='font-size:1.5rem;font-weight:800;color:"+sig["clr"]+"'>"+str(sig["confidence"])+"%</div></div>" if sig["confidence"]>0 else "")
    +"</div>",unsafe_allow_html=True)

if show_trend:
    st.markdown("<div class='section-title'>5-DAY BREADTH TREND</div>",unsafe_allow_html=True)
    with st.spinner("Loading 5-day breadth trend..."):
        trend=calc_breadth_trend(universe[:50])
    if trend:
        dates_t=[t["date"] for t in trend]
        adv_t=[t["advances"] for t in trend]
        dec_t=[t["declines"] for t in trend]
        ratio_t=[t["ad_ratio"] for t in trend]
        fig=go.Figure()
        fig.add_trace(go.Bar(name="Advancing",x=dates_t,y=adv_t,marker_color="#00ff88",opacity=0.8))
        fig.add_trace(go.Bar(name="Declining",x=dates_t,y=[-d for d in dec_t],marker_color="#ff4444",opacity=0.8))
        fig.add_hline(y=0,line_color="#445566",line_width=1)
        fig.update_layout(barmode="overlay",paper_bgcolor="#070b14",plot_bgcolor="#0d1626",
            xaxis={"tickfont":{"color":"#778899"},"gridcolor":"#1a2840"},
            yaxis={"tickfont":{"color":"#556677"},"gridcolor":"#1a2840","title":"Stock Count"},
            height=250,margin=dict(l=10,r=10,t=20,b=20),
            legend={"bgcolor":"#0d1626","font":{"color":"#aabbcc"}})
        st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False},key="trend_chart")
        # Trend direction
        if len(ratio_t)>=2:
            trend_dir="IMPROVING" if ratio_t[-1]>ratio_t[0] else "DETERIORATING" if ratio_t[-1]<ratio_t[0] else "STABLE"
            td_clr="#00ff88" if trend_dir=="IMPROVING" else "#ff4444" if trend_dir=="DETERIORATING" else "#ffdd00"
            st.markdown("<div style='background:#0d1626;border:1px solid #1a2840;border-left:4px solid "+td_clr+";border-radius:8px;padding:12px 18px'>"
                +"<div style='color:"+td_clr+";font-weight:800;font-size:0.9rem'>BREADTH TREND: "+trend_dir+"</div>"
                +"<div style='color:#445566;font-size:0.8rem;margin-top:4px'>5-day A/D trend: "+str(ratio_t[0])+" → "+str(ratio_t[-1])+"</div>"
                +"</div>",unsafe_allow_html=True)
    else:
        st.info("Trend data available during/after market hours.")

if show_stocks and breadth["details"]:
    st.markdown("<div class='section-title'>TOP DECLINERS & ADVANCERS</div>",unsafe_allow_html=True)
    tm1,tm2=st.columns(2)
    with tm1:
        st.markdown("<div style='font-size:0.78rem;color:#ff4444;font-weight:700;margin-bottom:8px'>TOP DECLINERS</div>",unsafe_allow_html=True)
        for stk in breadth["top_decliners"][:7]:
            row="<div style='display:flex;justify-content:space-between;background:#1a0000;border-left:3px solid #ff4444;border-radius:4px;padding:6px 12px;margin-bottom:4px'>"
            row+="<span style='color:#ccddee;font-weight:700'>"+stk["sym"]+"</span>"
            row+="<span style='color:#ff4444;font-weight:800'>"+str(stk["pct"])+"%</span>"
            row+="</div>"
            st.markdown(row,unsafe_allow_html=True)
    with tm2:
        st.markdown("<div style='font-size:0.78rem;color:#00ff88;font-weight:700;margin-bottom:8px'>TOP ADVANCERS</div>",unsafe_allow_html=True)
        for stk in breadth["top_advancers"][:7]:
            row="<div style='display:flex;justify-content:space-between;background:#001a08;border-left:3px solid #00ff88;border-radius:4px;padding:6px 12px;margin-bottom:4px'>"
            row+="<span style='color:#ccddee;font-weight:700'>"+stk["sym"]+"</span>"
            row+="<span style='color:#00ff88;font-weight:800'>+"+str(stk["pct"])+"%</span>"
            row+="</div>"
            st.markdown(row,unsafe_allow_html=True)

if api and auto_ai:
    st.markdown("<div class='section-title'>AI BREADTH INTERPRETATION</div>",unsafe_allow_html=True)
    div_text=divs[0]["type"]+" — "+divs[0]["msg"] if divs else "No divergence"
    p=("BearIQ market breadth analyst.\n\n"
        +"BREADTH DATA ("+u_label+"):\n"
        +"Universe: "+str(breadth["total"])+" stocks analyzed\n"
        +"Advancing: "+str(breadth["advances"])+" ("+str(breadth["ad_pct"])+"%)\n"
        +"Declining: "+str(breadth["declines"])+" ("+str(breadth["dec_pct"])+"%)\n"
        +"A/D Ratio: "+str(breadth["ad_ratio"])+" — "+breadth["signal"]+"\n"
        +"Nifty: "+str(nifty_p)+" ("+str(nifty_pct)+"% today)\n"
        +"VIX: "+str(vix_p)+" ("+str(vix_pct)+"%)\n"
        +"Divergence: "+div_text+"\n"
        +"Trading Signal: "+sig["action"]+" ("+str(sig["confidence"])+"% confidence)\n\n"
        +"Give professional market breadth analysis:\n"
        +"1. BREADTH READING: What "+str(breadth["ad_ratio"])+" A/D ratio tells us right now\n"
        +"2. DIVERGENCE IMPACT: Is divergence signal reliable here?\n"
        +"3. TRADING RECOMMENDATION: Should trader buy puts, avoid, or wait?\n"
        +"4. KEY WATCH LEVEL: What A/D ratio would change your view?\n"
        +"5. CONFIDENCE: Overall confidence in bearish trade right now (%)\n\n"
        +"Be direct. Use exact numbers. This is for professional F&O traders.")
    with st.spinner("AI analyzing market breadth..."): ai_r=groq(p,api,700)
    st.markdown("<div class='ai-box'><div style='font-size:0.7rem;color:#3388ff;font-weight:800;margin-bottom:12px'>BEARIQ AI — BREADTH INTERPRETATION</div><div style='color:#ccddee;font-size:0.92rem;line-height:1.85'>"+ai_r.replace("\n","<br>")+"</div></div>",unsafe_allow_html=True)

st.markdown("<div style='background:#0d1626;border:1px solid #1a2840;border-radius:8px;padding:10px 14px;color:#334455;font-size:0.72rem;margin-top:10px'>⚠ Breadth data based on price movement from yFinance. Updates every 60 seconds. Not SEBI registered advice.</div>",unsafe_allow_html=True)