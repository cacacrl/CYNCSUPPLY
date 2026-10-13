# 📦 CYNCSUPPLY

CyncSupply is a Python/Streamlit inventory system for hardware stores. It tracks stock in real time across laptop, tablet, and phone, uses per-unit barcodes to prevent theft and double-selling, auto-generates purchase orders, and delivers sales analytics.

---

## 🚀 Main Features

- **🔐 Role-Based Authentication** — Login/Signup with PBKDF2-hashed passwords. Four roles: System Admin, Inventory Manager, Yard Clerk, Sales Analyst.
- **📊 Live Dashboard** — Real-time KPIs, category health tiles, sales charts, and reorder queue with 5-second auto-refresh.
- **🧱 Categorized Inventory** — Color-coded stock levels (red/amber/green), category filter, and manual refresh button.
- **📝 Automated Purchase Order Module** — Multi-line cart with vendor routing, verification lock, and PDF export (one page per supplier).
- **📦 Pending Deliveries Checklist** — Verify physical receipts, credit inventory, and hand off to the barcode generator.
- **🏷️ Barcode Generator** — Creates one unique Code128 barcode per physical unit. Downloadable as an A4 PDF print sheet (6 labels per page) or ZIP of individual PNGs.
- **📷 Barcode Scanner** — Camera or upload scanning. Each scan sells one unit, decrements stock, and expires the barcode (blocks repeat scans).
- **📈 Item Sales Analytics** — Velocity trends, turnover tiers, top-selling items, and category sales ratios.

---

## 🔧 Other Features

- **📦 Product Management** — Add, edit, and delete inventory products with validation.
- **⚡ Live Low-Stock Alerts** — Persistent red banner and sidebar quick-order buttons that trigger when stock falls to or below threshold.
- **🧾 Per-Unit Audit Trail** — Every delivery and sale is logged with the user, timestamp, and item details.
- **📱 Multi-Device Support** — Responsive layout for desktop, laptop, tablet, and phone.
- **🛡️ Anti-Theft Tagging** — Printed receiving tags physically attached to each item prove verified intake.
- **📄 Auto-Generated PDFs** — Purchase orders and barcode label sheets produced on demand via ReportLab.
- **🔄 Cross-Device Sync** — All devices share live data through Supabase PostgreSQL.
- **🧩 Modular Architecture** — Each feature is a self-contained module with a single public `render()` function.
- **⚙️ Auto-Migration** — Database columns are created automatically on first load (no manual SQL required).

---

## 🛠️ Technologies Used

### Core
- **Python 3.12** — Main programming language
- **Streamlit** — Web interface framework

### Database & Persistence
- **Supabase (PostgreSQL)** — Cloud database (production)
- **SQLite** — Local development fallback
- **SQLAlchemy 2.x** — Database abstraction layer
- **psycopg (psycopg3)** — PostgreSQL driver
- **python-dotenv** — Environment variable loader
- **pandas** — Data manipulation

### Barcode & Image Processing
- **python-barcode** — Code128 barcode generation (SVG + PNG)
- **zxing-cpp** — High-accuracy barcode decoder
- **OpenCV (opencv-contrib-python)** — Image preprocessing + secondary decoder
- **NumPy** — Image array operations

### PDF & Rendering
- **ReportLab** — Purchase Order and A4 label PDF generation
- **Pillow (PIL)** — Label image rendering at 600 DPI

### Security (Python Standard Library)
- **hashlib** — PBKDF2-HMAC-SHA256 password hashing (200,000 iterations)
- **hmac** — Constant-time password comparison
- **base64** — Salt and hash encoding
- **os.urandom** — Cryptographic salt generation

### Networking & Deployment
- **ngrok** — HTTPS tunnel for mobile camera access
- **Windows Firewall Rule** — Allows LAN access on port 8501

### Standard Library Modules
- `os`, `datetime`, `random`, `io.BytesIO`, `zipfile`, `html`, `contextlib`, `zoneinfo`

---

## 🧬 OOP Principles Applied (with Evidence)

All four core OOP principles are applied in CyncSupply. Each principle is backed by actual code in specific files.

---

### 1️⃣ Encapsulation

**Definition:** Hiding internal implementation details and exposing only what's needed through a controlled interface.

**Where it's applied:** `db.py` — the entire SQL and connection layer.

