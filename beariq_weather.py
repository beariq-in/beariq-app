"""
BearIQ Market Weather Intelligence — Morning Outlook Engine v2
Single daily report at 8:45 AM IST
Institutional-grade market intelligence for retail investors
"""
import json, os, requests, traceback
from datetime import datetime, timedelta
import yfinance as yf
import streamlit as st

BASE = os.path.dirname(os.path.abspath(__file__))
WEATHER_FILE = os.path.join(BASE, "data", "weather_reports.json")
USERS_FILE = os.path.join(BASE, "data", "users.json")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

# ── UTILITIES ──────────────────────────────────────────────────────
def ensure_data_dir():
    os.makedirs(os.path.join(BASE, "data"), exist_ok=True)

def load_key():
    for p in [os.path.join(BASE, "config.txt"),
              os.path.join(BASE, ".streamlit", "secrets.toml"), "config.txt"]:
        if os.path.exists(p):
            content = open(p).read().strip()
            if "groq_api_key" in content:
                for line in content.split("\n"):
                    if "groq_api_key" in line:
                        return line.split("=",1)[1].strip().strip('"').strip("'")
            elif content and not content.startswith("["):
                return content
    try: return st.secrets.get("groq_api_key", "")
    except: return ""

def load_weather_reports():
    ensure_data_dir()
    if os.path.exists(WEATHER_FILE):
        try:
            with open(WEATHER_FILE, "r") as f: return json.load(f)
        except: return []
    return []

def save_weather_report(report):
    ensure_data_dir()
    reports = load_weather_reports()
    reports.append(report)
    reports = reports[-180:]
    with open(WEATHER_FILE, "w") as f: json.dump(reports, f, indent=2)

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

# ── MARKET NEWS (RSS — headlines only, copyright safe) ─────────────
@st.cache_data(ttl=900)
def fetch_market_news(max_items=5):
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
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            if r.status_code != 200: continue
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:3]:
                title = item.find("title")
                link = item.find("link")
                if title is not None and title.text:
                    t = title.text.strip()
                    skip = ["buy","sell","target price","multibagger","stock pick","stocks to","top picks"]
                    if any(w in t.lower() for w in skip): continue
                    headlines.append({"title": t[:150], "source": source,
                                     "link": link.text.strip() if link is not None and link.text else ""})
        except: continue
    seen = set(); unique = []
    for h in headlines:
        key = h["title"][:50].lower()
        if key not in seen: seen.add(key); unique.append(h)
    return unique[:max_items]

# ── INDIA MARKET DATA ──────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch_india_data():
    d = {}
    # Nifty
    try:
        t = yf.Ticker("^NSEI"); h = t.history(period="30d", interval="1d")
        h5 = t.history(period="1d", interval="5m")
        curr = round(float(h5["Close"].iloc[-1]) if not h5.empty else float(h["Close"].iloc[-1]), 2)
        prev = float(h["Close"].iloc[-2]) if len(h) > 1 else curr
        d["nifty"] = curr; d["nifty_pct"] = round(((curr - prev) / prev) * 100, 2)
        c = h["Close"]
        if len(c) >= 14:
            delta = c.diff(); gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss; d["nifty_rsi"] = round(float((100 - (100 / (1 + rs))).iloc[-1]), 1)
        else: d["nifty_rsi"] = 50
    except: d["nifty"] = 0; d["nifty_pct"] = 0; d["nifty_rsi"] = 50
    # BankNifty
    try:
        t = yf.Ticker("^NSEBANK"); h = t.history(period="5d", interval="1d")
        h5 = t.history(period="1d", interval="5m")
        curr = round(float(h5["Close"].iloc[-1]) if not h5.empty else float(h["Close"].iloc[-1]), 2)
        prev = float(h["Close"].iloc[-2]) if len(h) > 1 else curr
        d["banknifty"] = curr; d["banknifty_pct"] = round(((curr - prev) / prev) * 100, 2)
    except: d["banknifty"] = 0; d["banknifty_pct"] = 0
    # India VIX
    try:
        t = yf.Ticker("^INDIAVIX"); h = t.history(period="30d", interval="1d")
        h5 = t.history(period="1d", interval="5m")
        curr = round(float(h5["Close"].iloc[-1]) if not h5.empty else float(h["Close"].iloc[-1]), 2)
        prev = float(h["Close"].iloc[-2]) if len(h) > 1 else curr
        d["vix"] = curr; d["vix_pct"] = round(((curr - prev) / prev) * 100, 2)
        d["vix_ma20"] = round(float(h["Close"].rolling(20).mean().iloc[-1]), 2) if len(h) >= 20 else curr
    except: d["vix"] = 15; d["vix_pct"] = 0; d["vix_ma20"] = 15
    # Breadth (A/D from 20 major stocks for speed)
    try:
        stocks = ["RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","SBIN","WIPRO",
                  "AXISBANK","LT","BAJFINANCE","MARUTI","SUNPHARMA",
                  "ONGC","NTPC","POWERGRID","TATASTEEL","HCLTECH","DIVISLAB","CIPLA","NESTLEIND"]
        batch = yf.download([s+".NS" for s in stocks], period="3d",
                           interval="1d", group_by="ticker", progress=False, threads=True)
        adv = 0; dec = 0
        for sym in stocks:
            try:
                df = batch[sym+".NS"] if sym+".NS" in batch.columns.get_level_values(0) else None
                if df is None or df.empty: continue
                c = df["Close"].dropna()
                if len(c) < 2: continue
                p = ((c.iloc[-1] - c.iloc[-2]) / c.iloc[-2]) * 100
                if p > 0.25: adv += 1
                elif p < -0.25: dec += 1
            except: pass
        d["advances"] = adv; d["declines"] = dec
        d["ad_ratio"] = round(adv / dec, 2) if dec > 0 else (3.0 if adv > 0 else 1.0)
    except: d["advances"] = 0; d["declines"] = 0; d["ad_ratio"] = 1.0
    return d

