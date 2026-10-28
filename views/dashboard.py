import streamlit as st
from repositories.connection import read_df


@st.fragment(run_every="5s")
def _live_kpis():
    inv = read_df("SELECT * FROM inventory")
    sales = read_df("SELECT * FROM sales")
    pos = read_df("SELECT COUNT(*) AS n FROM purchase_orders").iloc[0]["n"]
    pend = read_df("SELECT COUNT(*) AS n FROM pending_deliveries").iloc[0]["n"]

    low = inv[inv["quantity"] <= inv["threshold"]]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total SKUs", len(inv))
    c2.metric("Low-Stock Alerts", len(low),
              delta=(f"-{len(low)}" if len(low) else "clear"),
              delta_color="inverse" if len(low) else "off")
    c3.metric("Units Sold (all time)", int(sales["units"].sum()) if len(sales) else 0)
    c4.metric("Open Deliveries / POs", f"{pend} / {pos}")


def render_dashboard_module():
    st.title("📊 Operations Dashboard")
    st.caption("Live snapshot — auto-refreshes every 5 seconds.")

    _live_kpis()

    st.markdown("---")
    st.subheader("🏷️ Category Health")

    inv = read_df("SELECT * FROM inventory")
    categories = ["Cements", "Rebars", "Paints", "Sand & Gravel"]
    cols = st.columns(4)

    for col, cat in zip(cols, categories):
        sub = inv[inv["category"] == cat]
        total_qty = int(sub["quantity"].sum()) if len(sub) else 0
        skus = len(sub)
        alerts = int((sub["quantity"] <= sub["threshold"]).sum()) if len(sub) else 0

        status = "ok"
        if alerts > 0:
            status = "danger"
        elif len(sub) and (sub["quantity"] / sub["threshold"].replace(0, 1)).min() <= 1.5:
            status = "warn"

        with col:
            st.markdown(
                f"<div class='cat-card {status}'>"
                f"<h4>{cat.upper()}</h4>"
                f"<div class='big'>{total_qty:,} "
                f"<span style='font-size:14px;font-weight:500'>units</span></div>"
                f"<div class='sub'>{skus} SKUs · {alerts} low-stock alert(s)</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("📈 Sales by Category")
        scat = read_df("SELECT category, SUM(units) AS units FROM sales GROUP BY category")
        if not scat.empty:
            st.bar_chart(scat.set_index("category"))

    with col_b:
        st.subheader("🕒 Units Sold — Last 7 Days")
        trend = read_df(
            "SELECT date, SUM(units) AS units FROM sales "
            "GROUP BY date ORDER BY date DESC LIMIT 7"
        )
        if not trend.empty:
            st.line_chart(trend.set_index("date").sort_index())

    st.markdown("---")
    st.subheader("⚠️ Items Needing Reorder")
    low = inv[inv["quantity"] <= inv["threshold"]].sort_values("quantity")
    if low.empty:
        st.success("All items above threshold.")
    else:
        st.dataframe(
            low[["item_id", "name", "category", "quantity", "threshold", "supplier"]]
              .rename(columns={
                  "item_id": "Item ID", "name": "Item Name", "category": "Category",
                  "quantity": "On Hand", "threshold": "Threshold", "supplier": "Supplier",
              }),
            use_container_width=True, hide_index=True,
        )
        if st.button("📝 Dispatch Reorders (Purchase Order Module)", type="primary"):
            st.session_state.nav_to = "Purchase Order Module"
            st.rerun()