**What's encapsulated:**
- SQL query strings
- Database connection logic
- Backend switching (SQLite ↔ Postgres)
- Parameter placeholder rewriting
- Connection pooling and transaction handling
- Password hashing algorithm

**Evidence — `db.py`:**
```python
def read_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame."""
    with engine.connect() as conn:
        result = conn.exec_driver_sql(_adapt(sql), params)
        if result.returns_rows:
            rows = result.fetchall()
            cols = list(result.keys())
            return pd.DataFrame(rows, columns=cols)
        return pd.DataFrame()


def exec_sql(sql: str, params: tuple = ()) -> None:
    """Run an INSERT / UPDATE / DELETE with tuple params."""
    with engine.begin() as conn:
        conn.exec_driver_sql(_adapt(sql), params)


def hash_password(password: str, salt: bytes | None = None) -> str:
    """PBKDF2-HMAC-SHA256 with 200k iterations."""
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"
```

**Why it matters:** Every feature module calls `read_df()` and `exec_sql()`. None of them know — or care — whether the backend is SQLite or Postgres, or how passwords are hashed. If we ever switch from SQLAlchemy to raw psycopg, only `db.py` changes.

---

### 2️⃣ Inheritance

**Definition:** Creating new classes or modules that reuse, extend, and specialize behavior from a parent class or shared base.

**Where it's applied:** Three places in the project.

#### A. SQLAlchemy Engine Hierarchy (Framework Level)
The `create_engine()` factory returns instances of different engine subclasses that all inherit from SQLAlchemy's abstract `Engine` base class:

```
SQLAlchemy Engine (abstract)
    ├── SQLiteDialect        (local development)
    └── PostgresqlDialect    (Supabase production)
```

**Evidence — `db.py`:**
```python
from sqlalchemy import create_engine

def _build_engine():
    if USE_SUPABASE:
        # Returns PostgresqlEngine instance
        return create_engine(SUPABASE_DB_URL, pool_pre_ping=True, ...)
    # Returns SQLiteEngine instance
    return create_engine(f"sqlite:///{SQLITE_PATH}",
                         connect_args={"check_same_thread": False})
```

Both engines share the same parent interface (`connect()`, `begin()`, `exec_driver_sql()`), so application code uses them identically.

#### B. Feature Module Pattern (Project Level)
Every feature module follows the same inherited structure — a single public `render_*_module()` function that Streamlit's router calls:

```
main.py router (parent contract)
    ├── feature_dashboard.py    → render_dashboard_module()
    ├── feature_inventory.py    → render_inventory_module()
    ├── feature_delivery.py     → render_delivery_module()
    ├── feature_receiving.py    → render_receiving_module()
    ├── feature_camera_scan.py  → render_camera_scan_module()
    ├── feature_analytics.py    → render_analytics_module()
    ├── feature_products.py     → render_product_management_module()
    └── feature_po.py           → render_po_module()
```

**Evidence — `main.py`:**
```python
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
```

**Why it matters:** Adding a new module takes ~15 lines — create the file with the same `render_*_module()` contract, import it, add a router branch. No changes needed elsewhere.

#### C. Role-Based Access Inheritance (Permission Level)
Each role inherits permissions from the base set and adds its own. `Yard Clerk` inherits from a baseline of view permissions and gains receiving/scanner access; `Sales Analyst` inherits view access but gains analytics only.

**Evidence — `main.py`:**
```python
ROLE_MODULES = {
    "System Admin":           ALL_MODULES,
    "Inventory Manager":      ALL_MODULES,
    "Yard Clerk / Inspector": ["Dashboard", "Categorized Inventory",
                               "Pending Deliveries",
                               "Barcode Generator", "Barcode Scanner"],
    "Sales Analyst":          ["Dashboard", "Item Sales Analytics"],
}
```

---

### 3️⃣ Polymorphism

**Definition:** The ability for the same method or operation to behave differently depending on the object or context it's called on.

**Where it's applied:** `db.py` — the `_adapt()` function and the shared `read_df()` / `exec_sql()` calls.

#### A. Placeholder Adaptation (Backend Polymorphism)
The same SQL call works on both backends because `_adapt()` polymorphically rewrites the placeholder syntax:

**Evidence — `db.py`:**
```python
def _adapt(sql: str) -> str:
    """Rewrite '?' placeholders to '%s' for Postgres."""
    if USE_SUPABASE:
        return sql.replace("?", "%s")
    return sql
```

