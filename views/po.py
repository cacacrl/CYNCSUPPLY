import streamlit as st
import datetime
import os
from io import BytesIO

from repositories.connection import (
    read_df, exec_sql, today_str, next_po_number,
    vendors_for_item, flash,
)

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    _PDF_OK = True
except Exception:
    _PDF_OK = False


_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"

_FONT_CANDIDATES = [
    ("C:/Windows/Fonts/DejaVuSans.ttf",
     "C:/Windows/Fonts/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf",
     "C:/Windows/Fonts/arialbd.ttf"),
    ("C:/Windows/Fonts/segoeui.ttf",
     "C:/Windows/Fonts/segoeuib.ttf"),
    ("C:/Windows/Fonts/calibri.ttf",
     "C:/Windows/Fonts/calibrib.ttf"),
    ("/Library/Fonts/Arial.ttf",
     "/Library/Fonts/Arial Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
]


def _register_fonts():
    global _FONT_REGULAR, _FONT_BOLD
    if not _PDF_OK:
        return
    for regular, bold in _FONT_CANDIDATES:
        if os.path.exists(regular) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont("CyncReg", regular))
                pdfmetrics.registerFont(TTFont("CyncBold", bold))
                _FONT_REGULAR = "CyncReg"
                _FONT_BOLD = "CyncBold"
                return
            except Exception:
                continue


_register_fonts()


def _esc(s):
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def _preview_po_numbers(n: int) -> list:
    base = int(read_df("SELECT COUNT(*) AS n FROM purchase_orders").iloc[0]["n"])
    date_part = today_str()[:7].replace("-", "")
    return [f"PO-{date_part}-{base + i + 1:04d}" for i in range(n)]


def _add_to_cart(item_name: str, qty: int) -> None:
    cart = st.session_state.po_cart
    for line in cart:
        if line["item_name"] == item_name:
            line["quantity"] += int(qty)
            return
    cart.append({"item_name": item_name, "quantity": int(qty)})


def _cart_totals():
    enriched = []
    grand = 0.0
    for line in st.session_state.po_cart:
        rows = read_df(
            "SELECT supplier, supplier_price, category FROM inventory WHERE name = ?",
            (line["item_name"],),
        )
        if rows.empty:
            continue
        r = rows.iloc[0]
        unit_price = float(r["supplier_price"])
        line_total = unit_price * int(line["quantity"])
        grand += line_total
        enriched.append({
            "item_name": line["item_name"],
            "quantity": int(line["quantity"]),
            "supplier": r["supplier"],
            "unit_price": unit_price,
            "line_total": line_total,
            "category": r["category"],
        })
    return enriched, grand


