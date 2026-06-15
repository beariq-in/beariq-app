"""
BearIQ Market Weather Intelligence
Premium Dashboard — Apple Weather x CRED x TradingView
"""
import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(
    page_title="BearIQ — Market Weather Intelligence",
    page_icon="🐻",
    layout="wide",
    initial_sidebar_state="collapsed"
)

from beariq_auth import (is_logged_in, get_current_user, is_admin,
                          render_login, render_navbar, render_admin_users, logout)
from beariq_analytics import track, render_analytics_page
from beariq_weather import (render_weather_page, load_weather_reports,
                             fetch_weather_data, fetch_market_news)

import yfinance as yf
import requests
from datetime import datetime, timedelta

# ── PREMIUM DESIGN SYSTEM ─────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
html,body,[class*="css"]{font-family:'Inter',-apple-system,sans-serif!important}
.stApp{background:#07090f;color:#e7eaf0}
[data-testid="stSidebar"]{background-color:#0a0d15;border-right:1px solid #1a1f2e}
[data-testid="stHeader"]{background:transparent}
.block-container{padding-top:1rem;max-width:680px!important;margin:0 auto}
.section-title{font-size:0.72rem;font-weight:700;color:#5b6478;text-transform:uppercase;
    letter-spacing:2px;margin:28px 0 12px 4px}
.stButton>button{background:#161b28;color:#aab4cc;border:1px solid #232a3d;
    border-radius:14px;font-weight:600;padding:12px;transition:all 0.2s;width:100%}
.stButton>button:hover{background:#1d2436;border-color:#2f3850}
[data-testid="collapsedControl"]{display:block!important;visibility:visible!important;color:#f87171!important}
h1,h2,h3{color:#f1f5f9!important}
hr{border-color:#1a1f2e!important}
</style>""", unsafe_allow_html=True)

# ── AUTH GATE ─────────────────────────────────────────────────────
if not is_logged_in():
    render_login()
    st.stop()

username = get_current_user()
admin = is_admin()
now = datetime.now()
today = now.strftime("%d %b %Y")

# ── SIDEBAR NAV ───────────────────────────────────────────────────
render_navbar()
with st.sidebar:
    st.markdown("<div style='font-size:0.68rem;color:#5b6478;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px'>NAVIGATION</div>", unsafe_allow_html=True)
    pages = ["🏠 Home", "🌡️ Fear-Greed", "🎯 Market Regime",
             "⚠️ Early Warning", "📊 Market Breadth", "🌤️ Weather Reports"]
    if admin:
        pages += ["📈 Analytics", "👤 Users"]
    page = st.radio("", pages, label_visibility="collapsed")

# ── DATA HELPERS ──────────────────────────────────────────────────
def get_yesterday_report():
    """Get last report from a previous day for comparison"""
    reports = load_weather_reports()
    prev = [r for r in reports if r.get("date") != today]
    return prev[-1] if prev else None

@st.cache_data(ttl=3600)
def fetch_fii_dii():
    """
    FII/DII cash market activity.
    Method 1: NSE official API (most reliable)
    Method 2: Moneycontrol table parse
    Always degrades gracefully to None.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/json, text/html",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/"
    }
    # ── METHOD 1: NSE official FII/DII API ──
    try:
        s = requests.Session()
        s.headers.update(headers)
        # Warm up session (NSE needs cookies)
        s.get("https://www.nseindia.com", timeout=8)
        r = s.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=8)
        if r.status_code == 200:
            data = r.json()
            fii_net = None; dii_net = None
            for row in data:
                cat = str(row.get("category","")).upper()
                net = row.get("netValue") or row.get("net")
                if net is None: continue
                net = float(str(net).replace(",",""))
                if "FII" in cat or "FPI" in cat: fii_net = net
                elif "DII" in cat: dii_net = net
            if fii_net is not None and dii_net is not None:
                return {"fii_net": round(fii_net,1), "dii_net": round(dii_net,1),
                        "source": "NSE"}
    except: pass
    # ── METHOD 2: Moneycontrol parse ──
    try:
        import re
        r = requests.get(
            "https://www.moneycontrol.com/stocks/marketstats/fii_dii_activity/index.php",
            timeout=10, headers=headers)
        if r.status_code == 200:
            text = r.text
            # Look for table rows containing FII/FPI and DII with 3 numbers each
            rows = re.findall(r'(FII|FPI|DII)[^<]*</t[dh]>\s*<td[^>]*>\s*(-?[\d,]+\.?\d*)\s*</td>\s*<td[^>]*>\s*(-?[\d,]+\.?\d*)\s*</td>\s*<td[^>]*>\s*(-?[\d,]+\.?\d*)', text)
            fii_net=None; dii_net=None
            for cat,buy,sell,net in rows:
                n=float(net.replace(",",""))
                if cat in ("FII","FPI") and fii_net is None: fii_net=n
                elif cat=="DII" and dii_net is None: dii_net=n
            if fii_net is not None and dii_net is not None:
                return {"fii_net": round(fii_net,1), "dii_net": round(dii_net,1),
                        "source": "Moneycontrol"}
    except: pass
    return None

# ════════════════════════════════════════════════════════════════
# HOME — PREMIUM DASHBOARD
# ════════════════════════════════════════════════════════════════
if "Home" in page:
    track(username, "home")

    with st.spinner(""):
        d = fetch_weather_data()

    fg = d.get("fear_greed", 50)
    fg_label = d.get("fg_label", "NEUTRAL")
    bs = d.get("bear_score", 0)
    bz = d.get("bear_zone", "CALM")
    nifty = d.get("nifty", 0)
    np_ = d.get("nifty_pct", 0)
    vix = d.get("vix", 15)
    vp_ = d.get("vix_pct", 0)
    ad = d.get("ad_ratio", 1.0)
    bn = d.get("banknifty", 0)
    bnp = d.get("banknifty_pct", 0)

    # ── 1. HERO CARD — Apple Weather Style ──────────────────────
    # Gradient + emoji by condition
    if fg <= 20:
        grad = "linear-gradient(160deg,#2d1115 0%,#1a0a0d 60%,#0a0608 100%)"
        accent = "#ff5d5d"; emoji = "⛈️"; condition = "Extreme Fear"
        sub = "Heavy selling pressure across the market"
    elif fg <= 35:
        grad = "linear-gradient(160deg,#2b1a10 0%,#1a100a 60%,#0a0705 100%)"
        accent = "#ff8c5d"; emoji = "🌧️"; condition = "Fear"
        sub = "Caution in the air — fear building"
    elif fg <= 50:
        grad = "linear-gradient(160deg,#252017 0%,#16130d 60%,#0a0906 100%)"
        accent = "#ffc25d"; emoji = "🌦️"; condition = "Mild Fear"
        sub = "Mixed skies — slight unease in the market"
    elif fg <= 65:
        grad = "linear-gradient(160deg,#141a26 0%,#0d1118 60%,#070a0f 100%)"
        accent = "#7da4ff"; emoji = "⛅"; condition = "Neutral"
        sub = "Calm conditions — market in balance"
    elif fg <= 80:
        grad = "linear-gradient(160deg,#10241a 0%,#0a1710 60%,#060d09 100%)"
        accent = "#5dff9f"; emoji = "🌤️"; condition = "Greed"
        sub = "Optimism rising — confidence in the market"
    else:
        grad = "linear-gradient(160deg,#0d2a1c 0%,#081a11 60%,#050f0a 100%)"
        accent = "#3dffa0"; emoji = "☀️"; condition = "Extreme Greed"
        sub = "Peak optimism — market running hot"

    greeting = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 17 else "Good evening"

    st.markdown(f"""
    <div style='background:{grad};border:1px solid {accent}22;border-radius:28px;
                padding:36px 32px 30px;margin-bottom:14px;position:relative;overflow:hidden'>
        <div style='color:#8a93a8;font-size:0.8rem;font-weight:500;margin-bottom:2px'>{greeting}</div>
        <div style='color:#5b6478;font-size:0.72rem;margin-bottom:24px'>{now.strftime('%A, %d %B')} · India Markets</div>
        <div style='display:flex;align-items:center;justify-content:space-between'>
            <div>
                <div style='font-size:4.6rem;font-weight:800;color:#f5f7fb;line-height:1;letter-spacing:-3px'>{fg}<span style='font-size:1.6rem;font-weight:600;color:#5b6478'>/100</span></div>
                <div style='font-size:1.3rem;font-weight:700;color:{accent};margin-top:8px'>{condition}</div>
                <div style='color:#8a93a8;font-size:0.82rem;margin-top:4px'>{sub}</div>
            </div>
            <div style='font-size:5rem;line-height:1'>{emoji}</div>
        </div>
        <div style='display:flex;gap:24px;margin-top:28px;padding-top:20px;border-top:1px solid #ffffff0d'>
            <div><div style='color:#5b6478;font-size:0.65rem;font-weight:600;letter-spacing:1px'>NIFTY</div>
                <div style='color:{"#ff7a7a" if np_<0 else "#5dffa0"};font-weight:700;font-size:0.95rem;margin-top:2px'>{nifty:,.0f} <span style='font-size:0.78rem'>{'+' if np_>=0 else ''}{np_}%</span></div></div>
            <div><div style='color:#5b6478;font-size:0.65rem;font-weight:600;letter-spacing:1px'>VIX</div>
                <div style='color:{"#ff7a7a" if vix>18 else "#ffc25d" if vix>15 else "#5dffa0"};font-weight:700;font-size:0.95rem;margin-top:2px'>{vix} <span style='font-size:0.78rem'>{'+' if vp_>=0 else ''}{vp_}%</span></div></div>
            <div><div style='color:#5b6478;font-size:0.65rem;font-weight:600;letter-spacing:1px'>BEAR SCORE</div>
                <div style='color:{"#ff7a7a" if bs>=65 else "#ffc25d" if bs>=40 else "#5dffa0"};font-weight:700;font-size:0.95rem;margin-top:2px'>{bs} <span style='font-size:0.78rem'>{bz}</span></div></div>
            <div><div style='color:#5b6478;font-size:0.65rem;font-weight:600;letter-spacing:1px'>BREADTH</div>
                <div style='color:{"#ff7a7a" if ad<0.8 else "#5dffa0"};font-weight:700;font-size:0.95rem;margin-top:2px'>{ad}</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 2. WHAT CHANGED SINCE YESTERDAY ──────────────────────────
    yest = get_yesterday_report()
    if yest:
        yd = yest.get("data", {})
        changes = []
        y_fg = yd.get("fear_greed", fg)
        y_bs = yd.get("bear_score", bs)
        y_vix = yd.get("vix", vix)
        y_ad = yd.get("ad_ratio", ad)
        if abs(fg - y_fg) >= 1:
            arrow = "↑" if fg > y_fg else "↓"
            clr = "#5dffa0" if fg > y_fg else "#ff7a7a"
            changes.append(("Sentiment", f"{y_fg} → {fg}", arrow, clr))
        if abs(bs - y_bs) >= 1:
            arrow = "↑" if bs > y_bs else "↓"
            clr = "#ff7a7a" if bs > y_bs else "#5dffa0"
            changes.append(("Bear Score", f"{y_bs} → {bs}", arrow, clr))
        if abs(vix - y_vix) >= 0.2:
            arrow = "↑" if vix > y_vix else "↓"
            clr = "#ff7a7a" if vix > y_vix else "#5dffa0"
            changes.append(("Volatility", f"{y_vix} → {vix}", arrow, clr))
        if abs(ad - y_ad) >= 0.1:
            arrow = "↑" if ad > y_ad else "↓"
            clr = "#5dffa0" if ad > y_ad else "#ff7a7a"
            changes.append(("Breadth", f"{y_ad} → {ad}", arrow, clr))

        st.markdown("<div class='section-title'>What changed since yesterday</div>", unsafe_allow_html=True)
        if changes:
            chips = ""
            for name, val, arrow, clr in changes:
                chips += f"""<div style='background:#12161f;border:1px solid #1f2533;border-radius:16px;
                    padding:14px 16px;flex:1;min-width:140px'>
                    <div style='color:#5b6478;font-size:0.68rem;font-weight:600'>{name}</div>
                    <div style='display:flex;align-items:center;gap:6px;margin-top:6px'>
                        <span style='color:#e7eaf0;font-weight:700;font-size:0.9rem'>{val}</span>
                        <span style='color:{clr};font-weight:800;font-size:1rem'>{arrow}</span>
                    </div></div>"""
            st.markdown(f"<div style='display:flex;gap:10px;flex-wrap:wrap'>{chips}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='background:#12161f;border:1px solid #1f2533;border-radius:16px;padding:16px;color:#8a93a8;font-size:0.85rem'>Market conditions steady — no significant changes from yesterday.</div>", unsafe_allow_html=True)

    # ── 3. BEARIQ AI MORNING BRIEF ────────────────────────────────
    reports = load_weather_reports()
    today_reports = [r for r in reports if r.get("date") == today]
    latest = today_reports[-1] if today_reports else None
    ai_text = latest.get("ai_summary", "") if latest else ""

    st.markdown("<div class='section-title'>BearIQ morning brief</div>", unsafe_allow_html=True)
    if ai_text:
        st.markdown(f"""
        <div style='background:linear-gradient(145deg,#10141f 0%,#0d1019 100%);
                    border:1px solid #1f2533;border-radius:20px;padding:22px 24px'>
            <div style='display:flex;align-items:center;gap:8px;margin-bottom:12px'>
                <div style='width:8px;height:8px;background:#7da4ff;border-radius:50%'></div>
                <span style='color:#7da4ff;font-size:0.7rem;font-weight:700;letter-spacing:1.5px'>AI INTELLIGENCE</span>
            </div>
            <div style='color:#d3d9e5;font-size:0.92rem;line-height:1.75'>{ai_text}</div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown("<div style='background:#12161f;border:1px solid #1f2533;border-radius:16px;padding:18px;color:#8a93a8;font-size:0.85rem'>Morning brief generates automatically at 8:45 AM on market days. Visit Weather Reports to generate now.</div>", unsafe_allow_html=True)

    # ── 4. FII / DII ACTIVITY ─────────────────────────────────────
    st.markdown("<div class='section-title'>Institutional activity</div>", unsafe_allow_html=True)
    fii = fetch_fii_dii()
    if fii:
        fii_net = fii["fii_net"]; dii_net = fii["dii_net"]
        fii_clr = "#5dffa0" if fii_net >= 0 else "#ff7a7a"
        dii_clr = "#5dffa0" if dii_net >= 0 else "#ff7a7a"
        fii_lbl = "Net Buyers" if fii_net >= 0 else "Net Sellers"
        dii_lbl = "Net Buyers" if dii_net >= 0 else "Net Sellers"
        st.markdown(f"""
        <div style='display:flex;gap:10px'>
            <div style='background:#12161f;border:1px solid #1f2533;border-radius:18px;padding:18px 20px;flex:1'>
                <div style='color:#5b6478;font-size:0.68rem;font-weight:600;letter-spacing:1px'>FII (Foreign)</div>
                <div style='color:{fii_clr};font-weight:800;font-size:1.3rem;margin-top:6px'>{'+' if fii_net>=0 else ''}{fii_net:,.0f} Cr</div>
                <div style='color:#8a93a8;font-size:0.72rem;margin-top:2px'>{fii_lbl}</div>
            </div>
            <div style='background:#12161f;border:1px solid #1f2533;border-radius:18px;padding:18px 20px;flex:1'>
                <div style='color:#5b6478;font-size:0.68rem;font-weight:600;letter-spacing:1px'>DII (Domestic)</div>
                <div style='color:{dii_clr};font-weight:800;font-size:1.3rem;margin-top:6px'>{'+' if dii_net>=0 else ''}{dii_net:,.0f} Cr</div>
                <div style='color:#8a93a8;font-size:0.72rem;margin-top:2px'>{dii_lbl}</div>
            </div>
        </div>
        <div style='color:#3d4456;font-size:0.65rem;margin-top:6px;padding-left:4px'>Source: {fii.get('source','NSE')} · Previous session cash market data</div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""<div style='background:#12161f;border:1px solid #1f2533;border-radius:16px;padding:16px;display:flex;justify-content:space-between;align-items:center'>
            <span style='color:#8a93a8;font-size:0.85rem'>FII/DII data updating…</span>
            <a href='https://www.moneycontrol.com/stocks/marketstats/fii_dii_activity/index.php' target='_blank' style='color:#7da4ff;font-size:0.78rem;text-decoration:none'>View on Moneycontrol →</a>
        </div>""", unsafe_allow_html=True)

    # ── 5. IMPORTANT HEADLINES ────────────────────────────────────
    st.markdown("<div class='section-title'>Important headlines</div>", unsafe_allow_html=True)
    try:
        news = fetch_market_news(5)
    except: news = []
    if news:
        news_html = "<div style='background:#12161f;border:1px solid #1f2533;border-radius:20px;padding:8px 20px'>"
        for i, n in enumerate(news):
            border = "border-bottom:1px solid #1a1f2e;" if i < len(news)-1 else ""
            link = n.get("link","")
            title = n.get("title","")
            source = n.get("source","")
            if link:
                news_html += f"""<div style='padding:14px 0;{border}'>
                    <a href='{link}' target='_blank' style='color:#d3d9e5;font-size:0.88rem;text-decoration:none;line-height:1.5;font-weight:500'>{title}</a>
                    <div style='color:#5b6478;font-size:0.7rem;margin-top:3px'>{source}</div></div>"""
            else:
                news_html += f"""<div style='padding:14px 0;{border}'>
                    <span style='color:#d3d9e5;font-size:0.88rem;line-height:1.5;font-weight:500'>{title}</span>
                    <div style='color:#5b6478;font-size:0.7rem;margin-top:3px'>{source}</div></div>"""
        news_html += "</div>"
        st.markdown(news_html, unsafe_allow_html=True)
    else:
        st.markdown("<div style='background:#12161f;border:1px solid #1f2533;border-radius:16px;padding:16px;color:#8a93a8;font-size:0.85rem'>Headlines loading…</div>", unsafe_allow_html=True)

    # ── 6. QUICK ACCESS TO SIGNALS ────────────────────────────────
    st.markdown("<div class='section-title'>Intelligence engines</div>", unsafe_allow_html=True)
    engines = [
        ("🌡️","Fear-Greed Index","Live sentiment gauge","#ff8c5d"),
        ("🎯","Market Regime","Structure detection","#b07dff"),
        ("⚠️","Early Warning","Bear Score monitor","#ff7a7a"),
        ("📊","Market Breadth","A/D participation","#7da4ff"),
    ]
    eng_html = "<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px'>"
    for icon, name, desc, clr in engines:
        eng_html += f"""<div style='background:#12161f;border:1px solid #1f2533;border-radius:18px;
            padding:18px;transition:all 0.2s'>
            <div style='font-size:1.6rem;margin-bottom:8px'>{icon}</div>
            <div style='color:#e7eaf0;font-weight:700;font-size:0.88rem'>{name}</div>
            <div style='color:#5b6478;font-size:0.72rem;margin-top:2px'>{desc}</div>
            <div style='color:{clr};font-size:0.7rem;font-weight:600;margin-top:10px'>Open from sidebar →</div>
        </div>"""
    eng_html += "</div>"
    st.markdown(eng_html, unsafe_allow_html=True)

    # Footer
    st.markdown(f"""<div style='text-align:center;color:#3d4456;font-size:0.68rem;
        margin-top:32px;padding-top:16px;border-top:1px solid #14181f'>
        BearIQ Market Weather Intelligence · beariq.in<br>For educational purposes only</div>""",
        unsafe_allow_html=True)

# ── OTHER PAGES (unchanged) ───────────────────────────────────────
elif "Fear-Greed" in page:
    track(username, "fear_greed")
    try:
        exec(open(os.path.join(os.path.dirname(__file__),"beariq_feargreed.py"),encoding="utf-8").read())
    except Exception as e:
        st.error(f"Fear-Greed module error: {e}")

elif "Regime" in page:
    track(username, "regime")
    try:
        exec(open(os.path.join(os.path.dirname(__file__),"beariq_regime.py"),encoding="utf-8").read())
    except Exception as e:
        st.error(f"Regime module error: {e}")

elif "Early Warning" in page:
    track(username, "early_warning")
    try:
        exec(open(os.path.join(os.path.dirname(__file__),"beariq_early_warning.py"),encoding="utf-8").read())
    except Exception as e:
        st.error(f"Early Warning module error: {e}")

elif "Breadth" in page:
    track(username, "breadth")
    try:
        exec(open(os.path.join(os.path.dirname(__file__),"beariq_breadth.py"),encoding="utf-8").read())
    except Exception as e:
        st.error(f"Breadth module error: {e}")

elif "Weather" in page:
    track(username, "weather")
    render_weather_page(username)

elif "Analytics" in page and admin:
    track(username, "admin")
    render_analytics_page()

elif "Users" in page and admin:
    track(username, "admin")
    render_admin_users()