# ── GLOBAL MARKET DATA ─────────────────────────────────────────────
@st.cache_data(ttl=600)
def fetch_global_data():
    g = {}
    tickers = {
        "dow": ("^DJI", "Dow Jones"),
        "sp500": ("^GSPC", "S&P 500"),
        "nasdaq": ("^IXIC", "Nasdaq"),
        "nikkei": ("^N225", "Nikkei 225"),
        "hangseng": ("^HSI", "Hang Seng"),
        "crude": ("CL=F", "Crude Oil"),
        "gold": ("GC=F", "Gold"),
        "dxy": ("DX-Y.NYB", "Dollar Index"),
        "usdinr": ("USDINR=X", "USD/INR"),
    }
    for key, (ticker, name) in tickers.items():
        try:
            t = yf.Ticker(ticker)
            h = t.history(period="5d", interval="1d")
            if h.empty: continue
            c = h["Close"].dropna()
            if len(c) < 2: continue
            curr = round(float(c.iloc[-1]), 2)
            prev = round(float(c.iloc[-2]), 2)
            pct = round(((curr - prev) / prev) * 100, 2)
            g[key] = {"value": curr, "pct": pct, "name": name}
        except: pass
    return g

# ── SECTOR PERFORMANCE ─────────────────────────────────────────────
@st.cache_data(ttl=600)
def fetch_sector_data():
    sectors = {}
    sector_tickers = {
        "Bank": "^NSEBANK", "IT": "^CNXIT", "Pharma": "^CNXPHARMA",
        "Auto": "^CNXAUTO", "Metal": "^CNXMETAL", "FMCG": "^CNXFMCG",
        "Energy": "^CNXENERGY", "Realty": "^CNXREALTY",
    }
    for name, ticker in sector_tickers.items():
        try:
            t = yf.Ticker(ticker)
            h = t.history(period="5d", interval="1d")
            if h.empty: continue
            c = h["Close"].dropna()
            if len(c) < 2: continue
            curr = round(float(c.iloc[-1]), 2)
            prev = round(float(c.iloc[-2]), 2)
            pct = round(((curr - prev) / prev) * 100, 2)
            sectors[name] = {"value": curr, "pct": pct}
        except: pass
    return sectors

