"""
Run locally once to produce the hashed passwords for the Supabase seed.
    python generate_seed_hashes.py
Then paste each UPDATE statement into the Supabase SQL Editor.
"""
import os
os.environ.setdefault("USE_SUPABASE", "0")

from repositories.connection import hash_password

SEEDS = [
    ("carlf", "password123", "Inventory Manager",      "Carlos Anay"),
    ("admin", "admin123",    "System Admin",           "Administrator"),
    ("clerk", "clerk123",    "Yard Clerk / Inspector", "Yard Clerk"),
    ("sales", "sales123",    "Sales Analyst",          "Sales Analyst"),
]

print("-- Paste into Supabase SQL Editor --\n")
for u, p, role, name in SEEDS:
    print(f"-- {u} ({role})")
    print(f"UPDATE users SET password = '{hash_password(p)}' WHERE username = '{u}';\n")