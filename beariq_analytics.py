"""
BearIQ Analytics Engine
Auto-tracks every user action silently
Admin page shows complete picture
"""
import json, os
from datetime import datetime
import streamlit as st

BASE = os.path.dirname(os.path.abspath(__file__))
ANALYTICS_FILE = os.path.join(BASE, "data", "analytics.json")

DASHBOARD_NAMES = {
    "home":        "Home",
    "fear_greed":  "Fear-Greed Index",
    "regime":      "Market Regime",
    "early_warning":"Early Warning",
    "breadth":     "Market Breadth",
    "weather":     "Weather Reports",
    "admin":       "Admin Panel"
}

def ensure_data_dir():
    os.makedirs(os.path.join(BASE,"data"), exist_ok=True)

def load_analytics():
    ensure_data_dir()
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE,"r") as f: return json.load(f)
        except: return {}
    return {}

def save_analytics(data):
    ensure_data_dir()
    with open(ANALYTICS_FILE,"w") as f: json.dump(data,f,indent=2)

def track(username, dashboard):
    """
    Auto-track dashboard visit
    Called silently on every page load
    """
    if not username: return
    try:
        data = load_analytics()
        today = datetime.now().strftime("%d %b %Y")
        ts = datetime.now().strftime("%I:%M %p")
        key = f"{username}_{today}"
        if key not in data:
            data[key] = {
                "username": username,
                "date": today,
                "events": [],
                "dashboards_viewed": [],
                "session_start": ts,
                "last_active": ts
            }
        # Add event
        event = {
            "time": ts,
            "dashboard": dashboard,
            "dashboard_name": DASHBOARD_NAMES.get(dashboard, dashboard)
        }
        data[key]["events"].append(event)
        data[key]["last_active"] = ts
        # Update dashboard list
        if dashboard not in data[key]["dashboards_viewed"]:
            data[key]["dashboards_viewed"].append(dashboard)
        save_analytics(data)
    except: pass  # Never crash main app due to analytics

def get_today_stats():
    """Stats for today"""
    data = load_analytics()
    today = datetime.now().strftime("%d %b %Y")
    today_data = {k:v for k,v in data.items() if v.get("date")==today}
    active_users = len(today_data)
    total_events = sum(len(v.get("events",[])) for v in today_data.values())
    # Dashboard popularity
    dash_counts = {}
    for session in today_data.values():
        for event in session.get("events",[]):
            d = event.get("dashboard_name","Unknown")
            dash_counts[d] = dash_counts.get(d,0) + 1
    return {
        "active_users": active_users,
        "total_events": total_events,
        "dashboard_counts": dict(sorted(dash_counts.items(),key=lambda x:x[1],reverse=True)),
        "sessions": today_data
    }

def get_all_stats():
    """All time stats"""
    data = load_analytics()
    total_sessions = len(data)
    unique_users = len(set(v.get("username") for v in data.values()))
    # User activity summary
    user_summary = {}
    for session in data.values():
        u = session.get("username")
        if u not in user_summary:
            user_summary[u] = {"sessions":0,"last_active":"","total_events":0}
        user_summary[u]["sessions"] += 1
        user_summary[u]["total_events"] += len(session.get("events",[]))
        user_summary[u]["last_active"] = session.get("last_active","")
    return {
        "total_sessions": total_sessions,
        "unique_users": unique_users,
        "user_summary": user_summary
    }

