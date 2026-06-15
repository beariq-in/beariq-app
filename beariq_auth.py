"""
BearIQ Authentication Module
Handles: Login, Register, Session, Admin, Auto-login
"""
import streamlit as st
import hashlib, json, os
from datetime import datetime, timedelta

# ── PATHS ──────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE, "data", "users.json")
INVITE_CODE = "BEARIQ2026"
ADMIN_USERNAME = "ishan_admin"
SESSION_DAYS = 30

# ── STORAGE ────────────────────────────────────────────────────
def ensure_data_dir():
    os.makedirs(os.path.join(BASE, "data"), exist_ok=True)

def load_users():
    ensure_data_dir()
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                return json.load(f)
        except: return {}
    return {}

def save_users(users):
    ensure_data_dir()
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

# ── SECURITY ────────────────────────────────────────────────────
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

# ── SESSION MANAGEMENT ──────────────────────────────────────────
def get_session_key(username):
    """Generate unique session key"""
    seed = username + "beariq_secret_2026"
    return hashlib.sha256(seed.encode()).hexdigest()[:32]

def save_session(username):
    """Save auto-login session to streamlit state"""
    st.session_state["beariq_user"] = username
    st.session_state["beariq_session_key"] = get_session_key(username)
    st.session_state["beariq_login_time"] = datetime.now().isoformat()
    # Update last seen in users
    users = load_users()
    if username in users:
        users[username]["last_login"] = datetime.now().strftime("%d %b %Y %I:%M %p")
        users[username]["login_count"] = users[username].get("login_count", 0) + 1
        save_users(users)

def is_logged_in():
    """Check if user has valid session"""
    if "beariq_user" not in st.session_state:
        return False
    if "beariq_session_key" not in st.session_state:
        return False
    username = st.session_state["beariq_user"]
    expected_key = get_session_key(username)
    if st.session_state["beariq_session_key"] != expected_key:
        return False
    # Check session not expired
    login_time = st.session_state.get("beariq_login_time")
    if login_time:
        try:
            lt = datetime.fromisoformat(login_time)
            if (datetime.now() - lt).days >= SESSION_DAYS:
                logout()
                return False
        except: pass
    # Verify user still active
    users = load_users()
    user = users.get(username, {})
    if user.get("status") != "active":
        logout()
        return False
    return True

def get_current_user():
    return st.session_state.get("beariq_user", None)

def is_admin():
    return get_current_user() == ADMIN_USERNAME

def logout():
    for key in ["beariq_user","beariq_session_key","beariq_login_time"]:
        if key in st.session_state:
            del st.session_state[key]

# ── UI STYLES ────────────────────────────────────────────────────
AUTH_CSS = """
<style>
.stApp{background-color:#070b14;color:#e0e0e0}
[data-testid="stSidebar"]{display:none}
.auth-container{
    max-width:420px;margin:0 auto;padding:40px 20px;
}
.auth-logo{
    text-align:center;margin-bottom:32px;
}
.auth-logo-text{
    font-size:3rem;font-weight:900;color:#ff4444;
    letter-spacing:6px;display:block;
}
.auth-tagline{
    font-size:0.8rem;color:#445566;letter-spacing:2px;
    display:block;margin-top:4px;
}
.auth-card{
    background:#0d1626;border:1px solid #1a2840;
    border-radius:16px;padding:32px;
}
.auth-title{
    font-size:1.2rem;font-weight:800;color:#e0e0e0;
    margin-bottom:24px;text-align:center;
}
.auth-divider{
    border:none;border-top:1px solid #1a2840;
    margin:20px 0;
}
.stTextInput>div>div>input{
    background:#070b14!important;
    border:1px solid #1a2840!important;
    color:#e0e0e0!important;
    border-radius:8px!important;
}
.stTextInput>div>div>input:focus{
    border:1px solid #4488ff!important;
    box-shadow:none!important;
}
.stButton>button{
    background:#ff4444!important;color:#fff!important;
    border:none!important;border-radius:8px!important;
    font-weight:700!important;width:100%!important;
    padding:12px!important;font-size:0.95rem!important;
}
.stButton>button:hover{background:#cc2222!important;}
.auth-footer{
    text-align:center;color:#334455;
    font-size:0.75rem;margin-top:24px;
}
.error-box{
    background:#1a0000;border:1px solid #ff444433;
    border-left:3px solid #ff4444;border-radius:8px;
    padding:10px 14px;color:#ff8888;font-size:0.85rem;
    margin:10px 0;
}
.success-box{
    background:#001a08;border:1px solid #00ff8833;
    border-left:3px solid #00ff88;border-radius:8px;
    padding:10px 14px;color:#00ff88;font-size:0.85rem;
    margin:10px 0;
}
</style>
"""