- **SQLite** uses `?` placeholders
- **Postgres** uses `%s` placeholders
- The **same** `read_df("SELECT ... WHERE name = ?", (name,))` call works on **both** without modification

**Example from `feature_inventory.py`:**
```python
match = read_df("SELECT * FROM inventory WHERE UPPER(item_id) = ?", (code,))
```

This exact line runs identically on SQLite (local) and Supabase (production).

#### B. Multi-Decoder Polymorphism (Scanning Pipeline)
The barcode decoding pipeline polymorphically attempts multiple decoding strategies on each image variant:

**Evidence — `feature_camera_scan.py`:**
```python
# Try zxing-cpp first
if _ZXING_OK:
    for v in variants:
        for b in zxingcpp.read_barcodes(v):
            if b.text:
                _add(b.text, str(b.format))

# Fallback to OpenCV if zxing fails
if not results and _CV2_OK:
    detector = cv2.barcode.BarcodeDetector()
    ok, infos, types, _ = detector.detectAndDecode(v)
```

Each decoder is a different "shape" of the same abstract operation — *decode barcode from image* — and the pipeline picks whichever succeeds first.

**Why it matters:** Application code is completely backend-agnostic. Switching databases or adding a new decoder requires no feature-code changes.

---

### 4️⃣ Abstraction

**Definition:** Hiding complex implementation details behind a simpler interface — showing *what* a method does, not *how* it does it.

**Where it's applied:** Two major places in the project.

#### A. Database Access Abstraction
All database operations are abstracted behind three simple functions — `read_df()`, `exec_sql()`, `exec_many()`.

**Evidence — `db.py`:**
```python
def read_df(sql: str, params: tuple = ()) -> pd.DataFrame: ...
def exec_sql(sql: str, params: tuple = ()) -> None: ...
def exec_many(sql: str, seq) -> None: ...
```

**Caller's perspective (`feature_inventory.py`):**
```python
match = read_df("SELECT * FROM inventory WHERE UPPER(item_id) = ?", (code,))
```

One line. The caller sees "give me the data matching this SQL." They never see:
- Connection pooling
- Dialect-specific placeholder rewriting
- Cursor management
- Transaction begin/commit/rollback
- DataFrame construction

#### B. Barcode Decoding Abstraction
The `_decode_from_bytes()` function hides an entire 7-stage image processing pipeline behind a single method call.

**What's hidden inside:**
1. Image bytes → NumPy array conversion
2. BGR → grayscale conversion
3. Upscaling to 2400px
4. Sharpening filter
5. Adaptive thresholding
6. Otsu thresholding
7. Multi-decoder fallback (zxing → OpenCV → QR)

**Evidence — `feature_camera_scan.py`:**
```python
def _decode_from_bytes(bytes_data: bytes):
    arr = np.frombuffer(bytes_data, dtype=np.uint8)
    img_color = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)
    variants = [gray]

    h, w = gray.shape
    up_for_thresh = gray
    if max(h, w) < 2400:
        scale = 2400 / max(h, w)
        up_for_thresh = cv2.resize(gray, (int(w * scale), int(h * scale)),
                                   interpolation=cv2.INTER_CUBIC)
        variants.append(("upscaled", up_for_thresh))

    sharp = cv2.addWeighted(gray, 1.6, cv2.GaussianBlur(gray, (0, 0), 3), -0.6, 0)
    variants.append(("sharpened", sharp))

    thresh = cv2.adaptiveThreshold(up_for_thresh, 255,
                                   cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 51, 15)
    variants.append(("adaptive_thresh", thresh))

    _, otsu = cv2.threshold(up_for_thresh, 0, 255,
                            cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("otsu", otsu))

    if _ZXING_OK:
        for name, v in variants:
            try:
                for b in zxingcpp.read_barcodes(v):
                    if b.text:
                        _add(b.text, str(b.format))
                if results:
                    break
            except Exception:
                continue

    if not results and _CV2_OK:
        for name, v in variants:
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
```

**Caller's perspective (`render_camera_scan_module`):**
```python
with st.spinner("Reading barcode…"):
    results = _decode_from_bytes(picture.getvalue())
```

One line. The caller sees a bytes-in, list-out method. It never sees the five preprocessing stages or the two decoder fallbacks.

#### C. PDF Generation Abstraction
`_generate_po_pdf()` hides font registration, table styling, page layout, and multi-page handling behind one call.

