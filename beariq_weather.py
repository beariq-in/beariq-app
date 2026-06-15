"""
BearIQ Market Weather Report Engine
Auto-generates and sends reports at 8:45 AM and 9:30 AM
"""
import json, os, requests
from datetime import datetime
import yfinance as yf
import streamlit as st

BASE = os.path.dirname(os.path.abspath(__file__))
WEATHER_FILE = os.path.join(BASE, "data", "weather_reports.json")
USERS_FILE = os.path.join(BASE, "data", "users.json")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

def ensure_data_dir():
    os.makedirs(os.path.join(BASE,"data"), exist_ok=True)

def load_key():
    for p in [os.path.join(BASE,"config.txt"),
              os.path.join(BASE,".streamlit","secrets.toml"),
              "config.txt"]:
        if os.path.exists(p):
            content = open(p).read().strip()
            # Handle secrets.toml format
            if "groq_api_key" in content:
                for line in content.split("\n"):
                    if "groq_api_key" in line:
                        return line.split("=")[1].strip().strip('"').strip("'")
            elif content and not content.startswith("["):
                return content
    # Try Streamlit secrets
    try:
        return st.secrets.get("groq_api_key","")
    except: return ""

def load_weather_reports():
    ensure_data_dir()
    if os.path.exists(WEATHER_FILE):
        try:
            with open(WEATHER_FILE,"r") as f: return json.load(f)
        except: return []
    return []

def save_weather_report(report):
    ensure_data_dir()
    reports = load_weather_reports()
    reports.append(report)
    # Keep last 90 days only
    reports = reports[-180:]
    with open(WEATHER_FILE,"w") as f: json.dump(reports,f,indent=2)

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE,"r") as f: return json.load(f)
        except: return {}
    return {}


