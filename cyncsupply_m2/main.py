import streamlit as st

from db import (
    init_db, seed_if_empty, read_df, exec_sql,
    hash_password, verify_password,
    backend_label, health_check,
)

ALL_MODULES = [
    "Dashboard",
    "Categorized Inventory",
    "Product Management",
    "Pending Deliveries",
    "Barcode Generator",
    "Barcode Scanner",
    "Item Sales Analytics",
    "Purchase Order Module",
]

ROLE_MODULES = {
    "System Admin":           ALL_MODULES,
    "Inventory Manager":      ALL_MODULES,
    "Yard Clerk / Inspector": ["Dashboard", "Categorized Inventory",
                               "Pending Deliveries",
                               "Barcode Generator", "Barcode Scanner"],
    "Sales Analyst":          ["Dashboard", "Item Sales Analytics"],
}


# ==========================================
# FLASH MESSAGES
# ==========================================
def flash(level: str, msg: str) -> None:
    st.session_state.setdefault("_flash", []).append((level, msg))


def render_flashes() -> None:
    for level, msg in st.session_state.pop("_flash", []):
        getattr(st, level)(msg)


# ==========================================
# AUTH
# ==========================================
def render_auth_page():
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown(
            "<h1 class='brand-title'>📦 CYNCSUPPLY</h1>"
            "<p class='brand-sub'>Multi-Device Inventory &amp; Receiving Management</p>",
            unsafe_allow_html=True,
        )

        ok, msg = health_check()
        color = "#2e7d32" if ok else "#d32f2f"
        icon = "🟢" if ok else "🔴"
        st.markdown(
            f"<p style='text-align:center;font-size:12px;color:{color};'>"
            f"{icon} Backend: {msg}</p>",
            unsafe_allow_html=True,
        )

        st.markdown("---")
        tab_login, tab_signup = st.tabs(["🔑 Log In", "📝 Sign Up"])

        with tab_login:
            st.subheader("Account Login")
            login_user = st.text_input("Username", key="login_username")
            login_pass = st.text_input("Password", type="password", key="login_password")

            if st.button("Log In", type="primary", use_container_width=True):
                if not login_user or not login_pass:
                    st.warning("Please enter both username and password.")
                else:
                    rows = read_df(
                        "SELECT username, name, password, role FROM users WHERE username = ?",
                        (login_user,),
                    )
                    if rows.empty or not verify_password(login_pass, rows.iloc[0]["password"]):
                        st.error("Invalid Username or Password.")
                    else:
                        r = rows.iloc[0]
                        st.session_state.authenticated = True
                        st.session_state.logged_user = {
                            "username": r["username"],
                            "name": r["name"],
                            "role": r["role"],
                        }
                        flash("success", f"Welcome back, {r['name']}!")
                        st.rerun()

        with tab_signup:
            st.subheader("Create New Account")
            new_name = st.text_input("Full Name", key="signup_name")
            new_user = st.text_input("Username", key="signup_username")
            new_role = st.selectbox(
                "Role / Department",
                ["Yard Clerk / Inspector", "Inventory Manager",
                 "Sales Analyst", "System Admin"],
                key="signup_role",
            )
            new_pass = st.text_input("Password", type="password", key="signup_password")
            confirm_pass = st.text_input("Confirm Password", type="password",
                                         key="signup_confirm_password")

            if st.button("Create Account", type="primary", use_container_width=True):
                if not new_name or not new_user or not new_pass:
                    st.warning("Please fill in all required fields.")
                elif new_pass != confirm_pass:
                    st.error("Passwords do not match.")
                elif not read_df("SELECT 1 FROM users WHERE username = ?", (new_user,)).empty:
                    st.error("Username already exists. Please choose a different one.")
                else:
                    exec_sql(
                        "INSERT INTO users (username, name, password, role) VALUES (?,?,?,?)",
                        (new_user, new_name, hash_password(new_pass), new_role),
                    )
                    st.success("Account created successfully! You can now log in.")


