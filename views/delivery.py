import streamlit as st
import datetime

from repositories.connection import read_df, exec_sql, today_str, flash


def render_delivery_module():
    st.title("📦 Pending Delivery Checklist")
    st.caption("Verify physical stock, confirm receipt, then generate per-item barcodes.")

    st.markdown(
        "<div class='flow-banner'>"
        "🔄 <b>Flow:</b> Confirm receipt → inventory credited → auto-open the "
        "Barcode Generator to print one label per unit."
        "</div>",
        unsafe_allow_html=True,
    )

    with st.expander("➕ Log an Expected Delivery (manual)"):
        inv = read_df("SELECT item_id, name FROM inventory ORDER BY name")
        c1, c2, c3 = st.columns(3)
        with c1:
            po_ref = st.text_input("PO / Delivery Ref #", key="del_po")
            supplier = st.text_input("Supplier", key="del_sup")
        with c2:
            item = st.selectbox("Expected Item", inv["name"].tolist(), key="del_item")
            qty = st.number_input("Expected Quantity", min_value=1, value=50, key="del_qty")
        with c3:
            eta = st.date_input("ETA", value=datetime.date.today(), key="del_eta")
            st.write("")
            if st.button("Add to Checklist", type="primary"):
                exec_sql(
                    "INSERT INTO pending_deliveries "
                    "(po_number, supplier, item_name, ordered, eta, added_by) "
                    "VALUES (?,?,?,?,?,?)",
                    (po_ref or "—", supplier or "—", item, int(qty),
                     str(eta), st.session_state.logged_user["name"]),
                )
                flash("success", f"Added {item} to checklist.")
                st.rerun()

    st.markdown("---")

    pending = read_df("SELECT * FROM pending_deliveries ORDER BY eta")
    if pending.empty:
        st.info("No pending deliveries. Dispatched POs will appear here automatically.")
        return

    st.markdown(f"### 🚚 {len(pending)} Awaiting Verification")

    for _, d in pending.iterrows():
        did = int(d["id"])
        header = f"**{d['po_number']}** — {d['supplier']} — ETA {d['eta']}"

        with st.expander(header):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Ordered", int(d["ordered"]))
                st.caption(f"Item: **{d['item_name']}**")
            with col2:
                verified = st.number_input(
                    "Verified Physical Count",
                    min_value=0, value=int(d["ordered"]),
                    key=f"ver_{did}",
                )

            notes = st.text_input("Discrepancy Notes", key=f"notes_{did}")

            if verified != int(d["ordered"]):
                st.warning(f"⚠️ Discrepancy: ordered {int(d['ordered'])}, verified {verified}")

            b1, b2 = st.columns(2)
            with b1:
                if st.button("✅ Confirm Received → Label Units",
                             key=f"ok_{did}", type="primary", use_container_width=True):
                    inv_check = read_df(
                        "SELECT quantity FROM inventory WHERE name = ?",
                        (d["item_name"],),
                    )
                    if inv_check.empty:
                        st.error(f"Item '{d['item_name']}' not found in inventory.")
                        st.stop()

                    old_qty = int(inv_check.iloc[0]["quantity"])
                    new_qty = old_qty + int(verified)

                    exec_sql(
                        "UPDATE inventory SET quantity = ? WHERE name = ?",
                        (new_qty, d["item_name"]),
                    )

                    exec_sql(
                        "INSERT INTO intake_log "
                        "(po_number, supplier, item_name, ordered, verified_qty, "
                        " notes, received, received_by) VALUES (?,?,?,?,?,?,?,?)",
                        (d["po_number"], d["supplier"], d["item_name"],
                         int(d["ordered"]), int(verified), notes,
                         today_str(), st.session_state.logged_user["name"]),
                    )

                    exec_sql("DELETE FROM pending_deliveries WHERE id = ?", (did,))

                    st.session_state.receiving_prefill = {
                        "po_number": d["po_number"] or "—",
                        "supplier": d["supplier"] or "Holcim Direct Phil",
                        "item_name": d["item_name"],
                        "quantity": int(verified),
                        "note": f"PO {d['po_number']} — {d['supplier']}",
                    }
                    st.session_state.nav_to = "Barcode Generator"

                    flash("success",
                          f"✅ Received {verified} × {d['item_name']} — inventory "
                          f"{old_qty} → {new_qty}. Opening barcode generator…")
                    st.rerun()
            with b2:
                if st.button("❌ Reject / Send Back", key=f"rej_{did}",
                             use_container_width=True):
                    exec_sql("DELETE FROM pending_deliveries WHERE id = ?", (did,))
                    flash("warning", f"Delivery {d['po_number']} rejected.")
                    st.rerun()

    st.markdown("---")
    st.subheader("📋 Recent Intake History")
    log = read_df("SELECT * FROM intake_log ORDER BY id DESC LIMIT 20")
    if log.empty:
        st.caption("No confirmed intakes yet.")
    else:
        st.dataframe(
            log.rename(columns={
                "po_number": "PO #", "supplier": "Supplier", "item_name": "Item",
                "ordered": "Ordered", "verified_qty": "Verified",
                "notes": "Notes", "received": "Date", "received_by": "Received By",
            }).drop(columns=["id"]),
            use_container_width=True, hide_index=True,
        )