# ── BEAR SCORE + FEAR-GREED CALCULATION ────────────────────────────
def calculate_scores(india, global_data):
    vix = india.get("vix", 15); vix_pct = india.get("vix_pct", 0)
    nifty_pct = india.get("nifty_pct", 0); ad = india.get("ad_ratio", 1.0)
    rsi = india.get("nifty_rsi", 50)
    # Bear Score
    bs = 0
    if vix > 25: bs += 20
    elif vix > 20: bs += 15
    elif vix > 16: bs += 8
    if vix_pct > 10: bs += 10
    elif vix_pct > 5: bs += 6
    if nifty_pct < -2: bs += 20
    elif nifty_pct < -1.5: bs += 15
    elif nifty_pct < -1: bs += 10
    elif nifty_pct < -0.5: bs += 5
    if ad < 0.3: bs += 20
    elif ad < 0.6: bs += 15
    elif ad < 0.8: bs += 10
    elif ad < 1.0: bs += 5
    if rsi < 30: bs += 15
    elif rsi < 40: bs += 10
    elif rsi < 50: bs += 5
    bs = min(bs, 100)
    if bs >= 80: bz = "EXTREME"
    elif bs >= 65: bz = "DANGER"
    elif bs >= 50: bz = "ALERT"
    elif bs >= 30: bz = "CAUTION"
    else: bz = "CALM"
    # Fear-Greed
    fg = 50 + (nifty_pct * 5) - (max(0, vix - 15) * 2) + (ad - 1) * 15
    fg = max(0, min(100, round(fg)))
    if fg <= 20: fgl = "EXTREME FEAR"
    elif fg <= 35: fgl = "FEAR"
    elif fg <= 50: fgl = "MILD FEAR"
    elif fg <= 65: fgl = "NEUTRAL"
    elif fg <= 80: fgl = "GREED"
    else: fgl = "EXTREME GREED"
    # Regime (simplified for report)
    if bs >= 65 and vix > 20: regime = "PANIC"
    elif bs >= 50 and vix > 18: regime = "TRENDING BEAR"
    elif fg >= 80 and vix < 14: regime = "EUPHORIC"
    elif fg >= 65 and vix < 16: regime = "TRENDING BULL"
    elif vix < 12 and abs(nifty_pct) < 0.3: regime = "COMPRESSION"
    elif vix > 18 and abs(nifty_pct) > 1: regime = "VOLATILE RANGE"
    else: regime = "TRANSITIONAL"
    # Risk Level
    if bs >= 65: risk = "HIGH"
    elif bs >= 40: risk = "MODERATE"
    elif bs >= 20: risk = "LOW"
    else: risk = "MINIMAL"
    # Warning signals count
    warnings = 0; warning_list = []
    if vix > 20: warnings += 1; warning_list.append("VIX elevated above 20")
    if vix_pct > 8: warnings += 1; warning_list.append("VIX spike detected")
    if nifty_pct < -1: warnings += 1; warning_list.append("Nifty decline exceeds 1%")
    if ad < 0.6: warnings += 1; warning_list.append("Weak market breadth")
    if rsi < 35: warnings += 1; warning_list.append("RSI approaching oversold")
    dow = global_data.get("dow", {})
    if dow and dow.get("pct", 0) < -1: warnings += 1; warning_list.append("Dow Jones closed weak")
    return {
        "bear_score": bs, "bear_zone": bz, "fear_greed": fg, "fg_label": fgl,
        "regime": regime, "risk": risk, "warnings": warnings, "warning_list": warning_list
    }

# ── CONFIDENCE SCORE (REAL FORMULA) ────────────────────────────────
def calculate_confidence(scores, india, global_data, sectors):
    """
    BearIQ Signal Alignment Score
    Measures how many signals agree on market reading
    NOT prediction accuracy — signal consensus measure
    """
    total = 0; max_score = 100
    fg = scores["fear_greed"]; bs = scores["bear_score"]
    regime = scores["regime"]; risk = scores["risk"]
    vix = india.get("vix", 15); ad = india.get("ad_ratio", 1.0)

    # 1. Fear-Greed vs Bear Score alignment (20 pts)
    # Both bearish or both bullish = aligned
    fg_bear = fg < 45; bs_bear = bs > 35
    fg_bull = fg > 55; bs_bull = bs < 25
    if (fg_bear and bs_bear) or (fg_bull and bs_bull): total += 20
    elif abs(fg - (100 - bs)) < 25: total += 12
    else: total += 5

    # 2. Regime stability (20 pts)
    # Clear regime = high confidence; Transitional = lower
    if regime in ("PANIC", "EUPHORIC", "TRENDING BEAR", "TRENDING BULL"): total += 20
    elif regime in ("COMPRESSION", "VOLATILE RANGE"): total += 12
    else: total += 6  # TRANSITIONAL

    # 3. Breadth confirmation (20 pts)
    # Strong breadth + clear direction = aligned
    if ad > 1.5 and fg > 55: total += 20  # Broad rally + bullish sentiment
    elif ad < 0.6 and fg < 45: total += 20  # Broad decline + bearish sentiment
    elif ad > 1.2 or ad < 0.7: total += 14  # Clear breadth direction
    else: total += 7  # Mixed breadth

    # 4. VIX behavior (15 pts)
    # VIX confirming sentiment
    vix_ma = india.get("vix_ma20", 15)
    if vix > vix_ma and fg < 45: total += 15  # VIX up + fear = aligned
    elif vix < vix_ma and fg > 55: total += 15  # VIX down + greed = aligned
    elif abs(vix - vix_ma) < 1: total += 10  # Neutral VIX
    else: total += 5  # Conflicting

    # 5. Warning signal clarity (15 pts)
    w = scores["warnings"]
    if w == 0 and fg > 55: total += 15  # No warnings + bullish = clear
    elif w >= 3 and fg < 40: total += 15  # Many warnings + bearish = clear
    elif w <= 1: total += 10
    else: total += 6

    # 6. Global cue alignment (10 pts)
    dow = global_data.get("dow", {}).get("pct", 0)
    sp = global_data.get("sp500", {}).get("pct", 0)
    nifty_pct = india.get("nifty_pct", 0)
    global_dir = (dow + sp) / 2 if dow and sp else 0
    if (global_dir > 0.3 and nifty_pct > 0) or (global_dir < -0.3 and nifty_pct < 0): total += 10
    elif abs(global_dir) < 0.3: total += 7
    else: total += 3

    return min(total, max_score)

