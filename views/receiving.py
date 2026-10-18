import streamlit as st
import streamlit.components.v1 as components
import html as _html
import random
import base64
import os
import zipfile
from io import BytesIO

from models.connection import read_df, exec_sql, today_str, now_str, flash

try:
    import barcode
    from barcode.writer import SVGWriter, ImageWriter
    _BARCODE_OK = True
except Exception:
    _BARCODE_OK = False

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_OK = True
except Exception:
    _PIL_OK = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    _PDF_OK = True
except Exception:
    _PDF_OK = False


# ==========================================
# FONT REGISTRATION (for Peso symbol)
# ==========================================
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


# ==========================================
# BARCODE — SVG (on-screen preview)
# ==========================================
def generate_barcode_svg(tag_id: str) -> str:
    if _BARCODE_OK:
        writer = SVGWriter()
        writer.set_options({
            "module_width": 0.6,
            "module_height": 18.0,
            "font_size": 14,
            "text_distance": 5.0,
            "background": "white",
            "foreground": "black",
        })
        code = barcode.get("code128", tag_id, writer=writer)
        buf = BytesIO()
        code.write(buf)
        return buf.getvalue().decode("utf-8")

    # Fallback — decorative bars
    random.seed(sum(ord(c) for c in tag_id))
    x, bars = 10, ""
    for _ in range(32):
        w = random.choice([2, 4, 5])
        bars += f'<rect x="{x}" y="10" width="{w}" height="50" fill="#111827"/>'
        x += w + random.choice([2, 3])
    return (
        f'<svg width="260" height="80" xmlns="http://www.w3.org/2000/svg" '
        f'style="background:#fff;border:1px solid #ccc;padding:4px;border-radius:4px;">'
        f'{bars}<text x="130" y="72" font-family="monospace" font-size="11" '
        f'fill="#111827" text-anchor="middle">{tag_id}</text></svg>'
    )


# ==========================================
# BARCODE — PIL Image (for print sheet + ZIP)
# ==========================================
def _barcode_pil(tag_id: str, target_width_px: int):
    writer = ImageWriter()
    writer.set_options({
        "module_width": 0.4,
        "module_height": 10.0,
        "font_size": 12,
        "text_distance": 3.0,
        "quiet_zone": 3.0,
        "background": "white",
        "foreground": "black",
        "write_text": False,
    })
    code = barcode.get("code128", tag_id, writer=writer)
    buf = BytesIO()
    code.write(buf)
    buf.seek(0)
    img = Image.open(buf).convert("RGB")
    ratio = target_width_px / img.width
    new_h = int(img.height * ratio)
    resample = getattr(Image, "Resampling", Image).LANCZOS
    return img.resize((target_width_px, new_h), resample)


def _barcode_png(tag_id: str, target_width_px: int) -> bytes:
    img = _barcode_pil(tag_id, target_width_px)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ==========================================
