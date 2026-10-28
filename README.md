# CyncSupply

## Project Description
CyncSupply is a Python OOP application that helps hardware stores manage inventory, prevent stock theft, and automate purchasing using per-unit barcode tracking.

## High-Priority Features
1. Role-based authentication
2. Real-time inventory dashboard
3. Categorized stock tracking
4. Per-unit barcode generation
5. Camera scan-to-sell verification
6. Automated purchase order generation
7. Sales analytics and reporting

## Technologies Used
- Python
- Streamlit
- Supabase (PostgreSQL)
- SQLAlchemy
- OpenCV & ZXing-C++ (Barcode decoding)
- ReportLab (PDF generation)

## OOP Implementation
- Encapsulation: Database connection logic and SQL queries are hidden inside the `connection.py` module.
- Inheritance: A base database engine is extended by both local SQLite and cloud PostgreSQL engines.
- Polymorphism: The same database query function dynamically adapts its syntax depending on the active backend.
- Abstraction: The complex image processing pipeline for barcode scanning is hidden behind a single function call.

## Project Structure
- models/: Database connection and data access layer
- views/: User interface modules for each feature
- controller/: Application routing and main entry point
- utils/: Standalone scripts (e.g., password hashing)

## Installation
1. Download or clone the repository.
2. Create and activate a Python virtual environment.
3. Install the required packages.
4. Configure the application `.env` file with Supabase credentials.
5. Run the main Python file (`python -m streamlit run controller/main.py`).

## Developers
- Carl Francis G. Anay
- Justin Danganon