# ── MARKET NEWS FETCHER (RSS — free, headlines only) ────────────
@st.cache_data(ttl=900)
def fetch_market_news(max_items=5):
    """
    Fetch top market headlines from free RSS feeds.
    Headlines + source + link only — copyright safe.
    """
    import xml.etree.ElementTree as ET
    feeds = [
        ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
        ("Moneycontrol", "https://www.moneycontrol.com/rss/marketreports.xml"),
        ("LiveMint", "https://www.livemint.com/rss/markets"),
    ]
    headlines = []
    for source, url in feeds:
        try:
            r = requests.get(url, timeout=8,
                headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            if r.status_code != 200: continue
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            for item in items[:3]:
                title = item.find("title")
                link = item.find("link")
                if title is not None and title.text:
                    t = title.text.strip()
                    # Filter: market-relevant only, skip stock tips
                    skip_words = ["buy","sell","target price","multibagger",
                                  "stock pick","stocks to","top picks"]
                    if any(w in t.lower() for w in skip_words): continue
                    headlines.append({
                        "title": t[:150],
                        "source": source,
                        "link": link.text.strip() if link is not None and link.text else ""
                    })
        except: continue
    # Deduplicate by title similarity (first 50 chars)
    seen = set(); unique = []
    for h in headlines:
        key = h["title"][:50].lower()
        if key not in seen:
            seen.add(key)
            unique.append(h)
    return unique[:max_items]

# ── MARKET DATA FETCHER ───────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch_weather_data():
    """Fetch all data needed for weather report"""
    d = {}
    try:
        # Nifty
        t=yf.Ticker("^NSEI")
        h=t.history(period="30d",interval="1d")
        h5=t.history(period="1d",interval="5m")
        if not h.empty:
            c=h["Close"]
            curr=round(float(h5["Close"].iloc[-1]) if not h5.empty else float(c.iloc[-1]),2)
            prev=float(c.iloc[-2]) if len(c)>1 else curr
            d["nifty"]=curr
            d["nifty_pct"]=round(((curr-prev)/prev)*100,2)
            d["nifty_rsi"]=50
            if len(c)>=14:
                delta=c.diff(); gain=delta.clip(lower=0).rolling(14).mean()
                loss=(-delta.clip(upper=0)).rolling(14).mean()
                d["nifty_rsi"]=round(float((100-(100/(1+gain/loss))).iloc[-1]),1)
    except: d["nifty"]=0; d["nifty_pct"]=0; d["nifty_rsi"]=50
    try:
        t=yf.Ticker("^NSEBANK")
        h=t.history(period="5d",interval="1d")
        h5=t.history(period="1d",interval="5m")
        curr=round(float(h5["Close"].iloc[-1]) if not h5.empty else float(h["Close"].iloc[-1]),2)
        prev=float(h["Close"].iloc[-2]) if len(h)>1 else curr
        d["banknifty"]=curr; d["banknifty_pct"]=round(((curr-prev)/prev)*100,2)
    except: d["banknifty"]=0; d["banknifty_pct"]=0
    try:
        t=yf.Ticker("^INDIAVIX")
        h=t.history(period="30d",interval="1d")
        h5=t.history(period="1d",interval="5m")
        curr=round(float(h5["Close"].iloc[-1]) if not h5.empty else float(h["Close"].iloc[-1]),2)
        prev=float(h["Close"].iloc[-2]) if len(h)>1 else curr
        d["vix"]=curr; d["vix_pct"]=round(((curr-prev)/prev)*100,2)
        d["vix_ma20"]=round(float(h["Close"].rolling(20).mean().iloc[-1]),2) if len(h)>=20 else curr
    except: d["vix"]=15; d["vix_pct"]=0; d["vix_ma20"]=15
    try:
        t=yf.Ticker("GC=F")
        h=t.history(period="5d",interval="1d")
        h5=t.history(period="1d",interval="5m")
        curr=round(float(h5["Close"].iloc[-1]) if not h5.empty else float(h["Close"].iloc[-1]),2)
        prev=float(h["Close"].iloc[-2]) if len(h)>1 else curr
        d["gold"]=curr; d["gold_pct"]=round(((curr-prev)/prev)*100,2)
    except: d["gold"]=2300; d["gold_pct"]=0
    try:
        t=yf.Ticker("USDINR=X")
        h=t.history(period="5d",interval="1d")
        h5=t.history(period="1d",interval="5m")
        curr=round(float(h5["Close"].iloc[-1]) if not h5.empty else float(h["Close"].iloc[-1]),2)
        d["usdinr"]=curr
    except: d["usdinr"]=84
    try:
        stocks=["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","SBIN","WIPRO",
                "AXISBANK","LT","BAJFINANCE","MARUTI","TATAMOTORS","SUNPHARMA",
                "ONGC","NTPC","POWERGRID","TATASTEEL","HCLTECH","DIVISLAB","CIPLA"]
        batch=yf.download([s+".NS" for s in stocks],period="3d",
                         interval="1d",group_by="ticker",progress=False,threads=True)
        adv=0;dec=0
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
        d["advances"]=adv; d["declines"]=dec
        d["ad_ratio"]=round(adv/dec,2) if dec>0 else (3.0 if adv>0 else 1.0)
    except: d["advances"]=0; d["declines"]=0; d["ad_ratio"]=1.0
    # Simple bear score
    bs=0
    vix=d.get("vix",15); vix_pct=d.get("vix_pct",0)
    nifty_pct=d.get("nifty_pct",0); ad=d.get("ad_ratio",1.0)
    rsi=d.get("nifty_rsi",50)
    if vix>25: bs+=20
    elif vix>20: bs+=15
    elif vix>16: bs+=8
    if vix_pct>10: bs+=10
    elif vix_pct>5: bs+=6
    if nifty_pct<-2: bs+=20
    elif nifty_pct<-1.5: bs+=15
    elif nifty_pct<-1: bs+=10
    elif nifty_pct<-0.5: bs+=5
    if ad<0.3: bs+=20
    elif ad<0.6: bs+=15
    elif ad<0.8: bs+=10
    elif ad<1.0: bs+=5
    if rsi<30: bs+=15
    elif rsi<40: bs+=10
    elif rsi<50: bs+=5
    d["bear_score"]=min(bs,100)
    if bs>=80: d["bear_zone"]="EXTREME"
    elif bs>=65: d["bear_zone"]="DANGER"
    elif bs>=50: d["bear_zone"]="ALERT"
    elif bs>=30: d["bear_zone"]="CAUTION"
    else: d["bear_zone"]="CALM"
    # Fear-Greed (simplified proxy)
    fg=50+(nifty_pct*5)-(max(0,vix-15)*2)+(d.get("ad_ratio",1)-1)*15
    d["fear_greed"]=max(0,min(100,round(fg)))
    if fg<=20: d["fg_label"]="EXTREME FEAR"
    elif fg<=35: d["fg_label"]="FEAR"
    elif fg<=50: d["fg_label"]="MILD FEAR"
    elif fg<=65: d["fg_label"]="NEUTRAL"
    elif fg<=80: d["fg_label"]="GREED"
    else: d["fg_label"]="EXTREME GREED"
    return d

def get_market_emoji(score, label):
    if label in ["EXTREME FEAR","FEAR"]: return "🌧️"
    elif label == "MILD FEAR": return "🌦️"
    elif label == "NEUTRAL": return "⛅"
    elif label == "GREED": return "🌤️"
    else: return "☀️"

def generate_weather_report(report_type="pre_market"):
    """Generate complete weather report"""
    data = fetch_weather_data()
    key = load_key()
    ts = datetime.now().strftime("%d %b %Y %I:%M %p")
    date_str = datetime.now().strftime("%d %b %Y")
    emoji = get_market_emoji(data["fear_greed"], data["fg_label"])

    # AI summary
    ai_summary = ""
    if key:
        rtype = "pre-market opening briefing" if report_type=="pre_market" else "live market briefing after first 15 minutes"
        prompt = (f"BearIQ Market Weather Intelligence — {rtype}\n\n"
                 f"DATA:\n"
                 f"Nifty: {data['nifty']} ({'+' if data['nifty_pct']>=0 else ''}{data['nifty_pct']}%)\n"
                 f"VIX: {data['vix']} ({'+' if data['vix_pct']>=0 else ''}{data['vix_pct']}%)\n"
                 f"Fear-Greed: {data['fear_greed']}/100 ({data['fg_label']})\n"
                 f"Bear Score: {data['bear_score']}/100 ({data['bear_zone']})\n"
                 f"A/D Ratio: {data['ad_ratio']} ({data['advances']} adv / {data['declines']} dec)\n"
                 f"Gold: {data['gold']} ({'+' if data['gold_pct']>=0 else ''}{data['gold_pct']}%)\n"
                 f"USD/INR: {data['usdinr']}\n\n"
                 f"Write a 3-sentence market weather summary.\n"
                 f"Professional tone. No investment advice. No buy/sell recommendations.\n"
                 f"Just describe market conditions like a weather forecast.\n"
                 f"Example style: 'Markets showing cautious conditions as volatility builds...'\n"
                 f"End with one key level to watch today.")
        try:
            r=requests.post(GROQ_URL,
                headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
                json={"model":GROQ_MODEL,"messages":[{"role":"user","content":prompt}],
                      "temperature":0.6,"max_tokens":200},timeout=20)
            if r.status_code==200:
                ai_summary=r.json()["choices"][0]["message"]["content"].strip()
        except: ai_summary="Market intelligence data updated. Check dashboards for detailed analysis."

    # Fetch top market headlines
    try:
        news = fetch_market_news(5)
    except: news = []

    report = {
        "id": datetime.now().strftime("%d%m%H%M"),
        "date": date_str,
        "timestamp": ts,
        "type": report_type,
        "type_label": "Pre-Market" if report_type=="pre_market" else "Live Market",
        "data": data,
        "ai_summary": ai_summary,
        "news": news,
        "emoji": emoji,
        "sent": False,
        "sent_to": []
    }
    save_weather_report(report)
    return report

def should_send_report(report_type):
    """Check if report for today already sent"""
    reports = load_weather_reports()
    today = datetime.now().strftime("%d %b %Y")
    for r in reports:
        if r.get("date")==today and r.get("type")==report_type and r.get("sent"):
            return False
    return True

def send_email_report(report):
    """Send weather report via Gmail SMTP"""
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        # Get email config from secrets
        try:
            gmail_user = st.secrets.get("gmail_user","")
            gmail_pass = st.secrets.get("gmail_pass","")
        except:
            gmail_user = ""; gmail_pass = ""
        if not gmail_user or not gmail_pass:
            return False, "Email not configured"
        data = report["data"]
        users = load_users()
        active_users = [u for u in users.values()
                       if u.get("status")=="active" and u.get("email")
                       and u.get("username")!="ishan_admin"]
        if not active_users:
            return False, "No active users"
        type_label = report["type_label"]
        date_str = report["date"]
        emoji = report["emoji"]
        fg_label = data["fg_label"]
        nifty_sign = "+" if data["nifty_pct"]>=0 else ""
        vix_sign = "+" if data["vix_pct"]>=0 else ""
        # Build news section HTML
        news_items = report.get("news", [])
        news_html = ""
        if news_items:
            news_html = '<div style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:14px;margin-bottom:16px">'
            news_html += '<div style="color:#fbbf24;font-size:0.7rem;font-weight:800;margin-bottom:10px;letter-spacing:1px">📰 TOP MARKET HEADLINES</div>'
            for n in news_items:
                news_html += f'<div style="margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #33415544">'
                news_html += f'<div style="color:#e2e8f0;font-size:0.82rem;line-height:1.5">{n["title"]}</div>'
                news_html += f'<div style="color:#64748b;font-size:0.7rem;margin-top:2px">— {n["source"]}</div></div>'
            news_html += '</div>'
        html_body = f"""
        <div style="background:#070b14;padding:30px;font-family:Arial,sans-serif;max-width:500px;margin:0 auto;border-radius:12px">
            <div style="text-align:center;margin-bottom:24px">
                <div style="font-size:2rem;font-weight:900;color:#ff4444;letter-spacing:4px">BearIQ</div>
                <div style="color:#94a3b8;font-size:0.75rem;letter-spacing:2px">MARKET WEATHER INTELLIGENCE</div>
            </div>
            <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;padding:20px;margin-bottom:16px">
                <div style="color:#94a3b8;font-size:0.75rem;margin-bottom:6px">{type_label} Report — {date_str}</div>
                <div style="font-size:2.5rem;margin-bottom:8px">{emoji}</div>
                <div style="font-size:1.3rem;font-weight:800;color:#f1f5f9;margin-bottom:4px">{fg_label}</div>
                <div style="color:#94a3b8;font-size:0.85rem">Fear-Greed: {data['fear_greed']}/100</div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px">
                <div style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:12px;text-align:center">
                    <div style="color:#94a3b8;font-size:0.65rem">NIFTY</div>
                    <div style="color:{'#ff4444' if data['nifty_pct']<0 else '#00ff88'};font-weight:800;font-size:1.1rem">{data['nifty']}</div>
                    <div style="color:{'#ff4444' if data['nifty_pct']<0 else '#00ff88'};font-size:0.8rem">{nifty_sign}{data['nifty_pct']}%</div>
                </div>
                <div style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:12px;text-align:center">
                    <div style="color:#94a3b8;font-size:0.65rem">VIX</div>
                    <div style="color:{'#ff4444' if data['vix']>18 else '#ffdd00' if data['vix']>15 else '#00ff88'};font-weight:800;font-size:1.1rem">{data['vix']}</div>
                    <div style="color:#94a3b8;font-size:0.8rem">{vix_sign}{data['vix_pct']}%</div>
                </div>
                <div style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:12px;text-align:center">
                    <div style="color:#94a3b8;font-size:0.65rem">BEAR SCORE</div>
                    <div style="color:{'#ff4444' if data['bear_score']>=65 else '#ff8800' if data['bear_score']>=50 else '#ffdd00' if data['bear_score']>=30 else '#00ff88'};font-weight:800;font-size:1.1rem">{data['bear_score']}/100</div>
                    <div style="color:#94a3b8;font-size:0.8rem">{data['bear_zone']}</div>
                </div>
                <div style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:12px;text-align:center">
                    <div style="color:#94a3b8;font-size:0.65rem">A/D RATIO</div>
                    <div style="color:{'#ff4444' if data['ad_ratio']<0.8 else '#00ff88'};font-weight:800;font-size:1.1rem">{data['ad_ratio']}</div>
                    <div style="color:#94a3b8;font-size:0.8rem">{data['advances']} adv / {data['declines']} dec</div>
                </div>
            </div>
            <div style="background:#172554;border:1px solid #1e40af;border-left:3px solid #4488ff;border-radius:8px;padding:14px;margin-bottom:16px">
                <div style="color:#3388ff;font-size:0.7rem;font-weight:800;margin-bottom:6px">AI WEATHER SUMMARY</div>
                <div style="color:#ccddee;font-size:0.88rem;line-height:1.6">{report.get('ai_summary','Market data updated.')}</div>
            </div>
            {news_html}
            <div style="text-align:center;margin-top:20px">
                <a href="https://beariq.in" style="background:#ff4444;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:700;font-size:0.9rem">Open BearIQ →</a>
            </div>
            <div style="text-align:center;color:#64748b;font-size:0.72rem;margin-top:20px;border-top:1px solid #1a2840;padding-top:12px">
                BearIQ Market Weather Intelligence | beariq.in<br>For educational purposes only.
            </div>
        </div>
        """
        sent_to = []
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(gmail_user, gmail_pass)
        for user in active_users:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"BearIQ {emoji} {type_label} Weather — {date_str}"
            msg["From"] = f"BearIQ Intelligence <{gmail_user}>"
            msg["To"] = user["email"]
            msg.attach(MIMEText(html_body,"html"))
            try:
                server.sendmail(gmail_user, user["email"], msg.as_string())
                sent_to.append(user["email"])
            except: pass
        server.quit()
        # Mark as sent
        reports = load_weather_reports()
        for i,r in enumerate(reports):
            if r.get("id")==report["id"]:
                reports[i]["sent"]=True
                reports[i]["sent_to"]=sent_to
                break
        with open(WEATHER_FILE,"w") as f: json.dump(reports,f,indent=2)
        return True, f"Sent to {len(sent_to)} users"
    except Exception as e:
        return False, str(e)

# ── WEATHER REPORT PAGE ────────────────────────────────────────────
def render_weather_page(username):
    """Display weather reports inside BearIQ app"""
    st.markdown("<div style='font-size:1.6rem;font-weight:800;color:#f1f5f9;border-bottom:1px solid #334155;padding-bottom:12px;margin-bottom:20px'>🌤️ MARKET WEATHER REPORTS</div>", unsafe_allow_html=True)
    now = datetime.now()
    hour = now.hour; minute = now.minute
    is_market_day = now.weekday() < 5

    # Auto generate and show today's reports
    if is_market_day:
        # Pre-market check (after 8:45 AM)
        if hour >= 8 and (hour > 8 or minute >= 45):
            reports = load_weather_reports()
            today = now.strftime("%d %b %Y")
            has_pre = any(r.get("date")==today and r.get("type")=="pre_market" for r in reports)
            if not has_pre:
                with st.spinner("Generating pre-market weather report..."):
                    report = generate_weather_report("pre_market")
                    st.toast("📊 Pre-market report ready!", icon="✅")
        # Live market check (after 9:30 AM)
        if hour >= 9 and (hour > 9 or minute >= 30):
            reports = load_weather_reports()
            today = now.strftime("%d %b %Y")
            has_live = any(r.get("date")==today and r.get("type")=="live_market" for r in reports)
            if not has_live:
                with st.spinner("Generating live market weather report..."):
                    report = generate_weather_report("live_market")
                    st.toast("📊 Live market report ready!", icon="✅")

    # Show today's reports
    reports = load_weather_reports()
    today = now.strftime("%d %b %Y")
    today_reports = [r for r in reports if r.get("date")==today]
    today_reports.sort(key=lambda x: x.get("timestamp",""), reverse=True)

    if today_reports:
        st.markdown("<div style='font-size:0.82rem;font-weight:800;color:#3388cc;text-transform:uppercase;letter-spacing:3px;border-bottom:1px solid #334155;padding-bottom:8px;margin-bottom:14px'>TODAY'S REPORTS</div>", unsafe_allow_html=True)
        for report in today_reports:
            _render_report_card(report)
    else:
        st.markdown("<div style='background:#1e293b;border:1px solid #334155;border-radius:12px;padding:30px;text-align:center;color:#94a3b8'>Today's weather reports will appear here automatically at 8:45 AM and 9:30 AM.</div>", unsafe_allow_html=True)

    # Archive
    older = [r for r in reports if r.get("date")!=today]
    if older:
        st.markdown("<div style='font-size:0.82rem;font-weight:800;color:#3388cc;text-transform:uppercase;letter-spacing:3px;border-bottom:1px solid #334155;padding-bottom:8px;margin:20px 0 14px'>ARCHIVE</div>", unsafe_allow_html=True)
        with st.expander("View previous reports"):
            for report in reversed(older[-10:]):
                _render_report_card(report, compact=True)

def _render_report_card(report, compact=False):
    data = report.get("data",{})
    emoji = report.get("emoji","⛅")
    type_label = report.get("type_label","")
    ts = report.get("timestamp","")
    fg = data.get("fear_greed",50)
    fg_label = data.get("fg_label","NEUTRAL")
    bs = data.get("bear_score",0)
    bz = data.get("bear_zone","CALM")
    nifty = data.get("nifty",0)
    np_ = data.get("nifty_pct",0)
    vix = data.get("vix",15)
    vp_ = data.get("vix_pct",0)
    ad = data.get("ad_ratio",1.0)
    ai = report.get("ai_summary","")

    fg_clr = "#ff0000" if fg<=20 else "#ff4444" if fg<=35 else "#ff8800" if fg<=50 else "#ffdd00" if fg<=65 else "#00ff88"
    bs_clr = "#ff0000" if bs>=80 else "#ff4444" if bs>=65 else "#ff8800" if bs>=50 else "#ffdd00" if bs>=30 else "#00ff88"

    if compact:
        h=f"<div style='background:#1e293b;border:1px solid #334155;border-radius:10px;padding:12px 16px;margin-bottom:6px'>"
        h+=f"<div style='display:flex;justify-content:space-between'>"
        h+=f"<div><span style='font-size:1.2rem'>{emoji}</span> <span style='color:#f1f5f9;font-weight:700'>{type_label}</span> <span style='color:#94a3b8;font-size:0.78rem'>— {ts}</span></div>"
        h+=f"<div style='color:{fg_clr};font-weight:800'>{fg}/100 {fg_label}</div></div></div>"
    else:
        h=f"<div style='background:#1e293b;border:1px solid #334155;border-radius:14px;padding:20px;margin-bottom:14px'>"
        h+=f"<div style='display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px'>"
        h+=f"<div><div style='color:#94a3b8;font-size:0.72rem;margin-bottom:4px'>{type_label} — {ts}</div>"
        h+=f"<div style='font-size:2.5rem'>{emoji}</div>"
        h+=f"<div style='font-size:1.3rem;font-weight:900;color:{fg_clr};margin-top:4px'>{fg_label}</div>"
        h+=f"<div style='color:#94a3b8;font-size:0.78rem'>Fear-Greed: {fg}/100</div></div></div>"
        h+=f"<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px'>"
        for lb,v,vc in [("NIFTY",str(nifty)+"<br>"+("+" if np_>=0 else "")+str(np_)+"%","#ff4444" if np_<0 else "#00ff88"),
                        ("VIX",str(vix)+"<br>"+("+" if vp_>=0 else "")+str(vp_)+"%","#ff4444" if vix>18 else "#ffdd00" if vix>15 else "#00ff88"),
                        ("BEAR SCORE",str(bs)+"/100<br>"+bz,bs_clr),
                        ("A/D RATIO",str(ad)+"<br>"+str(data.get("advances",0))+" adv",("#ff4444" if ad<0.8 else "#00ff88"))]:
            h+=f"<div style='background:#0f172a;border-radius:8px;padding:8px;text-align:center'>"
            h+=f"<div style='color:#94a3b8;font-size:0.62rem'>{lb}</div>"
            h+=f"<div style='color:{vc};font-weight:800;font-size:0.82rem;margin-top:3px;line-height:1.4'>{v}</div></div>"
        h+="</div>"
        if ai:
            h+=f"<div style='background:#172554;border:1px solid #1e40af;border-left:3px solid #4488ff;border-radius:8px;padding:12px;margin-bottom:10px'>"
            h+=f"<div style='color:#3388ff;font-size:0.68rem;font-weight:800;margin-bottom:6px'>AI WEATHER SUMMARY</div>"
            h+=f"<div style='color:#ccddee;font-size:0.85rem;line-height:1.6'>{ai}</div></div>"
        # News section
        news_items = report.get("news", [])
        if news_items:
            h+=f"<div style='background:#1e293b;border:1px solid #334155;border-left:3px solid #fbbf24;border-radius:8px;padding:12px'>"
            h+=f"<div style='color:#fbbf24;font-size:0.68rem;font-weight:800;margin-bottom:8px;letter-spacing:1px'>📰 TOP MARKET HEADLINES</div>"
            for n in news_items:
                link = n.get("link","")
                title = n.get("title","")
                source = n.get("source","")
                if link:
                    h+=f"<div style='margin-bottom:8px'><a href='{link}' target='_blank' style='color:#e2e8f0;font-size:0.82rem;text-decoration:none;line-height:1.5'>{title}</a>"
                else:
                    h+=f"<div style='margin-bottom:8px'><span style='color:#e2e8f0;font-size:0.82rem;line-height:1.5'>{title}</span>"
                h+=f"<div style='color:#64748b;font-size:0.7rem;margin-top:1px'>— {source}</div></div>"
            h+="</div>"
        h+="</div>"
    st.markdown(h, unsafe_allow_html=True)
