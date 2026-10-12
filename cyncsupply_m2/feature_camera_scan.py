import streamlit as st
import numpy as np

try:
    import cv2
    _CV2_OK = True
except Exception:
    _CV2_OK = False

try:
    import zxingcpp
    _ZXING_OK = True
except Exception:
    _ZXING_OK = False

from db import read_df, exec_sql, today_str, now_str, flash


# ==========================================
# AUTO-MIGRATION
# ==========================================
def _ensure_sold_columns():
    try:
        exec_sql("ALTER TABLE receiving_tags ADD COLUMN sold INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        exec_sql("ALTER TABLE receiving_tags ADD COLUMN sold_at TEXT")
    except Exception:
        pass
    try:
        exec_sql("UPDATE receiving_tags SET sold = 0 WHERE sold IS NULL")
    except Exception:
        pass


# ==========================================
# BARCODE DECODING
# ==========================================
def _decode_from_bytes(bytes_data: bytes):
    arr = np.frombuffer(bytes_data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR) if _CV2_OK else None
    results, seen = [], set()

    def _add(code, typ):
        code = str(code).strip()
        if code and code not in seen:
            seen.add(code)
            results.append((code, typ))

    if img is None:
        return results

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    variants = [gray]

    h, w = gray.shape
    up = gray
    if max(h, w) < 2400:
        scale = 2400 / max(h, w)
        up = cv2.resize(gray, (int(w * scale), int(h * scale)),
                        interpolation=cv2.INTER_CUBIC)
        variants.append(up)

    sharp = cv2.addWeighted(gray, 1.6, cv2.GaussianBlur(gray, (0, 0), 3), -0.6, 0)
    variants.append(sharp)

    thresh = cv2.adaptiveThreshold(up, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 51, 15)
    variants.append(thresh)

    _, otsu = cv2.threshold(up, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(otsu)

    if _ZXING_OK:
        for v in variants:
            try:
                for b in zxingcpp.read_barcodes(v):
                    if b.text:
                        _add(b.text, str(b.format))
                if results:
                    break
            except Exception:
                continue

    if not results and _CV2_OK:
        for v in variants:
            try:
                detector = cv2.barcode.BarcodeDetector()
                ok, infos, types, _ = detector.detectAndDecode(v)
                if ok:
                    for i, t in zip(infos, types):
                        if i:
                            _add(i, str(t) if t else "Barcode")
                if results:
                    break
            except Exception:
                continue

    return results


# ==========================================
# SELL ONE UNIT
# ==========================================
def _sell_item(barcode: str):
    tag_rows = read_df(
        "SELECT tag_id, item_name, supplier, COALESCE(sold, 0) AS sold, sold_at "
        "FROM receiving_tags WHERE tag_id = ?",
        (barcode,),
    )
    if tag_rows.empty:
        return False, f"Barcode `{barcode}` is not registered in the system."

    tag = tag_rows.iloc[0]
    item_name = str(tag["item_name"]).strip()

    if int(tag["sold"]) == 1:
        return False, (
            f"❌ **EXPIRED** — Barcode `{barcode}` was already sold on "
            f"`{tag['sold_at']}`. It cannot be used again."
        )

    inv_rows = read_df(
        "SELECT item_id, name, category, quantity FROM inventory WHERE name = ?",
        (item_name,),
    )
    if inv_rows.empty:
        inv_rows = read_df(
            "SELECT item_id, name, category, quantity FROM inventory "
            "WHERE TRIM(LOWER(name)) = TRIM(LOWER(?))",
            (item_name,),
        )
    if inv_rows.empty:
        short = item_name[:20].lower()
        inv_rows = read_df(
            "SELECT item_id, name, category, quantity FROM inventory "
            "WHERE LOWER(name) LIKE ?",
            (f"%{short}%",),
        )

    if inv_rows.empty:
        return False, (
            f"⚠️ Item `{item_name}` from the barcode is not in inventory. "
            f"Rename the inventory item or regenerate the barcode."
        )

    inv = inv_rows.iloc[0]
    item_id = inv["item_id"]
    real_name = inv["name"]
    category = inv["category"]
    old_qty = int(inv["quantity"])

    if old_qty <= 0:
        return False, f"❌ **Out of stock** — {real_name} has 0 units left."

    new_qty = old_qty - 1
    sold_time = now_str()

    exec_sql(
        "UPDATE inventory SET quantity = ? WHERE item_id = ?",
        (new_qty, item_id),
    )

    verify = read_df("SELECT quantity FROM inventory WHERE item_id = ?", (item_id,))
    verified = int(verify.iloc[0]["quantity"]) if not verify.empty else None

    if verified != new_qty:
        return False, (
            f"⚠️ Inventory update failed. Expected {new_qty}, database shows "
            f"{verified}. Nothing was recorded."
        )

    exec_sql(
        "UPDATE receiving_tags SET sold = 1, sold_at = ? WHERE tag_id = ?",
        (sold_time, barcode),
    )

    exec_sql(
        "INSERT INTO sales (date, item_id, item_name, units, category, performed_by) "
        "VALUES (?,?,?,?,?,?)",
        (today_str(), item_id, real_name, 1, category,
         st.session_state.logged_user["name"]),
    )

    return True, (
        f"**{real_name}** sold.\n\n"
        f"Inventory: **{old_qty} → {new_qty}** units (−1)\n\n"
        f"Barcode `{barcode}` expired."
    )


# ==========================================
# MAIN MODULE
# ==========================================
def render_camera_scan_module():
    st.title("📷 Barcode Scanner")
    st.caption("Scan a barcode to sell 1 unit. The barcode expires after use.")

    if "_sold_columns_ready" not in st.session_state:
        with st.spinner("Preparing barcode tracking…"):
            _ensure_sold_columns()
        st.session_state["_sold_columns_ready"] = True

    last = st.session_state.pop("_scan_result", None)
    if last:
        if last["ok"]:
            st.success(last["msg"])
        else:
            st.error(last["msg"])

    st.markdown("---")

    if not _CV2_OK:
        st.error("⚠️ `opencv-contrib-python` is not installed.")
        return

    method = st.radio(
        "**Input method:**",
        ["📸 Use Camera", "📁 Upload Image"],
        horizontal=True,
        key="scan_method",
    )

    picture = None
    if method == "📸 Use Camera":
        picture = st.camera_input("Scan item barcode", key="camera_scan")
    else:
        uploaded = st.file_uploader(
            "Choose an image",
            type=["png", "jpg", "jpeg", "webp", "bmp"],
            key="barcode_upload",
        )
        if uploaded is not None:
            st.image(uploaded, width=380)
            picture = uploaded

    if picture is None:
        _render_history()
        return

    with st.spinner("Reading barcode…"):
        results = _decode_from_bytes(picture.getvalue())

    if not results:
        st.error("❌ No barcode detected. Try a clearer image.")
        manual = st.text_input("Or type the barcode ID:",
                               key="manual_tag", placeholder="CR-7035-001")
        if not manual:
            _render_history()
            return
        results = [(manual.strip(), "Manual")]

    code, typ = results[0]
    st.info(f"Scanned ({typ}): `{code}`")

    ok, msg = _sell_item(code)
    st.session_state["_scan_result"] = {"ok": ok, "msg": msg}
    if ok:
        st.balloons()
    st.rerun()


# ==========================================
# HISTORY + INVENTORY SNAPSHOT
# ==========================================
def _render_history():
    st.markdown("---")
    st.subheader("🧾 Recent Sales via Barcode")
    log = read_df(
        "SELECT sold_at AS sold_time, item_name, tag_id "
        "FROM receiving_tags WHERE sold = 1 AND sold_at IS NOT NULL "
        "ORDER BY sold_at DESC LIMIT 10"
    )
    if log.empty:
        st.caption("No barcode sales yet.")
    else:
        st.dataframe(
            log.rename(columns={"sold_time": "Time", "item_name": "Item",
                                "tag_id": "Barcode"}),
            use_container_width=True, hide_index=True,
        )

    st.markdown("---")
    st.subheader("📦 Current Inventory Snapshot")
    inv = read_df(
        "SELECT name, quantity, threshold FROM inventory ORDER BY name"
    )
    if inv.empty:
        st.caption("Inventory empty.")
    else:
        st.dataframe(
            inv.rename(columns={"name": "Item", "quantity": "On Hand",
                                "threshold": "Threshold"}),
            use_container_width=True, hide_index=True,
        )