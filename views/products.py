import streamlit as st

from models.connection import read_df, exec_sql, flash


CATEGORIES = ["Cements", "Rebars", "Paints", "Sand & Gravel", "Other"]


# ==========================================
# ADD PRODUCT
# ==========================================
def _render_add_form():
    st.subheader("➕ Add New Product")
    st.caption("Create a new inventory item. The **Item ID** is its unique code and cannot be changed later.")

    existing_suppliers = read_df(
        "SELECT DISTINCT supplier FROM inventory WHERE supplier <> '' ORDER BY supplier"
    )["supplier"].tolist()

    with st.form("add_product_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            item_id = st.text_input(
                "Item ID *",
                placeholder="e.g. CMT-003",
                help="Short unique code. Uppercase letters, numbers, and dashes recommended.",
            )
            name = st.text_input(
                "Item Name *",
                placeholder="e.g. Holcim Portland Cement (50kg)",
            )
            category = st.selectbox("Category *", CATEGORIES, index=0)

        with c2:
            quantity = st.number_input("Initial Quantity", min_value=0, value=0, step=1)
            threshold = st.number_input("Low-Stock Threshold", min_value=0, value=10, step=1,
                                        help="Alert appears when quantity falls to or below this value.")
            supplier_price = st.number_input("Supplier Price (₱)", min_value=0.0, value=0.0,
                                             step=0.01, format="%.2f")

        supplier = st.text_input("Supplier *", placeholder="e.g. Holcim Direct Phil")
        if existing_suppliers:
            st.caption("Existing suppliers: " + ", ".join(f"`{s}`" for s in existing_suppliers[:8])
                       + (f" +{len(existing_suppliers)-8} more" if len(existing_suppliers) > 8 else ""))

        submitted = st.form_submit_button("➕ Add Product", type="primary", use_container_width=True)

        if submitted:
            errors = []
            if not item_id.strip():
                errors.append("Item ID is required.")
            if not name.strip():
                errors.append("Item Name is required.")
            if not supplier.strip():
                errors.append("Supplier is required.")

            if item_id.strip():
                dup = read_df(
                    "SELECT item_id FROM inventory WHERE UPPER(item_id) = ?",
                    (item_id.strip().upper(),),
                )
                if not dup.empty:
                    errors.append(f"Item ID `{item_id.strip().upper()}` already exists. Choose a different one.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                exec_sql(
                    "INSERT INTO inventory "
                    "(item_id, name, category, quantity, threshold, supplier_price, supplier) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (item_id.strip().upper(), name.strip(), category,
                     int(quantity), int(threshold), float(supplier_price), supplier.strip()),
                )
                flash("success", f"✅ Added product: **{name}** (`{item_id.strip().upper()}`)")
                st.rerun()


# ==========================================
# EDIT PRODUCT
# ==========================================
def _render_edit_form():
    st.subheader("✏️ Edit Existing Product")

    inv = read_df("SELECT * FROM inventory ORDER BY name")
    if inv.empty:
        st.info("No products in inventory yet. Use the **Add Product** tab to create one.")
        return

    options = [f"{r['item_id']} — {r['name']}" for _, r in inv.iterrows()]
    selected = st.selectbox("Select product to edit", options, key="edit_product_select")
    selected_id = selected.split(" — ")[0]
    row = inv[inv["item_id"] == selected_id].iloc[0]

    st.markdown(f"**Editing:** `{row['item_id']}` — {row['name']}")
    st.caption("Item ID is locked. All other fields can be changed.")

    cat = row["category"] if row["category"] in CATEGORIES else "Other"
    cat_idx = CATEGORIES.index(cat)

    with st.form("edit_product_form"):
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("Item ID (locked)", value=row["item_id"], disabled=True)
            name = st.text_input("Item Name", value=row["name"])
            category = st.selectbox("Category", CATEGORIES, index=cat_idx)
        with c2:
            quantity = st.number_input("Quantity", min_value=0, value=int(row["quantity"]), step=1)
            threshold = st.number_input("Low-Stock Threshold", min_value=0, value=int(row["threshold"]), step=1)
            supplier_price = st.number_input("Supplier Price (₱)", min_value=0.0,
                                             value=float(row["supplier_price"]),
                                             step=0.01, format="%.2f")

        supplier = st.text_input("Supplier", value=row["supplier"])

        saved = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)

        if saved:
            errors = []
            if not name.strip():
                errors.append("Item Name is required.")
            if not supplier.strip():
                errors.append("Supplier is required.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                exec_sql(
                    "UPDATE inventory SET name = ?, category = ?, quantity = ?, "
                    "threshold = ?, supplier_price = ?, supplier = ? "
                    "WHERE item_id = ?",
                    (name.strip(), category, int(quantity), int(threshold),
                     float(supplier_price), supplier.strip(), row["item_id"]),
                )
                if name.strip() != row["name"]:
                    flash("warning",
                          f"✅ Updated **{name}**. ⚠️ Barcodes generated for the old name "
                          f"(`{row['name']}`) will no longer match this item.")
                else:
                    flash("success", f"✅ Updated product: **{name}**")
                st.rerun()

    # ---- Delete zone ----
    st.markdown("---")
    st.markdown("#### 🗑️ Danger Zone")

    pending = st.session_state.get("pending_delete_id")
    if pending == row["item_id"]:
        st.warning(
            f"⚠️ **Confirm deletion** of `{row['item_id']}` — **{row['name']}**?\n\n"
            f"This cannot be undone. Any barcodes referencing this item will be orphaned."
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Yes, delete permanently", type="primary", use_container_width=True):
                exec_sql("DELETE FROM inventory WHERE item_id = ?", (row["item_id"],))
                st.session_state.pop("pending_delete_id", None)
                flash("warning", f"🗑️ Deleted product: **{row['name']}**")
                st.rerun()
        with c2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.pop("pending_delete_id", None)
                st.rerun()
    else:
        if st.button("🗑️ Delete this product", use_container_width=True):
            st.session_state["pending_delete_id"] = row["item_id"]
            st.rerun()


# ==========================================
# MAIN MODULE
# ==========================================
def render_product_management_module():
    st.title("📦 Product Management")
    st.caption("Add new products to inventory or edit existing ones.")

    tab_add, tab_edit = st.tabs(["➕ Add Product", "✏️ Edit / Delete Product"])

    with tab_add:
        _render_add_form()

    with tab_edit:
        _render_edit_form()

    st.markdown("---")
    st.subheader("📋 Full Product List")
    inv = read_df(
        "SELECT item_id, name, category, quantity, threshold, supplier_price, supplier "
        "FROM inventory ORDER BY category, name"
    )
    if inv.empty:
        st.caption("No products yet.")
    else:
        st.dataframe(
            inv.rename(columns={
                "item_id": "Item ID", "name": "Item Name", "category": "Category",
                "quantity": "Qty", "threshold": "Threshold",
                "supplier_price": "Unit Price", "supplier": "Supplier",
            }).style.format({"Unit Price": "₱{:,.2f}"}),
            use_container_width=True, hide_index=True,
        )
        st.caption(f"Total products: **{len(inv)}**")