import streamlit as st

from models.connection import read_df, exec_sql, hash_password, verify_password, health_check


def flash(level: str, msg: str) -> None:
    st.session_state.setdefault("_flash", []).append((level, msg))


def render_flashes() -> None:
    for level, msg in st.session_state.pop("_flash", []):
        getattr(st, level)(msg)


def render_auth_page() -> None:
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