**Evidence — `feature_po.py`:**
```python
pdf_bytes = _generate_po_pdf(
    enriched,
    preview_numbers,
    st.session_state.logged_user["name"],
)
```

---

### 📊 OOP Principles Summary

| Principle | Where Applied | Concrete Evidence | Impact |
|---|---|---|---|
| **Encapsulation** | `db.py` (all DB logic) | `read_df()`, `exec_sql()` hide SQL, connections, hashing | Feature modules never touch SQL directly |
| **Inheritance** | `db.py` engines, feature modules, roles | Shared interface across engines, modules, and roles | Adding a new module/DB takes ~20 lines |
| **Polymorphism** | `db.py` `_adapt()`, `feature_camera_scan.py` | Same call works on any backend; multi-decoder fallback | App is backend-agnostic; scanning is resilient |
| **Abstraction** | `db.py`, `feature_camera_scan.py`, `feature_po.py` | Complex pipelines behind single method calls | Caller code is short and readable |

---

## 🚀 Setup

### Prerequisites
- Python 3.12+
- A Supabase account (free tier works)
- A modern browser (Chrome, Edge, Firefox, Safari)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/cyncsupply.git
cd cyncsupply

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Configure Supabase

1. Create a new project at [supabase.com](https://supabase.com)
2. Open the **SQL Editor** and run the contents of `supabase_schema.sql`
3. Copy the **Session Pooler** connection string from **Project Settings → Database**
4. Create a `.env` file in the project root:

```
USE_SUPABASE=1
SQLITE_PATH=cyncsupply.db
SUPABASE_DB_URL=postgresql://postgres.xxxx:password@aws-0-region.pooler.supabase.com:5432/postgres
```

### Run the Application

```bash
python -m streamlit run main.py
```

The app opens at `http://localhost:8501`.

---

## 👤 Demo Accounts

| Username | Password | Role |
|---|---|---|
| `carlf` | `password123` | Inventory Manager |
| `admin` | `admin123` | System Admin |
| `clerk` | `clerk123` | Yard Clerk / Inspector |
| `sales` | `sales123` | Sales Analyst |

---

## 📱 Multi-Device Access

### Same Wi-Fi (LAN — no camera)
1. Run `python -m streamlit run main.py` on the laptop
2. Open `http://<Network-URL-IP>:8501` on the phone/tablet
3. Open Windows Firewall port 8501 once:
   ```powershell
   New-NetFirewallRule -DisplayName "Streamlit 8501" -Direction Inbound -LocalPort 8501 -Protocol TCP -Action Allow
   ```

### HTTPS via ngrok (camera enabled)
1. Open a second terminal and run:
   ```
   ngrok http 8501
   ```
2. Copy the `https://xxxx.ngrok-free.dev` URL
3. Open it on the phone/tablet and allow camera access

---

## 📋 Complete Workflow

```
Product Setup
     ↓
Purchase Order Dispatched ─────► Pending Delivery
                                      ↓
                                 Confirm Received (inventory +)
                                      ↓
                                 Barcode Generated & Attached
                                      ↓
                                 Customer Buys → Scan Barcode
                                      ↓
                                 Inventory −, Sale Logged, Barcode Expired
                                      ↓
                                 Analytics & Dashboard Updated
                                      ↓
                                 Low Stock? → Back to Purchase Order
```

---

## 📂 Project Structure

```
cyncsupply_m2/
├── main.py                        # Router, auth, UI shell
├── db.py                          # Repository layer (Database abstraction)
├── feature_auth.py                # Authentication UI
├── feature_dashboard.py           # KPIs + charts
├── feature_inventory.py           # Stock table + POS scan
├── feature_products.py            # Product CRUD
├── feature_delivery.py            # Pending deliveries
├── feature_receiving.py           # Barcode generator
├── feature_camera_scan.py         # Barcode scanner (decode abstraction)
├── feature_analytics.py           # Sales analytics
├── feature_po.py                  # Purchase Order module (PDF abstraction)
├── .streamlit/config.toml         # Server + theme config
├── requirements.txt               # Python dependencies
├── supabase_schema.sql            # PostgreSQL schema
├── generate_seed_hashes.py        # Password hash generator
└── .env                           # Database connection secrets
```

---

## 👨‍💻 Author

**Carl Francis G Anay and Justin Danganon** — IT102 Object-Oriented Programming

---

## 📄 License

This project is for educational purposes.