# ── MARKET WEATHER EMOJI ───────────────────────────────────────────
def get_weather(fg):
    if fg <= 20: return "⛈️", "Storm"
    elif fg <= 35: return "🌧️", "Rain"
    elif fg <= 50: return "🌦️", "Mixed"
    elif fg <= 65: return "⛅", "Partly Cloudy"
    elif fg <= 80: return "🌤️", "Mostly Clear"
    else: return "☀️", "Clear Skies"

# ── GENERATE MORNING OUTLOOK ───────────────────────────────────────
def generate_weather_report(report_type="morning_outlook"):
    india = fetch_india_data()
    global_data = fetch_global_data()
    sectors = fetch_sector_data()
    scores = calculate_scores(india, global_data)
    confidence = calculate_confidence(scores, india, global_data, sectors)
    news = []
    try: news = fetch_market_news(5)
    except: pass

    emoji, weather_word = get_weather(scores["fear_greed"])
    ts = datetime.now().strftime("%d %b %Y %I:%M %p")
    date_str = datetime.now().strftime("%d %b %Y")

    # Sort sectors
    sorted_sectors = sorted(sectors.items(), key=lambda x: x[1]["pct"], reverse=True)
    top_sectors = sorted_sectors[:3] if sorted_sectors else []
    bottom_sectors = sorted_sectors[-3:] if len(sorted_sectors) >= 3 else []

    # Build data package for AI
    data_block = f"""BEARIQ INTERNAL SIGNALS:
Fear-Greed Score: {scores['fear_greed']}/100 ({scores['fg_label']})
Market Regime: {scores['regime']}
Bear Score: {scores['bear_score']}/100 ({scores['bear_zone']})
Risk Level: {scores['risk']}
Active Warning Signals: {scores['warnings']} — {', '.join(scores['warning_list']) if scores['warning_list'] else 'None'}
Signal Confidence: {confidence}%
A/D Ratio: {india.get('ad_ratio',1.0)} ({india.get('advances',0)} advancing / {india.get('declines',0)} declining)
Nifty RSI(14): {india.get('nifty_rsi',50)}

INDIA MARKET DATA (Previous Close):
Nifty 50: {india.get('nifty',0)} ({'+' if india.get('nifty_pct',0)>=0 else ''}{india.get('nifty_pct',0)}%)
BankNifty: {india.get('banknifty',0)} ({'+' if india.get('banknifty_pct',0)>=0 else ''}{india.get('banknifty_pct',0)}%)
India VIX: {india.get('vix',15)} ({'+' if india.get('vix_pct',0)>=0 else ''}{india.get('vix_pct',0)}%) | 20-day MA: {india.get('vix_ma20',15)}"""

    # Global data block
    g_lines = []
    for key in ["dow","sp500","nasdaq","nikkei","hangseng"]:
        gd = global_data.get(key)
        if gd: g_lines.append(f"{gd['name']}: {gd['value']:,.0f} ({'+' if gd['pct']>=0 else ''}{gd['pct']}%)")
    for key in ["crude","gold","dxy","usdinr"]:
        gd = global_data.get(key)
        if gd: g_lines.append(f"{gd['name']}: {gd['value']:,.2f} ({'+' if gd['pct']>=0 else ''}{gd['pct']}%)")

    data_block += "\n\nGLOBAL MARKETS (Latest Close):\n" + "\n".join(g_lines) if g_lines else ""

    # Sector block
    if sorted_sectors:
        s_lines = [f"{name}: {'+' if data['pct']>=0 else ''}{data['pct']}%" for name, data in sorted_sectors]
        data_block += "\n\nSECTOR PERFORMANCE:\n" + "\n".join(s_lines)

    # News block
    if news:
        n_lines = [f"• {n['title']} — {n['source']}" for n in news[:5]]
        data_block += "\n\nTOP HEADLINES:\n" + "\n".join(n_lines)

    # ── THE AI PROMPT ──────────────────────────────────────────────
    ai_prompt = f"""You are the official BearIQ Market Intelligence Engine. Generate the daily BearIQ Morning Outlook report.

IMPORTANT RULES:
- BearIQ is NOT a stock tip platform
- BearIQ is NOT a prediction platform
- BearIQ is a market weather and intelligence platform for Indian retail investors
- NEVER predict Nifty direction or levels
- NEVER recommend stocks to buy or sell
- NEVER guarantee returns or market direction
- BearIQ signals have HIGHEST priority — news should support conclusions, not create them
- NEVER fabricate data. If data is missing, skip that point
- Keep total reading time under 60 seconds
- Sound professional, intelligent, trustworthy
- Make user feel more informed than reading multiple financial sites
- Every report should feel like a premium institutional morning briefing simplified for retail investors

DATA:
{data_block}

Generate the report in EXACTLY this structure. Use plain text, no markdown headers, no bullet symbols. Use arrows (→) for sub-points. Keep each section tight.

SECTION 1: MARKET WEATHER
One-line summary combining: market weather ({weather_word}), regime ({scores['regime']}), fear-greed ({scores['fear_greed']}), risk ({scores['risk']}), confidence ({confidence}%), active warnings ({scores['warnings']}).
Then 1-2 sentence summary of today's environment.

SECTION 2: WHAT CHANGED
Compare yesterday vs today for: fear-greed, regime, breadth, warning signals, risk level. Note which changed and briefly explain why these changes matter. If no significant changes, say conditions are steady.

SECTION 3: GLOBAL PULSE
Summarize US markets, Asian markets, crude oil, dollar index in 3-4 lines. Focus only on what is relevant to today's Indian market environment. Avoid information overload.

SECTION 4: KEY HEADLINES
Pick only 3 most important headlines from the data. For each, add one line: "Why it matters:" with brief relevance to today's market.

SECTION 5: MARKET BEHAVIOR OUTLOOK (Most important section)
Do NOT predict Nifty. Instead describe the most likely market BEHAVIOR using BearIQ signals. Cover: expected volatility, trend quality, participation breadth, momentum quality. End with confidence percentage.

SECTION 6: BEARIQ VIEW
Final conclusion in exactly 3 sentences. Combine internal BearIQ signals + market data + global context + news. This is the takeaway the user remembers all day."""

    # Call Groq AI
    ai_summary = ""
    key = load_key()
    if key:
        try:
            r = requests.post(GROQ_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": GROQ_MODEL, "messages": [{"role": "user", "content": ai_prompt}],
                      "temperature": 0.5, "max_tokens": 800}, timeout=30)
            if r.status_code == 200:
                ai_summary = r.json()["choices"][0]["message"]["content"].strip()
        except: ai_summary = ""
    if not ai_summary:
        ai_summary = f"Market Weather: {weather_word} | Regime: {scores['regime']} | Risk: {scores['risk']} | Confidence: {confidence}%. Market intelligence data updated — check BearIQ dashboards for detailed analysis."

    report = {
        "id": datetime.now().strftime("%d%m%H%M"),
        "date": date_str, "timestamp": ts, "type": "morning_outlook",
        "type_label": "Morning Outlook",
        "india": india, "global": global_data, "sectors": sectors,
        "scores": scores, "confidence": confidence,
        "data": {**india, **scores, "fear_greed": scores["fear_greed"],
                 "fg_label": scores["fg_label"], "bear_score": scores["bear_score"],
                 "bear_zone": scores["bear_zone"]},
        "news": news, "ai_summary": ai_summary, "emoji": emoji,
        "weather_word": weather_word, "sent": False, "sent_to": []
    }
    save_weather_report(report)
    return report