# ==========================================
# SESSION BOOTSTRAP
# ==========================================
def init_session_state():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "logged_user" not in st.session_state:
        st.session_state.logged_user = None
    if "po_cart" not in st.session_state:
        st.session_state.po_cart = []


# ==========================================
# LIVE LOW-STOCK BANNER
# ==========================================
@st.fragment(run_every="5s")
def live_alert_banner():
    low = read_df(
        "SELECT item_id, name, quantity, threshold FROM inventory "
        "WHERE quantity <= threshold ORDER BY (quantity * 1.0 / NULLIF(threshold,0)) ASC"
    )
    if low.empty:
        st.markdown(
            "<div class='alert-bar alert-ok'>✅ All stock above critical thresholds.</div>",
            unsafe_allow_html=True,
        )
        return

    names = " · ".join(f"{r['name']} ({r['quantity']}/{r['threshold']})"
                       for _, r in low.head(4).iterrows())
    more = f" +{len(low) - 4} more" if len(low) > 4 else ""
    st.markdown(
        f"<div class='alert-bar alert-warn'>🔴 <b>{len(low)} item(s) at or below threshold</b>"
        f" — {names}{more}</div>",
        unsafe_allow_html=True,
    )


# ==========================================
# SIDEBAR: LOW-STOCK QUICK-ORDER
# ==========================================
def render_low_stock_alerts(user_role: str) -> None:
    if "Purchase Order Module" not in ROLE_MODULES.get(user_role, []):
        return

    low = read_df("SELECT item_id, name, quantity, threshold FROM inventory "
                  "WHERE quantity <= threshold ORDER BY quantity ASC")
    if low.empty:
        return

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"### ⚠️ Low Stock ({len(low)})")
    for _, row in low.iterrows():
        if st.sidebar.button(
            f"🔴 {row['name']}\n({row['quantity']} / {row['threshold']})",
            key=f"low_{row['item_id']}",
            use_container_width=True,
        ):
            st.session_state.po_prefill = row["name"]
            st.session_state.nav_to = "Purchase Order Module"
            st.rerun()


