"""Optional demo-data loader for Waste2Worth.
Run: python seed_demo.py
It resets demo records only if they do not already exist.
"""
import os
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash

from app import DB_PATH, init_db, now_iso

DEMO_USERS = [
    ("seller.demo@gmail.com", "DemoSeller@123", "Aarav Materials", "9000000001"),
    ("buyer.demo@gmail.com", "DemoBuyer@123", "Maya Circular Works", "9000000002"),
]


def main():
    init_db()
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    for email, password, name, phone in DEMO_USERS:
        row = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if not row:
            db.execute(
                "INSERT INTO users(email,password_hash,name,phone,role,created_at) VALUES (?,?,?,?,?,?)",
                (email, generate_password_hash(password), name, phone, "customer", now_iso()),
            )
    db.commit()
    seller = db.execute("SELECT * FROM users WHERE email='seller.demo@gmail.com'").fetchone()
    buyer = db.execute("SELECT * FROM users WHERE email='buyer.demo@gmail.com'").fetchone()
    store = db.execute("SELECT * FROM stores WHERE user_id=?", (seller["id"],)).fetchone()
    if not store:
        store_code = "W2W-DEMO-" + datetime.utcnow().strftime("%H%M%S")
        db.execute(
            """INSERT INTO stores(user_id,store_id,store_name,store_type,gst_id,license_no,address,city,pincode,owner_name,phone,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (seller["id"], store_code, "Aarav Eco Materials", "Recycler", "09DEMO1234F1Z5", "DEMO-LIC-2026", "12 Green Avenue", "Lucknow", "226010", seller["name"], seller["phone"], now_iso()),
        )
        store_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        samples = [
            (store_id, "Clean Corrugated Cardboard", "cardboard", "Dry, flattened boxes collected from local retail shipments. Suitable for paper recycling and packaging reuse.", 80, "kg", 9.5),
            (store_id, "Clear Glass Bottles", "glass", "Clean, intact glass bottles sorted by type. Ideal for reuse or glass recycling.", 120, "pieces", 4.0),
            (store_id, "HDPE Plastic Containers", "plastic", "Clean rigid HDPE containers, separated and ready for material recovery.", 45, "kg", 32.0),
        ]
        for rec in samples:
            db.execute(
                """INSERT INTO listings(store_id,item_name,category,about_item,quantity,unit,price,status,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (*rec, "active", now_iso(), now_iso()),
            )
    db.commit()
    db.close()
    print("Demo data ready.")
    print("Seller: seller.demo@gmail.com / DemoSeller@123")
    print("Buyer:  buyer.demo@gmail.com / DemoBuyer@123")


if __name__ == "__main__":
    main()