def _generate_po_pdf(enriched_lines, po_numbers, dispatched_by_name):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.75 * inch, bottomMargin=0.75 * inch,
                            title="Purchase Order", author="CyncSupply")
    base = getSampleStyleSheet()
    brand_style = ParagraphStyle("Brand", parent=base["Title"], fontName=_FONT_BOLD,
                                 fontSize=24, textColor=colors.HexColor("#d32f2f"),
                                 alignment=TA_LEFT, spaceAfter=0, leading=28)
    po_title = ParagraphStyle("POTitle", parent=base["Heading1"], fontName=_FONT_BOLD,
                              fontSize=14, textColor=colors.HexColor("#111827"),
                              alignment=TA_LEFT, spaceAfter=14, leading=18)
    meta_label = ParagraphStyle("MetaLabel", parent=base["Normal"], fontName=_FONT_BOLD,
                                fontSize=9, textColor=colors.HexColor("#6b7280"))
    meta_value = ParagraphStyle("MetaValue", parent=base["Normal"], fontName=_FONT_REGULAR,
                                fontSize=11, textColor=colors.HexColor("#111827"))
    section_style = ParagraphStyle("Section", parent=base["Heading2"], fontName=_FONT_BOLD,
                                   fontSize=12, textColor=colors.HexColor("#111827"),
                                   spaceBefore=6, spaceAfter=6)
    signature_style = ParagraphStyle("Signature", parent=base["Normal"], fontName=_FONT_REGULAR,
                                     fontSize=10, textColor=colors.HexColor("#111827"))
    grand_style = ParagraphStyle("GrandTotal", parent=base["Normal"], fontName=_FONT_BOLD,
                                 fontSize=14, textColor=colors.HexColor("#d32f2f"),
                                 alignment=TA_RIGHT)
    cell_style = ParagraphStyle("Cell", parent=base["Normal"], fontName=_FONT_REGULAR,
                                fontSize=10, textColor=colors.HexColor("#111827"))

    by_supplier = {}
    for l in enriched_lines:
        by_supplier.setdefault(l["supplier"], []).append(l)
    story = []
    suppliers = list(by_supplier.items())

    for idx, (supplier, lines) in enumerate(suppliers):
        po_num = po_numbers[idx]
        subtotal = sum(x["line_total"] for x in lines)
        story.append(Paragraph("CYNCSUPPLY", brand_style))
        story.append(Paragraph("PURCHASE ORDER", po_title))

        meta_data = [
            [Paragraph("<b>PO Number</b>", meta_label), Paragraph(_esc(po_num), meta_value),
             Paragraph("<b>Date</b>", meta_label), Paragraph(today_str(), meta_value)],
            [Paragraph("<b>Supplier</b>", meta_label), Paragraph(_esc(supplier), meta_value),
             Paragraph("<b>Prepared by</b>", meta_label), Paragraph(_esc(dispatched_by_name), meta_value)],
            [Paragraph("<b>Status</b>", meta_label), Paragraph("Draft — Pending Dispatch", meta_value),
             Paragraph("<b>Total</b>", meta_label), Paragraph(f"₱{subtotal:,.2f}", meta_value)],
        ]
        meta_tbl = Table(meta_data, colWidths=[1.1 * inch, 2.3 * inch, 1.2 * inch, 2.4 * inch])
        meta_tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, 0), 0.3, colors.HexColor("#e5e7eb")),
            ("LINEBELOW", (0, 1), (-1, 1), 0.3, colors.HexColor("#e5e7eb")),
        ]))
        story.append(meta_tbl)
        story.append(Spacer(1, 18))
        story.append(Paragraph("Line Items", section_style))

        table_data = [["#", "Item", "Qty", "Unit Price", "Line Total"]]
        for i, l in enumerate(lines, start=1):
            table_data.append([str(i), Paragraph(_esc(l["item_name"]), cell_style),
                               str(l["quantity"]), f"₱{l['unit_price']:,.2f}", f"₱{l['line_total']:,.2f}"])
        table_data.append(["", "", "", "Subtotal", f"₱{subtotal:,.2f}"])

        tbl = Table(table_data, colWidths=[0.4 * inch, 3.0 * inch, 0.7 * inch, 1.3 * inch, 1.6 * inch])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("FONTNAME", (0, 1), (-1, -1), _FONT_REGULAR),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#e5e7eb")),
            ("FONTNAME", (0, -1), (-1, -1), _FONT_BOLD),
            ("BACKGROUND", (3, -1), (-1, -1), colors.HexColor("#f5f5f5")),
            ("LINEABOVE", (0, -1), (-1, -1), 1.2, colors.HexColor("#111827")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 40))

        sig_table = Table(
            [[Paragraph("____________________________", signature_style),
              Paragraph("____________________________", signature_style)],
             [Paragraph("<b>Authorized by</b>", meta_label),
              Paragraph("<b>Date received</b>", meta_label)]],
            colWidths=[3.5 * inch, 3.5 * inch])
        sig_table.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 2),
                                       ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(sig_table)
        if idx < len(suppliers) - 1:
            story.append(PageBreak())

    if len(suppliers) > 1:
        grand = sum(sum(x["line_total"] for x in lines) for _, lines in suppliers)
        story.append(Spacer(1, 20))
        story.append(Paragraph(f"<b>GRAND TOTAL (all suppliers): ₱{grand:,.2f}</b>", grand_style))

    doc.build(story)
    return buf.getvalue()