# ==========================================
# PAGE CONFIG + STYLES
# ==========================================
st.set_page_config(
    page_title="CyncSupply - Multi-Device System",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    :root {
        --cync-red: #d32f2f;
        --cync-green: #2e7d32;
        --cync-amber: #ed6c02;
        --cync-ink: #111827;
    }
    .brand-title { text-align: center; font-weight: 800; letter-spacing: 1px;
                   color: var(--cync-ink); }
    .brand-sub { text-align: center; font-weight: 500; }

    .alert-bar { padding: 12px 18px; border-radius: 10px; font-size: 15px;
                 margin: 4px 0 16px 0; line-height: 1.4; }
    .alert-warn { background: #fdecea; border-left: 6px solid var(--cync-red);
                  color: #611a15; }
    .alert-ok   { background: #eaf6ec; border-left: 6px solid var(--cync-green);
                  color: #14532d; }

    .cat-card { padding: 14px 16px; border-radius: 12px; background: #ffffff;
                border: 1px solid #e5e7eb; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
                height: 100%; }
    .cat-card h4 { margin: 0 0 6px 0; font-size: 14px; color: #6b7280;
                   letter-spacing: .4px; }
    .cat-card .big { font-size: 26px; font-weight: 800; color: var(--cync-ink); }
    .cat-card .sub { font-size: 12px; color: #6b7280; margin-top: 4px; }
    .cat-card.danger { border-left: 6px solid var(--cync-red); }
    .cat-card.warn   { border-left: 6px solid var(--cync-amber); }
    .cat-card.ok     { border-left: 6px solid var(--cync-green); }

    .receiving-tag { background-color: #fffef5; border: 2px dashed var(--cync-red);
                     border-radius: 10px; padding: 20px; margin-top: 15px; }
    .tag-header { font-weight: 900; font-size: 18px; color: var(--cync-red);
                  border-bottom: 2px solid var(--cync-red); padding-bottom: 5px;
                  margin-bottom: 10px; }
    .anti-theft-stamp { display: inline-block; border: 2px solid var(--cync-green);
                        color: var(--cync-green); font-weight: bold; font-size: 12px;
                        padding: 4px 8px; border-radius: 4px; margin-top: 10px; }

    .flow-banner {
        background: linear-gradient(90deg, #fff7e6, #ffe4e1);
        border-left: 6px solid #ed6c02;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 16px;
        color: #5c2c06;
        font-weight: 500;
    }

    .stButton > button { min-height: 44px; font-weight: 600; border-radius: 8px; }
    .stButton > button[kind="primary"] { background: var(--cync-red);
                                          border-color: var(--cync-red); }
    .stButton > button[kind="primary"]:hover { background: #b71c1c;
                                                border-color: #b71c1c; }

    @media (max-width: 900px) {
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
        [data-testid="column"] { min-width: 100% !important; flex: 1 1 100% !important; }
        .brand-title { font-size: 26px !important; }
        .cat-card .big { font-size: 22px; }
        .stButton > button { min-height: 52px; font-size: 16px; }
        .alert-bar { font-size: 14px; padding: 10px 14px; }
        [data-testid="stDataFrame"] { overflow-x: auto; }
    }
    @media (max-width: 480px) {
        .stButton > button { min-height: 56px; font-size: 17px; }
        .brand-title { font-size: 22px !important; }
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# BOOT
# ==========================================
init_db()
seed_if_empty()
init_session_state()


# ==========================================
# IMPORTS
# ==========================================
from feature_dashboard import render_dashboard_module
from feature_inventory import render_inventory_module
from feature_products import render_product_management_module
from feature_delivery import render_delivery_module
from feature_receiving import render_receiving_module
from feature_camera_scan import render_camera_scan_module
from feature_analytics import render_analytics_module
from feature_po import render_po_module


# ==========================================
# ROUTER
# ==========================================
MENU_KEY = "_cync_menu"

if not st.session_state.authenticated:
    render_auth_page()
else:
    user = st.session_state.logged_user

    st.sidebar.title("📦 CYNCSUPPLY")
    st.sidebar.markdown(f"👤 **User:** {user['name']}  \n🏷️ **Role:** `{user['role']}`")

    ok, msg = health_check()
    color = "#2e7d32" if ok else "#d32f2f"
    icon = "🟢" if ok else "🔴"
    st.sidebar.markdown(
        f"<div style='font-size:12px;color:{color};padding:6px 0;'>{icon} {msg}</div>",
        unsafe_allow_html=True,
    )

    if st.sidebar.button("🚪 Log Out", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.logged_user = None
        st.session_state.pop("_flash", None)
        st.session_state.pop("po_cart", None)
        st.session_state.pop(MENU_KEY, None)
        st.session_state.pop("receiving_prefill", None)
        st.session_state.pop("pending_delete_id", None)
        st.rerun()

    st.sidebar.markdown("---")

    available = [m for m in ALL_MODULES if m in ROLE_MODULES.get(user["role"], [])] or ["Dashboard"]

    if MENU_KEY not in st.session_state or st.session_state[MENU_KEY] not in available:
        st.session_state[MENU_KEY] = available[0]

    nav = st.session_state.pop("nav_to", None)
    if nav and nav in available:
        st.session_state[MENU_KEY] = nav

    menu = st.sidebar.radio("SELECT MODULE", available, key=MENU_KEY)

    render_low_stock_alerts(user["role"])

    st.sidebar.markdown("---")
    st.sidebar.info("📱 Responsive: desktop · laptop · tablet · mobile")

    live_alert_banner()
    render_flashes()

    if menu == "Dashboard":
        render_dashboard_module()
    elif menu == "Categorized Inventory":
        render_inventory_module()
    elif menu == "Product Management":
        render_product_management_module()
    elif menu == "Pending Deliveries":
        render_delivery_module()
    elif menu == "Barcode Generator":
        render_receiving_module()
    elif menu == "Barcode Scanner":
        render_camera_scan_module()
    elif menu == "Item Sales Analytics":
        render_analytics_module()
    elif menu == "Purchase Order Module":
        render_po_module()