# ── EMAIL SENDER ───────────────────────────────────────────────────
def send_email_report(report):
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        try:
            gmail_user = st.secrets.get("gmail_user", "")
            gmail_pass = st.secrets.get("gmail_pass", "")
        except: gmail_user = ""; gmail_pass = ""
        if not gmail_user or not gmail_pass: return False, "Email not configured"
        users = load_users()
        active_users = [u for u in users.values()
                       if u.get("status") == "active" and u.get("email")]
        if not active_users: return False, "No active users"

        scores = report.get("scores", {})
        india = report.get("india", {})
        global_data = report.get("global", {})
        conf = report.get("confidence", 0)
        emoji = report.get("emoji", "⛅")
        date_str = report.get("date", "")
        ai_text = report.get("ai_summary", "")
        news = report.get("news", [])
        fg = scores.get("fear_greed", 50); fgl = scores.get("fg_label", "NEUTRAL")
        bs = scores.get("bear_score", 0); bz = scores.get("bear_zone", "CALM")
        regime = scores.get("regime", "TRANSITIONAL")
        risk = scores.get("risk", "MODERATE")
        warns = scores.get("warnings", 0)
        np_ = india.get("nifty_pct", 0); vp_ = india.get("vix_pct", 0)

        # Build global section
        global_html = ""
        for key in ["dow","sp500","nasdaq","nikkei","hangseng"]:
            gd = global_data.get(key)
            if gd:
                gc = "#5dffa0" if gd["pct"] >= 0 else "#ff7a7a"
                global_html += f"<div style='display:flex;justify-content:space-between;padding:4px 0'><span style='color:#94a3b8'>{gd['name']}</span><span style='color:{gc};font-weight:700'>{'+' if gd['pct']>=0 else ''}{gd['pct']}%</span></div>"

        # Build news section
        news_html = ""
        if news:
            for n in news[:3]:
                news_html += f"<div style='padding:8px 0;border-bottom:1px solid #1f253344'><div style='color:#e2e8f0;font-size:0.85rem'>{n['title']}</div><div style='color:#64748b;font-size:0.7rem;margin-top:2px'>— {n['source']}</div></div>"

        html_body = f"""
        <div style="background:#07090f;padding:30px 24px;font-family:'Inter',Arial,sans-serif;max-width:520px;margin:0 auto;border-radius:16px">
            <div style="text-align:center;margin-bottom:24px">
                <div style="font-size:2rem;font-weight:900;color:#ff4444;letter-spacing:4px">BearIQ</div>
                <div style="color:#5b6478;font-size:0.72rem;letter-spacing:2px">MORNING OUTLOOK · {date_str}</div>
            </div>
            <div style="background:linear-gradient(160deg,#12161f 0%,#0d1019 100%);border:1px solid #1f2533;border-radius:20px;padding:24px;margin-bottom:14px;text-align:center">
                <div style="font-size:3rem">{emoji}</div>
                <div style="font-size:2.8rem;font-weight:800;color:#f5f7fb;margin-top:6px">{fg}<span style="font-size:1.2rem;color:#5b6478">/100</span></div>
                <div style="color:{'#ff7a7a' if fg<=35 else '#ffc25d' if fg<=50 else '#5dffa0'};font-weight:700;font-size:1.1rem;margin-top:4px">{fgl}</div>
                <div style="display:flex;justify-content:center;gap:20px;margin-top:16px;padding-top:14px;border-top:1px solid #ffffff0d">
                    <div><div style="color:#5b6478;font-size:0.6rem">REGIME</div><div style="color:#e7eaf0;font-weight:700;font-size:0.82rem">{regime}</div></div>
                    <div><div style="color:#5b6478;font-size:0.6rem">RISK</div><div style="color:{'#ff7a7a' if risk=='HIGH' else '#ffc25d' if risk=='MODERATE' else '#5dffa0'};font-weight:700;font-size:0.82rem">{risk}</div></div>
                    <div><div style="color:#5b6478;font-size:0.6rem">CONFIDENCE</div><div style="color:#7da4ff;font-weight:700;font-size:0.82rem">{conf}%</div></div>
                    <div><div style="color:#5b6478;font-size:0.6rem">WARNINGS</div><div style="color:{'#ff7a7a' if warns>=3 else '#ffc25d' if warns>=1 else '#5dffa0'};font-weight:700;font-size:0.82rem">{warns}</div></div>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:14px">
                <div style="background:#12161f;border:1px solid #1f2533;border-radius:12px;padding:12px;text-align:center">
                    <div style="color:#5b6478;font-size:0.58rem">NIFTY</div>
                    <div style="color:{'#ff7a7a' if np_<0 else '#5dffa0'};font-weight:800;font-size:0.95rem">{india.get('nifty',0):,.0f}</div>
                    <div style="color:{'#ff7a7a' if np_<0 else '#5dffa0'};font-size:0.72rem">{'+' if np_>=0 else ''}{np_}%</div>
                </div>
                <div style="background:#12161f;border:1px solid #1f2533;border-radius:12px;padding:12px;text-align:center">
                    <div style="color:#5b6478;font-size:0.58rem">VIX</div>
                    <div style="color:{'#ff7a7a' if india.get('vix',15)>18 else '#5dffa0'};font-weight:800;font-size:0.95rem">{india.get('vix',15)}</div>
                    <div style="color:#94a3b8;font-size:0.72rem">{'+' if vp_>=0 else ''}{vp_}%</div>
                </div>
                <div style="background:#12161f;border:1px solid #1f2533;border-radius:12px;padding:12px;text-align:center">
                    <div style="color:#5b6478;font-size:0.58rem">BEAR SCORE</div>
                    <div style="color:{'#ff7a7a' if bs>=50 else '#ffc25d' if bs>=30 else '#5dffa0'};font-weight:800;font-size:0.95rem">{bs}/100</div>
                    <div style="color:#94a3b8;font-size:0.72rem">{bz}</div>
                </div>
            </div>
            {'<div style="background:#12161f;border:1px solid #1f2533;border-radius:12px;padding:14px;margin-bottom:14px"><div style="color:#5b6478;font-size:0.62rem;font-weight:700;margin-bottom:8px">GLOBAL MARKETS</div>' + global_html + '</div>' if global_html else ''}
            <div style="background:#172554;border:1px solid #1e40af;border-left:3px solid #7da4ff;border-radius:12px;padding:16px;margin-bottom:14px">
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:10px"><div style="width:6px;height:6px;background:#7da4ff;border-radius:50%"></div><span style="color:#7da4ff;font-size:0.65rem;font-weight:700;letter-spacing:1.5px">BEARIQ INTELLIGENCE</span></div>
                <div style="color:#d3d9e5;font-size:0.85rem;line-height:1.7;white-space:pre-line">{ai_text}</div>
            </div>
            {'<div style="background:#12161f;border:1px solid #1f2533;border-radius:12px;padding:14px;margin-bottom:14px"><div style="color:#fbbf24;font-size:0.62rem;font-weight:700;margin-bottom:8px;letter-spacing:1px">KEY HEADLINES</div>' + news_html + '</div>' if news_html else ''}
            <div style="text-align:center;margin-top:18px">
                <a href="https://beariq.streamlit.app" style="background:#dc2626;color:#fff;padding:12px 28px;border-radius:10px;text-decoration:none;font-weight:700;font-size:0.88rem">Open BearIQ Live →</a>
            </div>
            <div style="text-align:center;color:#3d4456;font-size:0.68rem;margin-top:18px;padding-top:12px;border-top:1px solid #14181f">
                BearIQ Market Weather Intelligence · beariq.in<br>For educational purposes only
            </div>
        </div>
        """
        sent_to = []
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(gmail_user, gmail_pass)
        for user in active_users:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"BearIQ {emoji} Morning Outlook — {date_str} | {fgl}"
            msg["From"] = f"BearIQ Intelligence <{gmail_user}>"
            msg["To"] = user["email"]
            msg.attach(MIMEText(html_body, "html"))
            try:
                server.sendmail(gmail_user, user["email"], msg.as_string())
                sent_to.append(user["email"])
            except: pass
        server.quit()
        reports = load_weather_reports()
        for i, r in enumerate(reports):
            if r.get("id") == report["id"]:
                reports[i]["sent"] = True; reports[i]["sent_to"] = sent_to; break
        with open(WEATHER_FILE, "w") as f: json.dump(reports, f, indent=2)
        return True, f"Sent to {len(sent_to)} users"
    except Exception as e:
        return False, str(e)

