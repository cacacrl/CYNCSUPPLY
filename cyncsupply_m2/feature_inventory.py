import streamlit as st
import datetime

from db import read_df, exec_sql, today_str, flash


def _row_color(row):
    if row["Quantity"] <= row["Threshold"]:
        return ["color: #dc2626; font-weight: 700; "
                "border-left: 5px solid #dc2626"] * len(row)
    if row["Threshold"] > 0 and row["Quantity"] / row["Threshold"] <= 1.5:
        return ["color: #d97706; font-weight: 600; "
                "border-left: 5px solid #d97706"] * len(row)
    return ["color: #16a34a; border-left: 5px solid #16a34a"] * len(row)


def render_inventory_module():
    st.title("🧱 Categorized Inventory Tracking")
    st.caption("Live stock levels — auto-refreshes every 5 seconds.")

    # ---- Top action row: Refresh button + timestamp ----
    top1, top2 = st.columns([1, 4])
    with top1:
        if st.button("🔄 Refresh Now", use_container_width=True):
            st.rerun()
    with top2:
        now_str_display = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"🕒 Last refreshed: **{now_str_display}**")

    @st.fragment(run_every="5s")
    def _inventory_table():
        df = read_df(
            "SELECT item_id, name, category, quantity, threshold, "
            "supplier_price, supplier FROM inventory ORDER BY category, name"
        )

        category_filter = st.selectbox(
            "Filter by Category",
            ["All Categories", "Cements", "Rebars", "Paints", "Sand & Gravel"],
            key="inv_filter",
        )
        view = df if category_filter == "All Categories" else df[df["category"] == category_filter]

        display = view.rename(columns={
            "item_id": "Item ID", "name": "Item Name", "category": "Category",
            "quantity": "Quantity", "threshold": "Threshold",
            "supplier_price": "Supplier Price", "supplier": "Supplier",
        })

        display["Alert"] = display.apply(
            lambda r: "🔴 LOW" if r["Quantity"] <= r["Threshold"] else "🟢 OK", axis=1
        )

        styled = (
            display.style
            .apply(_row_color, axis=1)
            .format({"Supplier Price": "₱{:,.2f}"})
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # Show total units as a sanity check
        total = int(view["quantity"].sum()) if not view.empty else 0
        st.caption(f"📦 Total units in view: **{total}** across {len(view)} item(s)")

    _inventory_table()

    st.markdown("---")

    # ==========================================
    # POS Scan
    # ==========================================
    st.subheader("📷 Point of Sale — Scan to Dispatch")
    st.caption("USB/Bluetooth scanners act as keyboards — scan a tag and press Enter.")

    scan = st.text_input(
        "Scan item barcode / Item ID",
        key="pos_scan",
        placeholder="e.g. CMT-001",
    )

    if not scan:
        st.info("Awaiting scan… or type an Item ID and press Enter.")
        return

    code = scan.strip().upper()
    match = read_df("SELECT * FROM inventory WHERE UPPER(item_id) = ?", (code,))

    if match.empty:
        st.error(f"❌ No item matches '{scan}'")
        return

    item = match.iloc[0]
    on_hand = int(item["quantity"])
    st.success(f"✅ {item['name']}  |  On hand: {on_hand}  |  Supplier: {item['supplier']}")

    if on_hand <= 0:
        st.error("Out of stock — cannot dispatch.")
        return

    qty = st.number_input(
        "Quantity to dispatch",
        min_value=1, max_value=on_hand, value=1,
        key=f"qty_{item['item_id']}",
    )

    if st.button("🚀 Dispatch & Record Sale", type="primary"):
        exec_sql(
            "UPDATE inventory SET quantity = quantity - ? "
            "WHERE item_id = ? AND quantity >= ?",
            (int(qty), item["item_id"], int(qty)),
        )
        remaining = read_df("SELECT quantity FROM inventory WHERE item_id = ?",
                            (item["item_id"],)).iloc[0]["quantity"]
        if remaining == on_hand:
            st.error("Insufficient stock — dispatch aborted.")
            return

        exec_sql(
            "INSERT INTO sales (date, item_id, item_name, units, category, performed_by) "
            "VALUES (?,?,?,?,?,?)",
            (today_str(), item["item_id"], item["name"], int(qty),
             item["category"], st.session_state.logged_user["name"]),
        )
        flash("success", f"Dispatched {qty} × {item['name']} — {remaining} remaining.")
        st.session_state.pop("pos_scan", None)
        st.rerun()