def render_po_module():
    st.title("📝 Automated Purchase Order Module")
    st.caption("Vendor routing · line-item totals · verification lock · PDF export.")

    prefill = st.session_state.pop("po_prefill", None)
    inv = read_df("SELECT * FROM inventory ORDER BY supplier, name")
    if inv.empty:
        st.info("No inventory to order.")
        return

    st.markdown("---")
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("1. Build Order Line Items")
        categories = sorted(inv["category"].unique().tolist())
        cat_pick = st.selectbox("Category", ["All"] + categories, key="po_cat")
        pool = inv if cat_pick == "All" else inv[inv["category"] == cat_pick]
        names = pool["name"].tolist()
        default_idx = names.index(prefill) if prefill and prefill in names else 0
        selected_item = st.selectbox("Select Item", names, index=default_idx, key="po_item")

        item_row = pool[pool["name"] == selected_item].iloc[0]
        unit_price = float(item_row["supplier_price"])
        vendors = vendors_for_item(selected_item)
        st.caption(
            f"🔀 Vendor routing — primary: **{item_row['supplier']}**"
            + (f" · alternates: {', '.join(vendors[1:])}" if len(vendors) > 1 else "")
        )
        st.caption(f"💵 Original supplier price: ₱{unit_price:,.2f}")

        qty = st.number_input("Quantity", min_value=1, value=50, key="po_qty")
        if st.button("➕ Add to Order", type="primary"):
            _add_to_cart(selected_item, int(qty))
            flash("success", f"Added {qty} × {selected_item} to order.")
            st.rerun()

        st.markdown("### 🛒 Order Cart")
        cart = st.session_state.po_cart
        if not cart:
            st.info("Cart empty. Add items above.")
        else:
            enriched, grand = _cart_totals()
            by_supplier = {}
            for l in enriched:
                by_supplier.setdefault(l["supplier"], []).append(l)
            for sup, lines in by_supplier.items():
                st.markdown(f"**🏭 {sup}**")
                for i, l in enumerate(lines):
                    c1, c2, c3 = st.columns([4, 2, 1])
                    c1.write(f"{l['item_name']}")
                    c2.write(f"{l['quantity']} × ₱{l['unit_price']:,.2f}  =  **₱{l['line_total']:,.2f}**")
                    if c3.button("🗑️", key=f"rm_{sup}_{i}", help="Remove line"):
                        for j, raw in enumerate(st.session_state.po_cart):
                            if raw["item_name"] == l["item_name"]:
                                st.session_state.po_cart.pop(j)
                                break
                        st.rerun()
                st.markdown("---")
            st.markdown(f"### **Grand Total: ₱{grand:,.2f}**")

    with col2:
        st.subheader("2. Purchase Order Summary")
        enriched, grand = _cart_totals()
        if not enriched:
            st.info("Add at least one line item to dispatch.")
            return

        by_supplier = {}
        for l in enriched:
            by_supplier.setdefault(l["supplier"], []).append(l)
        preview_numbers = _preview_po_numbers(len(by_supplier))

        st.markdown(f"**Vendor routing result:** {len(by_supplier)} PO(s) will be generated — one per supplier.")
        for i, (sup, lines) in enumerate(by_supplier.items()):
            subtotal = sum(x["line_total"] for x in lines)
            st.markdown(f"* `{preview_numbers[i]}` — **{sup}** — {len(lines)} line(s) — ₱{subtotal:,.2f}")

        st.markdown("---")
        st.markdown(f"### **Grand Total: ₱{grand:,.2f}**")
        st.caption("Calculated from original supplier wholesale rates (no VAT added).")

        st.markdown("### 📄 Purchase Order PDF")
        if not _PDF_OK:
            st.warning("⚠️ `reportlab` not installed — run `pip install reportlab`.")
        else:
            try:
                pdf_bytes = _generate_po_pdf(enriched, preview_numbers, st.session_state.logged_user["name"])
                pdf_name = (f"purchase_order_{preview_numbers[0]}.pdf"
                            if len(preview_numbers) == 1 else f"purchase_orders_{today_str()}.pdf")
                st.download_button(
                    f"📄 Download PO PDF ({len(by_supplier)} page{'s' if len(by_supplier) > 1 else ''})",
                    data=pdf_bytes, file_name=pdf_name, mime="application/pdf",
                    type="secondary", use_container_width=True, key="po_pdf_download")
                st.caption("One page per supplier, with PO numbers, line items, subtotals, signature lines, and grand total.")
            except Exception as e:
                st.error(f"PDF generation failed: {type(e).__name__}: {e}")

        st.markdown("---")
        st.subheader("3. Verification Lock & Dispatch")
        lock = st.checkbox("🔒 I certify that I have verified the quantities and original supplier prices above.")

        b1, b2 = st.columns(2)
        with b1:
            if st.button("🚀 Dispatch All POs", type="primary", disabled=not lock, use_container_width=True):
                dispatched = []
                for sup, lines in by_supplier.items():
                    po_num = next_po_number()
                    subtotal = sum(x["line_total"] for x in lines)
                    exec_sql(
                        "INSERT INTO purchase_orders (po_number, supplier, total, status, date, dispatched_by) "
                        "VALUES (?,?,?,?,?,?)",
                        (po_num, sup, subtotal, "Dispatched to Supplier", today_str(), st.session_state.logged_user["name"]))
                    for l in lines:
                        exec_sql(
                            "INSERT INTO po_line_items (po_number, item_name, quantity, unit_price, line_total) "
                            "VALUES (?,?,?,?,?)",
                            (po_num, l["item_name"], l["quantity"], l["unit_price"], l["line_total"]))
                        exec_sql(
                            "INSERT INTO pending_deliveries (po_number, supplier, item_name, ordered, eta, added_by) "
                            "VALUES (?,?,?,?,?,?)",
                            (po_num, sup, l["item_name"], l["quantity"],
                             str(datetime.date.today() + datetime.timedelta(days=3)), st.session_state.logged_user["name"]))
                    dispatched.append(po_num)
                st.session_state.po_cart = []
                flash("success", f"Dispatched {len(dispatched)} PO(s): {', '.join(dispatched)}")
                st.rerun()
        with b2:
            if st.button("🧹 Clear Cart", use_container_width=True):
                st.session_state.po_cart = []
                st.rerun()

    st.markdown("---")
    st.subheader("📋 Purchase Order Dispatch History")
    pos = read_df("SELECT * FROM purchase_orders ORDER BY date DESC, po_number DESC")
    if pos.empty:
        st.info("No purchase orders generated yet.")
    else:
        for _, po in pos.iterrows():
            with st.expander(f"**{po['po_number']}** — {po['supplier']} — ₱{po['total']:,.2f} — {po['status']}"):
                st.caption(f"Dispatched {po['date']} by {po['dispatched_by']}")
                lines = read_df("SELECT item_name, quantity, unit_price, line_total FROM po_line_items WHERE po_number = ?", (po["po_number"],))
                lines = lines.rename(columns={"item_name": "Item", "quantity": "Qty", "unit_price": "Unit Price", "line_total": "Line Total"})
                st.dataframe(lines.style.format({"Unit Price": "₱{:,.2f}", "Line Total": "₱{:,.2f}"}), use_container_width=True, hide_index=True)