# ── IN-APP WEATHER REPORT PAGE ─────────────────────────────────────
def render_weather_page(username):
    st.markdown("<div style='font-size:1.6rem;font-weight:800;color:#f1f5f9;border-bottom:1px solid #1f2533;padding-bottom:12px;margin-bottom:20px'>Morning Outlook Reports</div>", unsafe_allow_html=True)
    now = datetime.now()
    today = now.strftime("%d %b %Y")
    is_market_day = now.weekday() < 5

    if is_market_day and now.hour >= 8 and (now.hour > 8 or now.minute >= 45):
        reports = load_weather_reports()
        has_today = any(r.get("date") == today and r.get("type") == "morning_outlook" for r in reports)
        if not has_today:
            with st.spinner("Generating BearIQ Morning Outlook..."):
                generate_weather_report()
                st.toast("Morning Outlook ready!", icon="✅")

    reports = load_weather_reports()
    today_reports = [r for r in reports if r.get("date") == today]
    today_reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    if today_reports:
        st.markdown("<div class='section-title'>TODAY'S OUTLOOK</div>", unsafe_allow_html=True)
        for report in today_reports:
            _render_report_card(report)
    else:
        st.markdown("<div style='background:#12161f;border:1px solid #1f2533;border-radius:16px;padding:30px;text-align:center;color:#8a93a8'>Morning Outlook generates automatically at 8:45 AM on market days.</div>", unsafe_allow_html=True)

    older = [r for r in reports if r.get("date") != today]
    if older:
        st.markdown("<div class='section-title'>ARCHIVE</div>", unsafe_allow_html=True)
        with st.expander("View previous reports"):
            for report in reversed(older[-10:]):
                _render_report_card(report, compact=True)