# ── ADMIN ANALYTICS PAGE ──────────────────────────────────────────
def render_analytics_page():
    st.markdown("<div style='font-size:1.4rem;font-weight:800;color:#e0e0e0;margin-bottom:20px'>📊 USER ANALYTICS</div>", unsafe_allow_html=True)

    today_stats = get_today_stats()
    all_stats = get_all_stats()

    # Today summary
    st.markdown("<div style='font-size:0.82rem;font-weight:800;color:#3388cc;text-transform:uppercase;letter-spacing:3px;border-bottom:1px solid #1a2840;padding-bottom:8px;margin-bottom:14px'>TODAY</div>", unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    with c1: st.metric("Active Users", today_stats["active_users"])
    with c2: st.metric("Total Events", today_stats["total_events"])
    with c3: st.metric("All Time Users", all_stats["unique_users"])
    with c4: st.metric("All Time Sessions", all_stats["total_sessions"])

    # Dashboard popularity
    if today_stats["dashboard_counts"]:
        st.markdown("<div style='font-size:0.82rem;font-weight:800;color:#3388cc;text-transform:uppercase;letter-spacing:3px;border-bottom:1px solid #1a2840;padding-bottom:8px;margin:20px 0 14px'>DASHBOARD POPULARITY TODAY</div>", unsafe_allow_html=True)
        total_events = sum(today_stats["dashboard_counts"].values())
        for dash, count in today_stats["dashboard_counts"].items():
            pct = round((count/total_events)*100) if total_events>0 else 0
            bar_w = pct
            h = f"<div style='background:#0d1626;border:1px solid #1a2840;border-radius:8px;padding:10px 14px;margin-bottom:6px'>"
            h += f"<div style='display:flex;justify-content:space-between;margin-bottom:4px'>"
            h += f"<span style='color:#e0e0e0;font-weight:700;font-size:0.88rem'>{dash}</span>"
            h += f"<span style='color:#4488ff;font-weight:800'>{count} views ({pct}%)</span></div>"
            h += f"<div style='background:#0a0e1a;border-radius:3px;height:5px'>"
            h += f"<div style='background:#4488ff;width:{bar_w}%;height:5px;border-radius:3px'></div></div></div>"
            st.markdown(h, unsafe_allow_html=True)

    # Today's active users
    if today_stats["sessions"]:
        st.markdown("<div style='font-size:0.82rem;font-weight:800;color:#3388cc;text-transform:uppercase;letter-spacing:3px;border-bottom:1px solid #1a2840;padding-bottom:8px;margin:20px 0 14px'>ACTIVE USERS TODAY</div>", unsafe_allow_html=True)
        for key, session in today_stats["sessions"].items():
            uname = session.get("username","")
            events = session.get("events",[])
            dashes = ", ".join(set(e.get("dashboard_name","") for e in events))
            first = events[0]["time"] if events else "—"
            last = session.get("last_active","—")
            h = f"<div style='background:#0d1626;border:1px solid #1a2840;border-left:3px solid #00ff88;border-radius:8px;padding:10px 16px;margin-bottom:6px'>"
            h += f"<div style='display:flex;justify-content:space-between'>"
            h += f"<div><span style='color:#e0e0e0;font-weight:700'>@{uname}</span>"
            h += f"<div style='color:#445566;font-size:0.75rem;margin-top:2px'>Viewed: {dashes}</div>"
            h += f"<div style='color:#445566;font-size:0.75rem'>First: {first} | Last active: {last}</div></div>"
            h += f"<div style='color:#00ff88;font-weight:800'>{len(events)} events</div></div></div>"
            st.markdown(h, unsafe_allow_html=True)

    # All time user summary
    st.markdown("<div style='font-size:0.82rem;font-weight:800;color:#3388cc;text-transform:uppercase;letter-spacing:3px;border-bottom:1px solid #1a2840;padding-bottom:8px;margin:20px 0 14px'>ALL TIME USER ACTIVITY</div>", unsafe_allow_html=True)
    for uname, summary in sorted(all_stats["user_summary"].items(), key=lambda x: x[1]["sessions"], reverse=True):
        if uname == "ishan_admin": continue
        h = f"<div style='background:#0d1626;border:1px solid #1a2840;border-radius:8px;padding:10px 16px;margin-bottom:6px'>"
        h += f"<div style='display:flex;justify-content:space-between'>"
        h += f"<div><span style='color:#e0e0e0;font-weight:700'>@{uname}</span>"
        h += f"<div style='color:#445566;font-size:0.75rem;margin-top:2px'>Total events: {summary['total_events']} | Last active: {summary['last_active']}</div></div>"
        h += f"<div style='text-align:right'><div style='color:#4488ff;font-weight:800'>{summary['sessions']} sessions</div></div></div></div>"
        st.markdown(h, unsafe_allow_html=True)
