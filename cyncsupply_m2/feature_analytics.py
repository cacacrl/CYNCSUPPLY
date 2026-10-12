import streamlit as st
import pandas as pd

from db import read_df


def _turnover_tier(ratio: float) -> str:
    if ratio >= 2.0:
        return "🔥 Fast"
    if ratio >= 1.0:
        return "⚡ Steady"
    if ratio >= 0.3:
        return "🟡 Slow"
    return "🧊 Stagnant"


def render_analytics_module():
    st.title("📈 Item Sales Analytics Dashboard")
    st.caption("Real-time velocity, high-demand rankings, and stock turnover rates.")
    st.caption("🔄 Auto-refreshes every 5 s.")

    @st.fragment(run_every="5s")
    def _analytics_body():
        df = read_df("SELECT * FROM sales")
        if df.empty:
            st.info("No sales recorded yet.")
            return

        units_total = int(df["units"].sum())
        revenue = read_df("""
            SELECT SUM(s.units * i.supplier_price) AS r
            FROM sales s LEFT JOIN inventory i ON s.item_id = i.item_id
        """).iloc[0]["r"]
        revenue = float(revenue) if pd.notna(revenue) else 0.0

        inv_value = read_df(
            "SELECT SUM(quantity * supplier_price) AS v FROM inventory"
        ).iloc[0]["v"]
        inv_value = float(inv_value) if pd.notna(inv_value) else 0.0

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Units Sold", f"{units_total:,}")
        c2.metric("Est. Sales Value (at supplier price)", f"₱{revenue:,.2f}")
        c3.metric("Inventory Value", f"₱{inv_value:,.2f}")

        st.markdown("### 📉 Sales Velocity Trend")
        trend = (df.groupby("date")["units"].sum()
                   .reset_index().sort_values("date"))
        st.line_chart(trend.set_index("date"))

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("### 📊 Units by Category")
            cat = df.groupby("category")["units"].sum().reset_index()
            st.bar_chart(cat.set_index("category"))
        with col_b:
            st.markdown("### 📐 Category Sales Ratio")
            totals = df.groupby("category")["units"].sum()
            ratio = (totals / totals.sum() * 100).round(1).rename("Share %").reset_index()
            ratio.columns = ["Category", "Share %"]
            st.dataframe(ratio, use_container_width=True, hide_index=True)

        st.markdown("### 🔄 Stock Turnover (Units Sold ÷ Current Stock)")
        inv = read_df("SELECT name, quantity FROM inventory").set_index("name")["quantity"]
        sold = df.groupby("item_name")["units"].sum()
        turnover = (sold / inv).replace([float("inf"), -float("inf")], None).dropna()

        turnover_df = (
            turnover.round(2).rename("Turnover Ratio").reset_index()
                .rename(columns={"item_name": "Item Name"})
                .sort_values("Turnover Ratio", ascending=False)
        )
        turnover_df["Tier"] = turnover_df["Turnover Ratio"].apply(_turnover_tier)
        st.dataframe(turnover_df, use_container_width=True, hide_index=True)
        st.caption("Fast: ≥ 2.0 · Steady: ≥ 1.0 · Slow: ≥ 0.3 · Stagnant: < 0.3")

        st.markdown("### 🔥 Top Selling Items (Velocity Ranking)")
        rank = (df.groupby("item_name")["units"].sum()
                  .reset_index()
                  .rename(columns={"item_name": "Item Name", "units": "Units Sold"})
                  .sort_values("Units Sold", ascending=False)
                  .reset_index(drop=True))
        rank.insert(0, "Rank", range(1, len(rank) + 1))
        st.dataframe(rank.head(10), use_container_width=True, hide_index=True)

        st.markdown("### 📋 Recent Sales Log")
        recent = (df.sort_values("id", ascending=False)
                    .head(15)
                    [["date", "item_name", "units", "category", "performed_by"]]
                    .rename(columns={
                        "date": "Date", "item_name": "Item", "units": "Units",
                        "category": "Category", "performed_by": "Sold By",
                    }))
        st.dataframe(recent, use_container_width=True, hide_index=True)

    _analytics_body()