def render_logo():
    st.markdown("""
    <div class="auth-logo">
        <span class="auth-logo-text">BearIQ</span>
        <span class="auth-tagline">MARKET WEATHER INTELLIGENCE</span>
    </div>
    """, unsafe_allow_html=True)

# ── LOGIN PAGE ────────────────────────────────────────────────────
def render_login():
    st.markdown(AUTH_CSS, unsafe_allow_html=True)
    st.markdown("<div class='auth-container'>", unsafe_allow_html=True)
    render_logo()
    st.markdown("<div class='auth-card'>", unsafe_allow_html=True)
    st.markdown("<div class='auth-title'>Welcome Back</div>", unsafe_allow_html=True)

    username = st.text_input("Username", placeholder="Enter your username", key="login_user")
    password = st.text_input("Password", type="password", placeholder="Enter your password", key="login_pass")

    if st.button("Sign In →", key="login_btn"):
        if not username or not password:
            st.markdown("<div class='error-box'>Please enter username and password</div>", unsafe_allow_html=True)
        else:
            users = load_users()
            user = users.get(username.lower().strip())
            if not user:
                st.markdown("<div class='error-box'>Username not found</div>", unsafe_allow_html=True)
            elif user.get("status") != "active":
                st.markdown("<div class='error-box'>Account inactive. Contact BearIQ support.</div>", unsafe_allow_html=True)
            elif not verify_password(password, user["password_hash"]):
                st.markdown("<div class='error-box'>Incorrect password</div>", unsafe_allow_html=True)
            else:
                save_session(username.lower().strip())
                st.rerun()

    st.markdown("<hr class='auth-divider'>", unsafe_allow_html=True)
    st.markdown("<div style='text-align:center;color:#445566;font-size:0.82rem'>New user? <span style='color:#4488ff'>Register below</span></div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # Register section
    with st.expander("Create New Account"):
        render_register()

    st.markdown("<div class='auth-footer'>BearIQ Market Weather Intelligence<br>For educational purposes only</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ── REGISTER PAGE ─────────────────────────────────────────────────
def render_register():
    st.markdown("<div style='padding:10px 0'>", unsafe_allow_html=True)

    full_name = st.text_input("Full Name", placeholder="Your full name", key="reg_name")
    reg_username = st.text_input("Choose Username", placeholder="e.g. rajesh_trader", key="reg_user")
    email = st.text_input("Email Address", placeholder="your@email.com", key="reg_email")
    reg_password = st.text_input("Create Password", type="password", placeholder="Minimum 6 characters", key="reg_pass")
    invite = st.text_input("Invite Code", placeholder="Enter invite code", key="reg_invite")

    if st.button("Create Account", key="reg_btn"):
        # Validations
        if not all([full_name, reg_username, email, reg_password, invite]):
            st.markdown("<div class='error-box'>All fields are required</div>", unsafe_allow_html=True)
        elif invite.upper().strip() != INVITE_CODE:
            st.markdown("<div class='error-box'>Invalid invite code</div>", unsafe_allow_html=True)
        elif len(reg_password) < 6:
            st.markdown("<div class='error-box'>Password must be at least 6 characters</div>", unsafe_allow_html=True)
        elif " " in reg_username or not reg_username.replace("_","").isalnum():
            st.markdown("<div class='error-box'>Username: letters, numbers and underscore only</div>", unsafe_allow_html=True)
        else:
            users = load_users()
            uname = reg_username.lower().strip()
            if uname in users:
                st.markdown("<div class='error-box'>Username already taken</div>", unsafe_allow_html=True)
            else:
                users[uname] = {
                    "username": uname,
                    "full_name": full_name.strip(),
                    "email": email.strip().lower(),
                    "password_hash": hash_password(reg_password),
                    "created": datetime.now().strftime("%d %b %Y"),
                    "last_login": None,
                    "login_count": 0,
                    "status": "active",
                    "role": "admin" if uname == ADMIN_USERNAME else "user"
                }
                save_users(users)
                st.markdown("<div class='success-box'>Account created! Please sign in above.</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ── ADMIN PAGE ────────────────────────────────────────────────────
def render_admin_users():
    """Admin user management panel"""
    st.markdown("<div style='font-size:1.4rem;font-weight:800;color:#e0e0e0;margin-bottom:20px'>👤 USER MANAGEMENT</div>", unsafe_allow_html=True)

    users = load_users()
    if not users:
        st.info("No users registered yet.")
        return

    # Summary
    total = len(users)
    active = sum(1 for u in users.values() if u.get("status")=="active")
    today = datetime.now().strftime("%d %b %Y")
    logged_today = sum(1 for u in users.values() if u.get("last_login","").startswith(today))

    c1,c2,c3 = st.columns(3)
    with c1: st.metric("Total Users", total)
    with c2: st.metric("Active", active)
    with c3: st.metric("Logged In Today", logged_today)

    st.markdown("---")

    # User table
    for uname, user in users.items():
        if uname == ADMIN_USERNAME: continue
        status = user.get("status","active")
        sc = "#00ff88" if status=="active" else "#ff4444"
        h = f"<div style='background:#0d1626;border:1px solid #1a2840;border-left:3px solid {sc};border-radius:10px;padding:12px 16px;margin-bottom:8px'>"
        h += f"<div style='display:flex;justify-content:space-between;align-items:center'>"
        h += f"<div><div style='color:#e0e0e0;font-weight:700'>@{uname} — {user.get('full_name','')}</div>"
        h += f"<div style='color:#445566;font-size:0.78rem'>{user.get('email','')} | Joined: {user.get('created','')} | Logins: {user.get('login_count',0)}</div>"
        h += f"<div style='color:#445566;font-size:0.78rem'>Last seen: {user.get('last_login','Never')}</div></div>"
        h += f"<div style='color:{sc};font-weight:800;font-size:0.85rem'>{status.upper()}</div></div></div>"
        st.markdown(h, unsafe_allow_html=True)

        col1, col2 = st.columns([1,1])
        with col1:
            if status == "active":
                if st.button(f"🚫 Revoke Access", key=f"revoke_{uname}"):
                    users[uname]["status"] = "inactive"
                    save_users(users)
                    st.rerun()
            else:
                if st.button(f"✅ Restore Access", key=f"restore_{uname}"):
                    users[uname]["status"] = "active"
                    save_users(users)
                    st.rerun()
        with col2:
            if st.button(f"🗑️ Delete User", key=f"delete_{uname}"):
                del users[uname]
                save_users(users)
                st.rerun()

    st.markdown("---")
    st.markdown(f"<div style='color:#445566;font-size:0.78rem'>Invite Code: <span style='color:#ffdd00;font-weight:700'>{INVITE_CODE}</span> — Share with new users</div>", unsafe_allow_html=True)

# ── NAVBAR ────────────────────────────────────────────────────────
def render_navbar():
    """Top navigation bar with user info and logout"""
    user = get_current_user()
    users = load_users()
    user_data = users.get(user, {})
    name = user_data.get("full_name", user)

    st.markdown(f"""
    <div style='background:#0a0f1e;border-bottom:1px solid #1a2840;
                padding:10px 20px;display:flex;justify-content:space-between;
                align-items:center;margin-bottom:20px;border-radius:0 0 12px 12px'>
        <div style='display:flex;align-items:center;gap:12px'>
            <span style='font-size:1.4rem;font-weight:900;color:#ff4444;letter-spacing:3px'>BearIQ</span>
            <span style='color:#334455;font-size:0.75rem;letter-spacing:2px'>MARKET WEATHER INTELLIGENCE</span>
        </div>
        <div style='display:flex;align-items:center;gap:16px'>
            <span style='color:#445566;font-size:0.82rem'>👤 {name}</span>
            {'<span style="background:#ff444422;color:#ff4444;padding:2px 10px;border-radius:20px;font-size:0.7rem;font-weight:800">ADMIN</span>' if is_admin() else ''}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Logout button in sidebar
    with st.sidebar:
        st.markdown(f"<div style='padding:10px 0;border-bottom:1px solid #1a2840;margin-bottom:12px'>"
                   f"<div style='color:#e0e0e0;font-weight:700'>👤 {name}</div>"
                   f"<div style='color:#445566;font-size:0.75rem'>@{user}</div></div>", unsafe_allow_html=True)
        if st.button("🚪 Sign Out", key="logout_btn"):
            logout()
            st.rerun()