def _render_report_card(report, compact=False):
    scores = report.get("scores", report.get("data", {}))
    india = report.get("india", report.get("data", {}))
    global_data = report.get("global", {})
    conf = report.get("confidence", 0)
    emoji = report.get("emoji", "⛅")
    ts = report.get("timestamp", "")
    fg = scores.get("fear_greed", 50); fgl = scores.get("fg_label", "NEUTRAL")
    bs = scores.get("bear_score", 0); bz = scores.get("bear_zone", "CALM")
    regime = scores.get("regime", "TRANSITIONAL")
    risk = scores.get("risk", "MODERATE")
    warns = scores.get("warnings", 0)
    ai = report.get("ai_summary", "")
    news = report.get("news", [])
    np_ = india.get("nifty_pct", 0)
    vix = india.get("vix", 15); vp_ = india.get("vix_pct", 0)
    ad = india.get("ad_ratio", 1.0)
    fg_clr = "#ff7a7a" if fg <= 35 else "#ffc25d" if fg <= 50 else "#5dffa0"

    if compact:
        h = f"<div style='background:#12161f;border:1px solid #1f2533;border-radius:12px;padding:12px 16px;margin-bottom:6px'>"
        h += f"<div style='display:flex;justify-content:space-between;align-items:center'>"
        h += f"<div><span style='font-size:1.2rem'>{emoji}</span> <span style='color:#f1f5f9;font-weight:700'>{report.get('type_label','Outlook')}</span> <span style='color:#5b6478;font-size:0.78rem'>— {ts}</span></div>"
        h += f"<div style='color:{fg_clr};font-weight:800'>{fg}/100 {fgl}</div></div></div>"
        st.markdown(h, unsafe_allow_html=True)
        return

    # Full card
    h = f"<div style='background:#12161f;border:1px solid #1f2533;border-radius:20px;padding:22px;margin-bottom:14px'>"
    h += f"<div style='color:#5b6478;font-size:0.72rem;margin-bottom:8px'>Morning Outlook — {ts}</div>"
    # Hero
    h += f"<div style='text-align:center;margin-bottom:16px'>"
    h += f"<div style='font-size:2.5rem'>{emoji}</div>"
    h += f"<div style='font-size:2rem;font-weight:800;color:#f5f7fb;margin-top:4px'>{fg}<span style='font-size:1rem;color:#5b6478'>/100</span></div>"
    h += f"<div style='color:{fg_clr};font-weight:700;font-size:1.1rem'>{fgl}</div>"
    h += f"<div style='display:flex;justify-content:center;gap:16px;margin-top:12px;color:#94a3b8;font-size:0.75rem'>"
    h += f"<span>Regime: <b style='color:#e7eaf0'>{regime}</b></span>"
    h += f"<span>Risk: <b style='color:{'#ff7a7a' if risk=='HIGH' else '#ffc25d' if risk=='MODERATE' else '#5dffa0'}'>{risk}</b></span>"
    h += f"<span>Confidence: <b style='color:#7da4ff'>{conf}%</b></span></div></div>"
    # Metrics strip
    h += f"<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:14px'>"
    for lb, v, vc in [("NIFTY", f"{india.get('nifty',0):,.0f}<br>{'+' if np_>=0 else ''}{np_}%", "#ff7a7a" if np_<0 else "#5dffa0"),
                      ("VIX", f"{vix}<br>{'+' if vp_>=0 else ''}{vp_}%", "#ff7a7a" if vix>18 else "#5dffa0"),
                      ("BEAR SCORE", f"{bs}/100<br>{bz}", "#ff7a7a" if bs>=50 else "#5dffa0"),
                      ("BREADTH", f"{ad}<br>{india.get('advances',0)} adv", "#ff7a7a" if ad<0.8 else "#5dffa0")]:
        h += f"<div style='background:#0d1019;border-radius:10px;padding:8px;text-align:center'>"
        h += f"<div style='color:#5b6478;font-size:0.58rem'>{lb}</div>"
        h += f"<div style='color:{vc};font-weight:700;font-size:0.78rem;margin-top:3px;line-height:1.4'>{v}</div></div>"
    h += "</div>"
    # Global
    if global_data:
        h += "<div style='margin-bottom:12px'><div style='color:#5b6478;font-size:0.62rem;font-weight:700;margin-bottom:6px'>GLOBAL MARKETS</div>"
        for key in ["dow","sp500","nasdaq","nikkei","hangseng","crude","dxy"]:
            gd = global_data.get(key)
            if gd:
                gc = "#5dffa0" if gd["pct"] >= 0 else "#ff7a7a"
                h += f"<div style='display:flex;justify-content:space-between;padding:3px 0'><span style='color:#94a3b8;font-size:0.78rem'>{gd['name']}</span><span style='color:{gc};font-weight:700;font-size:0.78rem'>{'+' if gd['pct']>=0 else ''}{gd['pct']}%</span></div>"
        h += "</div>"
    # AI Summary
    if ai:
        h += f"<div style='background:#172554;border:1px solid #1e40af;border-left:3px solid #7da4ff;border-radius:10px;padding:14px;margin-bottom:10px'>"
        h += f"<div style='display:flex;align-items:center;gap:6px;margin-bottom:8px'><div style='width:6px;height:6px;background:#7da4ff;border-radius:50%'></div><span style='color:#7da4ff;font-size:0.62rem;font-weight:700;letter-spacing:1.5px'>BEARIQ INTELLIGENCE</span></div>"
        h += f"<div style='color:#d3d9e5;font-size:0.82rem;line-height:1.7;white-space:pre-line'>{ai}</div></div>"
    # News
    if news:
        h += f"<div style='border-left:3px solid #fbbf24;border-radius:10px;padding:12px;background:#12161f'>"
        h += f"<div style='color:#fbbf24;font-size:0.62rem;font-weight:700;margin-bottom:6px;letter-spacing:1px'>KEY HEADLINES</div>"
        for n in news[:3]:
            link = n.get("link",""); title = n.get("title",""); source = n.get("source","")
            if link:
                h += f"<div style='margin-bottom:6px'><a href='{link}' target='_blank' style='color:#e2e8f0;font-size:0.78rem;text-decoration:none'>{title}</a>"
            else:
                h += f"<div style='margin-bottom:6px'><span style='color:#e2e8f0;font-size:0.78rem'>{title}</span>"
            h += f"<div style='color:#5b6478;font-size:0.65rem'>— {source}</div></div>"
        h += "</div>"
    h += "</div>"
    st.markdown(h, unsafe_allow_html=True)