# FONT LOADER (for individual tag PNG)
# ==========================================
def _load_font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf"   if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf"  if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibrib.ttf"  if bold else "C:/Windows/Fonts/calibri.ttf",
        "/Library/Fonts/Arial Bold.ttf"  if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(text, font, max_width, draw):
    text = str(text)
    words = text.split()
    lines, current = [], ""
    for w in words:
        trial = (current + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            if draw.textlength(w, font=font) > max_width:
                chunk = ""
                for ch in w:
                    if draw.textlength(chunk + ch, font=font) <= max_width:
                        chunk += ch
                    else:
                        lines.append(chunk)
                        chunk = ch
                current = chunk
            else:
                current = w
    if current:
        lines.append(current)
    return lines


# ==========================================
# INDIVIDUAL TAG → PNG (for ZIP download)
# ==========================================
def generate_tag_png(tag: dict, width_in: float = 1.375, height_in: float = 2.75,
                     dpi: int = 600):
    if not (_PIL_OK and _BARCODE_OK):
        return None

    W = int(round(width_in * dpi))
    H = int(round(height_in * dpi))
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    f_header = _load_font(28, bold=True)
    f_item   = _load_font(22, bold=True)
    f_body   = _load_font(18)
    f_small  = _load_font(15)
    f_stamp  = _load_font(14, bold=True)
    f_tagid  = _load_font(22, bold=True)

    pad = 18
    inner_w = W - 2 * pad
    y = pad

    draw.text((pad, y), "CYNCSUPPLY", fill="#d32f2f", font=f_header)
    y += 30
    draw.text((pad, y), "BARCODE LABEL", fill="#d32f2f", font=f_header)
    y += 34
    draw.line([(pad, y), (W - pad, y)], fill="#d32f2f", width=3)
    y += 8

    for line in _wrap_text(tag["item_name"], f_item, inner_w, draw)[:2]:
        draw.text((pad, y), line, fill="#111827", font=f_item)
        y += 26
    y += 6

    def field(label, value):
        nonlocal y
        draw.text((pad, y), label, fill="#6b7280", font=f_small)
        y += 18
        for line in _wrap_text(value, f_body, inner_w, draw)[:1]:
            draw.text((pad, y), line, fill="#111827", font=f_body)
            y += 22
        y += 4

    field("UNIT", tag.get("unit_label", "1 of 1"))
    field("SUPPLIER", tag["supplier"])
    field("INSPECTOR", tag["inspector"])
    field("DATE/TIME", tag["timestamp"])

    y += 10
    barcode_w = inner_w
    bc_img = _barcode_pil(tag["tag_id"], barcode_w)
    bc_x = (W - bc_img.width) // 2
    img.paste(bc_img, (bc_x, y))
    y += bc_img.height + 8

    tw = draw.textlength(tag["tag_id"], font=f_tagid)
    draw.text(((W - tw) / 2, y), tag["tag_id"], fill="#111827", font=f_tagid)
    y += 28

    stamp_text = "AUDITED & VERIFIED INTAKE"
    sw = draw.textlength(stamp_text, font=f_stamp)
    stamp_x = (W - sw) / 2
    stamp_y = H - 32
    draw.rectangle([stamp_x - 8, stamp_y - 3, stamp_x + sw + 8, stamp_y + 18],
                   outline="#2e7d32", width=3)
    draw.text((stamp_x, stamp_y + 1), stamp_text, fill="#2e7d32", font=f_stamp)

    buf = BytesIO()
    img.save(buf, format="PNG", dpi=(dpi, dpi))
    return buf.getvalue()


# ==========================================
# A4 PRINT SHEET PDF — exactly 6 labels per page
# ==========================================
def _build_a4_pdf(tags: list, item_name: str):
    if not (_PDF_OK and _PIL_OK and _BARCODE_OK):
        return None

    buf = BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Barcodes — {item_name}")
    c.setAuthor("CyncSupply")

    A4_W, A4_H = A4
    margin = 12 * mm
    cols, rows = 2, 3
    per_page = cols * rows

    cell_w = (A4_W - 2 * margin) / cols
    cell_h = (A4_H - 2 * margin) / rows
    pad = 4 * mm

    for i, tag in enumerate(tags):
        pos = i % per_page
        if pos == 0 and i > 0:
            c.showPage()

        col = pos % cols
        row = pos // cols

        x_left = margin + col * cell_w
        y_bottom = A4_H - margin - (row + 1) * cell_h

        # Dashed border
        c.saveState()
        c.setStrokeColor(colors.HexColor("#d1d5db"))
        c.setLineWidth(0.5)
        c.setDash(2, 2)
        c.rect(x_left, y_bottom, cell_w, cell_h, stroke=1, fill=0)
        c.restoreState()

        cx = x_left + cell_w / 2
        inner_top = y_bottom + cell_h - pad
        inner_w = cell_w - 2 * pad

        # Item name
        c.setFont(_FONT_BOLD, 9)
        c.setFillColor(colors.HexColor("#111827"))
        short_name = item_name if len(item_name) <= 42 else item_name[:39] + "…"
        name_y = inner_top - 4 * mm
        c.drawCentredString(cx, name_y, short_name)

        # Barcode image
        bc_img = _barcode_pil(tag["tag_id"], 700)
        img_buf = BytesIO()
        bc_img.save(img_buf, format="PNG")
        img_buf.seek(0)
        img_reader = ImageReader(img_buf)

        img_max_h = cell_h - 2 * pad - 28 * mm
        img_max_w = inner_w
        aspect = bc_img.width / bc_img.height
        img_w = img_max_w
        img_h = img_w / aspect
        if img_h > img_max_h:
            img_h = img_max_h
            img_w = img_h * aspect

        img_x = cx - img_w / 2
        img_y = name_y - 5 * mm - img_h
        c.drawImage(img_reader, img_x, img_y, width=img_w, height=img_h)

        # Tag ID
        c.setFont(_FONT_BOLD, 11)
        c.setFillColor(colors.HexColor("#111827"))
        tagid_y = img_y - 5 * mm
        c.drawCentredString(cx, tagid_y, tag["tag_id"])

        # Unit label
        c.setFont(_FONT_REGULAR, 8)
        c.setFillColor(colors.HexColor("#6b7280"))
        unit_y = y_bottom + pad + 1 * mm
        c.drawCentredString(cx, unit_y,
                            f"Unit {tag['unit_index']} of {tag['total_units']}")

    c.save()
    return buf.getvalue()


# ==========================================
# HTML PRINT SHEET (inline preview)
# ==========================================
def _build_print_sheet(tags: list, item_name: str):
    e = _html.escape
    labels_html = ""
    for t in tags:
        labels_html += f"""
        <div class="label">
            <div class="label-name">{e(item_name)}</div>
            <div class="label-svg">{t['svg']}</div>
            <div class="label-id">{e(t['tag_id'])}</div>
            <div class="label-num">Unit {t['unit_index']} of {t['total_units']}</div>
        </div>
        """
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Barcodes — {e(item_name)}</title>
<style>
  @page {{ size: A4 portrait; margin: 10mm; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: system-ui, sans-serif; background: #ffffff; }}
  .sheet {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 4mm;
    padding: 4mm;
  }}
  .label {{
    border: 0.5pt dashed #bbb;
    padding: 4mm 3mm;
    text-align: center;
    page-break-inside: avoid;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    min-height: 80mm;
    background: #ffffff;
  }}
  .label-name {{
    font-size: 11pt;
    font-weight: 700;
    line-height: 1.2;
    margin-bottom: 3mm;
    max-height: 20mm;
    overflow: hidden;
    color: #111827;
  }}
  .label-svg svg {{ max-width: 100%; height: auto; }}
  .label-id {{
    font-family: monospace;
    font-size: 11pt;
    font-weight: 700;
    margin-top: 2mm;
    letter-spacing: 1px;
    color: #111827;
  }}
  .label-num {{
    font-size: 9pt;
    color: #555;
    margin-top: 1mm;
  }}
  @media print {{
    body {{ margin: 0; }}
    .sheet {{ padding: 0; }}
  }}
</style></head><body>
<div class="sheet">{labels_html}</div>
<script>
  // Auto-print when opened in print mode (passed via ?print=1)
  if (window.location.search.includes('print=1')) {{
    window.onload = function() {{
      setTimeout(function() {{ window.print(); }}, 300);
    }};
  }}
</script>
</body></html>"""


def _build_zip(pngs: dict) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for tid, data in pngs.items():
            zf.writestr(f"{tid}.png", data)
    return buf.getvalue()


# ==========================================
# MAIN MODULE
# ==========================================
MAX_PER_BATCH = 200


def render_receiving_module():
    st.title("🏷️ Barcode Generator")
    st.markdown(
        "Generate **one unique barcode per physical unit**. Print, attach to the "
        "item, then scan it later in the **Barcode Scanner** to sell it."
    )

    prefill = st.session_state.get("receiving_prefill")

    if prefill:
        st.markdown(
            f"<div class='flow-banner'>"
            f"📥 <b>Labelling from PO <code>{_html.escape(str(prefill['po_number']))}</code></b><br>"
            f"<b>{_html.escape(prefill['item_name'])}</b> — "
            f"{prefill['quantity']} units from "
            f"<b>{_html.escape(prefill['supplier'])}</b><br>"
            f"Generate one barcode per unit and print them."
            f"</div>",
            unsafe_allow_html=True,
        )
        if "rcv_supplier_input" not in st.session_state:
            st.session_state["rcv_supplier_input"] = prefill.get(
                "supplier", "Holcim Direct Phil")
        if "rcv_item_input" not in st.session_state:
            st.session_state["rcv_item_input"] = prefill.get("item_name")
        if "rcv_qty_input" not in st.session_state:
            st.session_state["rcv_qty_input"] = int(prefill.get("quantity", 50))
        if "rcv_note_input" not in st.session_state:
            st.session_state["rcv_note_input"] = prefill.get("note", "")

    st.info(
        "ℹ️ Scanning the barcode in the **Barcode Scanner** module sells the item."
    )

    if not _BARCODE_OK:
        st.warning("⚠️ `python-barcode` not installed.")
    if not _PIL_OK:
        st.warning("⚠️ `pillow` not installed — PNG/PDF output unavailable.")
    if not _PDF_OK:
        st.warning("⚠️ `reportlab` not installed — A4 PDF unavailable.")

    st.markdown("---")
    st.subheader("🧾 Batch Setup")
    col1, col2 = st.columns([1, 1])

    with col1:
        inv = read_df("SELECT name FROM inventory ORDER BY name")
        inv_names = inv["name"].tolist()
        default_item = st.session_state.get("rcv_item_input")
        default_idx = inv_names.index(default_item) if default_item in inv_names else 0

        supplier_name = st.text_input(
            "Supplier / Distributor Name",
            value="Holcim Direct Phil",
            key="rcv_supplier_input",
        )
        item_to_receive = st.selectbox(
            "Item to Label", inv_names, index=default_idx, key="rcv_item_input",
        )
        qty_units = st.number_input(
            "How many individual units to label?",
            min_value=1, max_value=MAX_PER_BATCH, value=10, step=1,
            key="rcv_qty_input",
        )
        inspector_name = st.text_input(
            "Yard Clerk / Inspector Name",
            st.session_state.logged_user["name"],
            key="rcv_inspector_input",
        )
        delivery_note = st.text_area(
            "Delivery Note / Batch Ref #",
            "Delivery Truck License: ABC-1234",
            key="rcv_note_input",
        )
        generate = st.button("🏷️ Generate Barcodes for Each Item",
                             type="primary", use_container_width=True)

    with col2:
        st.subheader("📦 Batch Preview")
        st.markdown(f"""
        * **Item:** {item_to_receive}
        * **Quantity:** {int(qty_units)} unit(s)
        * **Supplier:** {supplier_name}
        * **Will create:** {int(qty_units)} unique barcode(s)
        * **Barcode format:** `CR-XXXX-NNN`
        * **Print layout:** **6 barcodes per A4 page** (2 × 3 grid)
        """)
        st.caption(
            "Each unit gets its own serial (001, 002, …). Scanning it in the "
            "**Barcode Scanner** identifies that specific physical item and "
            "sells it."
        )

    if generate:
        with st.spinner(f"Generating {int(qty_units)} barcodes…"):
            batch_num = random.randint(1000, 9999)
            ts = now_str()

            tag_ids = [
                f"CR-{batch_num}-{i:03d}"
                for i in range(1, int(qty_units) + 1)
            ]

            for tid in tag_ids:
                exec_sql(
                    "INSERT INTO receiving_tags "
                    "(tag_id, item_name, quantity, inspector, supplier, timestamp, ref_note) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (tid, item_to_receive, 1, inspector_name, supplier_name, ts,
                     delivery_note),
                )

            tags_for_sheet = []
            for i, tid in enumerate(tag_ids, start=1):
                tags_for_sheet.append({
                    "tag_id": tid,
                    "svg": generate_barcode_svg(tid),
                    "unit_index": i,
                    "total_units": int(qty_units),
                })

            pngs = {}
            if _PIL_OK:
                for i, tid in enumerate(tag_ids, start=1):
                    pngs[tid] = generate_tag_png({
                        "tag_id": tid,
                        "item_name": item_to_receive,
                        "qty": 1,
                        "supplier": supplier_name,
                        "inspector": inspector_name,
                        "timestamp": ts,
                        "note": delivery_note,
                        "unit_label": f"{i} of {int(qty_units)}",
                        "svg": tags_for_sheet[i - 1]["svg"],
                    })

            zip_bytes = _build_zip(pngs) if pngs else None
            print_html = _build_print_sheet(tags_for_sheet, item_to_receive)

            a4_pdf = None
            if _PDF_OK and _PIL_OK:
                try:
                    a4_pdf = _build_a4_pdf(tags_for_sheet, item_to_receive)
                except Exception as e:
                    st.warning(f"A4 PDF generation failed: {type(e).__name__}: {e}")

            st.session_state.current_batch = {
                "item_name": item_to_receive,
                "tag_ids": tag_ids,
                "tags_for_sheet": tags_for_sheet,
                "zip_bytes": zip_bytes,
                "print_html": print_html,
                "a4_pdf": a4_pdf,
                "quantity": int(qty_units),
                "supplier": supplier_name,
                "inspector": inspector_name,
                "note": delivery_note,
                "timestamp": ts,
            }

            st.session_state.pop("receiving_prefill", None)
            for k in ["rcv_supplier_input", "rcv_item_input", "rcv_qty_input",
                      "rcv_note_input"]:
                st.session_state.pop(k, None)

            st.session_state.pop("_show_html_preview", None)

            flash("success",
                  f"Generated {len(tag_ids)} barcodes for {item_to_receive}.")
            st.rerun()

    # ==========================================
    # CURRENT BATCH
    # ==========================================
    batch = st.session_state.get("current_batch")
    if batch:
        st.markdown("---")
        st.subheader(f"✅ Batch: {batch['item_name']} — {batch['quantity']} barcodes")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total units", batch["quantity"])
        c2.metric("Tag prefix", batch["tag_ids"][0].rsplit("-", 1)[0])
        c3.metric("Generated", batch["timestamp"][-8:])
        c4.metric("Pages (A4)", f"{-(-batch['quantity'] // 6)}")

        st.markdown("### 📄 Download")
        d1, d2, d3 = st.columns(3)

        with d1:
            if batch.get("a4_pdf"):
                st.download_button(
                    "📄 Download A4 PDF (6/page)",
                    data=batch["a4_pdf"],
                    file_name=f"barcodes_{batch['tag_ids'][0]}_A4.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary",
                )
            else:
                st.button("📄 A4 PDF unavailable",
                          disabled=True, use_container_width=True)

        with d2:
            if batch["zip_bytes"]:
                st.download_button(
                    f"⬇️ ZIP ({batch['quantity']} PNGs)",
                    data=batch["zip_bytes"],
                    file_name=f"barcodes_{batch['tag_ids'][0]}.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
            else:
                st.button("⬇️ ZIP unavailable",
                          disabled=True, use_container_width=True)

        with d3:
            # Toggle inline HTML preview (works around Chrome's data: URL block)
            if st.button("🖨️ Show HTML Preview",
                         use_container_width=True,
                         key=f"toggle_html_{batch['tag_ids'][0]}"):
                st.session_state["_show_html_preview"] = True
                st.rerun()

        st.caption(
            f"📐 A4 PDF: **6 labels per page** — 2 columns × 3 rows. "
            f"{batch['quantity']} labels → "
            f"{-(-batch['quantity'] // 6)} page(s)."
        )

        # ==========================================
        # INLINE HTML PREVIEW (fixed)
        # ==========================================
        if st.session_state.get("_show_html_preview"):
            st.markdown("### 👁️ HTML Preview")

            toolbar_left, toolbar_right = st.columns([3, 1])
            with toolbar_left:
                st.caption(
                    "Preview of the barcode sheet. Use the A4 PDF button above "
                    "for printing — it produces a cleaner, higher-quality sheet."
                )
            with toolbar_right:
                if st.button("✖ Close Preview",
                             use_container_width=True,
                             key="close_html_preview"):
                    st.session_state.pop("_show_html_preview", None)
                    st.rerun()

            # Render the HTML inline using Streamlit's component renderer.
            # This bypasses Chrome's `data:` URL block.
            components.html(
                batch["print_html"],
                height=1000,
                scrolling=True,
            )

        with st.expander("🧹 Clear this batch"):
            if st.button("Clear Batch", use_container_width=True):
                st.session_state.pop("current_batch", None)
                st.session_state.pop("_show_html_preview", None)
                st.rerun()

        st.markdown("### 👀 Preview (first 6 labels)")
        preview = batch["tags_for_sheet"][:6]
        cols = st.columns(3)
        for i, t in enumerate(preview):
            with cols[i % 3]:
                st.markdown(
                    f"<div style='border:1px solid #ddd;border-radius:8px;"
                    f"padding:10px;text-align:center;background:#fffef5;'>"
                    f"<div style='font-size:12px;font-weight:700;"
                    f"margin-bottom:6px;'>{_html.escape(batch['item_name'])}</div>"
                    f"<div>{t['svg']}</div>"
                    f"<div style='font-family:monospace;font-size:12px;"
                    f"font-weight:700;margin-top:6px;'>"
                    f"{_html.escape(t['tag_id'])}</div>"
                    f"<div style='font-size:10px;color:#666;'>"
                    f"Unit {t['unit_index']} of {t['total_units']}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        if batch["quantity"] > 6:
            st.caption(f"…and {batch['quantity'] - 6} more in the PDF / ZIP.")

    # ==========================================
    # RECENT BARCODES
    # ==========================================
    st.markdown("---")
    st.subheader("📋 Recent Individual Barcodes")
    hist = read_df(
        "SELECT tag_id, item_name, inspector, supplier, timestamp "
        "FROM receiving_tags ORDER BY timestamp DESC LIMIT 30"
    )
    if hist.empty:
        st.caption("No barcodes generated yet.")
    else:
        st.dataframe(
            hist.rename(columns={
                "tag_id": "Barcode ID", "item_name": "Item",
                "inspector": "Inspector", "supplier": "Supplier",
                "timestamp": "Issued",
            }),
            use_container_width=True, hide_index=True,
        )