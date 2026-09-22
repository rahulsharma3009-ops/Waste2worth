from __future__ import annotations

import os
import re
import sqlite3
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
DB_PATH = INSTANCE_DIR / "waste2worth.db"
INSTANCE_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("W2W_SECRET_KEY", "waste2worth-dev-secret-change-me"),
    DATABASE=str(DB_PATH),
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    ALLOWED_IMAGE_EXTENSIONS={"png", "jpg", "jpeg", "webp", "gif"},
)

DEFAULT_ADMIN_EMAIL = os.environ.get("W2W_ADMIN_EMAIL", "rahulssharma3009@gmail.com")
DEFAULT_ADMIN_PASSWORD = os.environ.get("W2W_ADMIN_PASSWORD", "Rahul@3009")

MATERIAL_FACTORS = {
    "cardboard": 0.70,
    "paper": 0.90,
    "plastic": 1.80,
    "glass": 0.35,
    "metal": 2.00,
    "textile": 2.50,
    "organic": 0.55,
    "e-waste": 3.20,
    "other": 0.40,
}


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db = sqlite3.connect(app.config["DATABASE"])
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        g.db = db
    return g.db


@app.teardown_appcontext
def close_db(_exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_db(query: str, args=(), one: bool = False):
    cur = get_db().execute(query, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute_db(query: str, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.lastrowid


def init_db() -> None:
    db = sqlite3.connect(app.config["DATABASE"])
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            phone TEXT,
            role TEXT NOT NULL CHECK(role IN ('customer','admin')) DEFAULT 'customer',
            is_blacklisted INTEGER NOT NULL DEFAULT 0,
            blacklist_reason TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            store_id TEXT UNIQUE NOT NULL,
            store_name TEXT NOT NULL,
            store_type TEXT NOT NULL,
            gst_id TEXT NOT NULL,
            license_no TEXT NOT NULL,
            address TEXT NOT NULL,
            city TEXT NOT NULL,
            pincode TEXT NOT NULL,
            owner_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            about_item TEXT NOT NULL,
            quantity REAL NOT NULL CHECK(quantity > 0),
            unit TEXT NOT NULL,
            price REAL NOT NULL CHECK(price >= 0),
            image_filename TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            seller_store_id INTEGER NOT NULL,
            quantity REAL NOT NULL CHECK(quantity > 0),
            total_price REAL NOT NULL CHECK(total_price >= 0),
            status TEXT NOT NULL DEFAULT 'placed',
            created_at TEXT NOT NULL,
            FOREIGN KEY(listing_id) REFERENCES listings(id),
            FOREIGN KEY(buyer_id) REFERENCES users(id),
            FOREIGN KEY(seller_store_id) REFERENCES stores(id)
        );

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            reporter_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            FOREIGN KEY(listing_id) REFERENCES listings(id),
            FOREIGN KEY(reporter_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER UNIQUE NOT NULL,
            buyer_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id),
            FOREIGN KEY(buyer_id) REFERENCES users(id),
            FOREIGN KEY(listing_id) REFERENCES listings(id)
        );
        """
    )
    admin = db.execute("SELECT id FROM users WHERE email = ?", (DEFAULT_ADMIN_EMAIL,)).fetchone()
    if not admin:
        db.execute(
            "INSERT INTO users(email,password_hash,name,role,created_at) VALUES (?,?,?,?,?)",
            (
                DEFAULT_ADMIN_EMAIL,
                generate_password_hash(DEFAULT_ADMIN_PASSWORD),
                "Waste2Worth Administrator",
                "admin",
                now_iso(),
            ),
        )
    db.commit()
    db.close()


def current_user():
    if "user_id" not in session:
        return None
    user = query_db("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)
    return user


def customer_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or user["role"] != "customer":
            flash("Please log in as a customer to continue.", "warning")
            return redirect(url_for("customer_login", next=request.path))
        if user["is_blacklisted"]:
            session.clear()
            flash("This account has been blacklisted. Contact the administrator for review.", "danger")
            return redirect(url_for("customer_login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or user["role"] != "admin":
            flash("Admin login required.", "warning")
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_IMAGE_EXTENSIONS"]


def money(v: float) -> str:
    return f"₹{v:,.2f}"


@app.template_filter("money")
def money_filter(value):
    try:
        return money(float(value))
    except Exception:
        return "₹0.00"


@app.template_filter("datetime_short")
def datetime_short(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "")).strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return value


@app.context_processor
def inject_globals():
    user = current_user()
    store = None
    if user and user["role"] == "customer":
        store = query_db("SELECT * FROM stores WHERE user_id = ?", (user["id"],), one=True)
    return {
        "current_user": user,
        "current_store": store,
        "categories": ["cardboard", "paper", "plastic", "glass", "metal", "textile", "organic", "e-waste", "other"],
        "material_factors": MATERIAL_FACTORS,
    }


@app.route("/")
def home():
    stats = {
        "active_listings": query_db("SELECT COUNT(*) c FROM listings WHERE status='active'", one=True)["c"],
        "stores": query_db("SELECT COUNT(*) c FROM stores", one=True)["c"],
        "orders": query_db("SELECT COUNT(*) c FROM orders", one=True)["c"],
        "material_kg": query_db("SELECT COALESCE(SUM(quantity),0) q FROM listings WHERE status='active'", one=True)["q"],
    }
    featured = query_db(
        """
        SELECT l.*, s.store_name, s.store_id AS public_store_id, s.city
        FROM listings l JOIN stores s ON s.id=l.store_id
        JOIN users u ON u.id=s.user_id
        WHERE l.status='active' AND u.is_blacklisted=0
        ORDER BY l.created_at DESC LIMIT 6
        """
    )
    return render_template("home.html", stats=stats, featured=featured)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/customer/signup", methods=["GET", "POST"])
def customer_signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        errors = []
        if not name or len(name) < 2:
            errors.append("Enter a valid full name.")
        if not re.fullmatch(r"[^\s@]+@gmail\.com", email, flags=re.I):
            errors.append("Use a valid Gmail address for the customer account.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if query_db("SELECT id FROM users WHERE email=?", (email,), one=True):
            errors.append("An account with this Gmail already exists.")
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("customer_signup.html")
        user_id = execute_db(
            "INSERT INTO users(email,password_hash,name,phone,role,created_at) VALUES (?,?,?,?,?,?)",
            (email, generate_password_hash(password), name, phone, "customer", now_iso()),
        )
        session.clear()
        session["user_id"] = user_id
        flash("Account created successfully. Create your Store ID to start selling.", "success")
        return redirect(url_for("customer_dashboard"))
    return render_template("customer_signup.html")


@app.route("/customer/login", methods=["GET", "POST"])
def customer_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = query_db("SELECT * FROM users WHERE email=? AND role='customer'", (email,), one=True)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid Gmail or password.", "danger")
            return render_template("customer_login.html")
        if user["is_blacklisted"]:
            flash("This customer account is currently blacklisted. Please contact the administrator.", "danger")
            return render_template("customer_login.html")
        session.clear()
        session["user_id"] = user["id"]
        flash(f"Welcome back, {user['name']}!", "success")
        next_url = request.args.get("next") or url_for("customer_dashboard")
        return redirect(next_url if next_url.startswith("/") else url_for("customer_dashboard"))
    return render_template("customer_login.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = query_db("SELECT * FROM users WHERE email=? AND role='admin'", (email,), one=True)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid admin credentials.", "danger")
            return render_template("admin_login.html")
        session.clear()
        session["user_id"] = user["id"]
        flash("Admin access granted.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
@customer_required
def customer_dashboard():
    user = current_user()
    store = query_db("SELECT * FROM stores WHERE user_id=?", (user["id"],), one=True)
    stats = {
        "listings": query_db("SELECT COUNT(*) c FROM listings l JOIN stores s ON s.id=l.store_id WHERE s.user_id=?", (user["id"],), one=True)["c"],
        "orders": query_db("SELECT COUNT(*) c FROM orders WHERE buyer_id=?", (user["id"],), one=True)["c"],
        "sales": query_db(
            "SELECT COALESCE(SUM(o.total_price),0) t FROM orders o JOIN stores s ON s.id=o.seller_store_id WHERE s.user_id=?",
            (user["id"],), one=True
        )["t"],
    }
    recent_listings = []
    recent_orders = []
    if store:
        recent_listings = query_db("SELECT * FROM listings WHERE store_id=? ORDER BY created_at DESC LIMIT 5", (store["id"],))
    recent_orders = query_db(
        """
        SELECT o.*, l.item_name, s.store_name, u.name buyer_name
        FROM orders o JOIN listings l ON l.id=o.listing_id
        JOIN stores s ON s.id=o.seller_store_id JOIN users u ON u.id=o.buyer_id
        WHERE o.buyer_id=? OR s.user_id=? ORDER BY o.created_at DESC LIMIT 8
        """,
        (user["id"], user["id"]),
    )
    return render_template("customer_dashboard.html", stats=stats, store=store, recent_listings=recent_listings, recent_orders=recent_orders)


@app.route("/store/create", methods=["GET", "POST"])
@customer_required
def create_store():
    user = current_user()
    existing = query_db("SELECT * FROM stores WHERE user_id=?", (user["id"],), one=True)
    if existing:
        return redirect(url_for("store_profile"))
    if request.method == "POST":
        data = {k: request.form.get(k, "").strip() for k in ["store_name", "store_type", "gst_id", "license_no", "address", "city", "pincode", "owner_name", "phone"]}
        errors = []
        for key, label in [("store_name","store name"),("store_type","store type"),("gst_id","GST ID"),("license_no","license number"),("address","address"),("city","city"),("pincode","pincode"),("owner_name","owner name"),("phone","phone")]:
            if not data[key]:
                errors.append(f"{label.title()} is required.")
        if data["gst_id"] and not re.fullmatch(r"[0-9A-Z]{8,20}", data["gst_id"].upper()):
            errors.append("GST ID format looks invalid. Use letters and digits only (8–20 characters).")
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("store_create.html", form=data)
        store_id = "W2W-" + datetime.utcnow().strftime("%y%m%d") + "-" + uuid.uuid4().hex[:6].upper()
        execute_db(
            """
            INSERT INTO stores(user_id,store_id,store_name,store_type,gst_id,license_no,address,city,pincode,owner_name,phone,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (user["id"],store_id,data["store_name"],data["store_type"],data["gst_id"].upper(),data["license_no"],data["address"],data["city"],data["pincode"],data["owner_name"],data["phone"],now_iso()),
        )
        flash(f"Store created successfully. Your unique Store ID is {store_id}.", "success")
        return redirect(url_for("store_profile"))
    form = {"owner_name": user["name"], "phone": user["phone"] or ""}
    return render_template("store_create.html", form=form)


@app.route("/store")
@customer_required
def store_profile():
    user = current_user()
    store = query_db("SELECT * FROM stores WHERE user_id=?", (user["id"],), one=True)
    if not store:
        return redirect(url_for("create_store"))
    return render_template("store_profile.html", store=store)


@app.route("/store/id-card")
@customer_required
def store_id_card():
    user = current_user()
    store = query_db("SELECT * FROM stores WHERE user_id=?", (user["id"],), one=True)
    if not store:
        return redirect(url_for("create_store"))
    return render_template("store_id_card.html", store=store, user=user)


@app.route("/sell", methods=["GET", "POST"])
@customer_required
def sell():
    user = current_user()
    store = query_db("SELECT * FROM stores WHERE user_id=?", (user["id"],), one=True)
    if not store:
        flash("Create your Store ID before listing items.", "warning")
        return redirect(url_for("create_store"))
    if request.method == "POST":
        item_name = request.form.get("item_name", "").strip()
        category = request.form.get("category", "other").strip().lower()
        about = request.form.get("about_item", "").strip()
        unit = request.form.get("unit", "kg").strip()
        try:
            quantity = float(request.form.get("quantity", "0"))
            price = float(request.form.get("price", "0"))
        except ValueError:
            quantity = price = 0
        image = request.files.get("item_picture")
        errors=[]
        if not item_name: errors.append("Item name is required.")
        if not about: errors.append("Description is required.")
        if quantity <= 0: errors.append("Quantity must be greater than 0.")
        if price < 0: errors.append("Price cannot be negative.")
        if category not in MATERIAL_FACTORS: errors.append("Choose a valid material category.")
        filename = None
        if image and image.filename:
            if not allowed_file(image.filename):
                errors.append("Image must be PNG, JPG, JPEG, WEBP, or GIF.")
            else:
                ext = secure_filename(image.filename).rsplit(".",1)[1].lower()
                filename = f"{uuid.uuid4().hex}.{ext}"
        if errors:
            for e in errors: flash(e, "danger")
            return render_template("sell.html", store=store)
        if filename:
            image.save(UPLOAD_DIR / filename)
        execute_db(
            """
            INSERT INTO listings(store_id,item_name,category,about_item,quantity,unit,price,image_filename,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (store["id"], item_name, category, about, quantity, unit, price, filename, "active", now_iso(), now_iso()),
        )
        flash("Item listed successfully on the Waste2Worth marketplace.", "success")
        return redirect(url_for("my_listings"))
    return render_template("sell.html", store=store)


@app.route("/listings")
@customer_required
def my_listings():
    user = current_user()
    store = query_db("SELECT * FROM stores WHERE user_id=?", (user["id"],), one=True)
    listings = query_db("SELECT * FROM listings WHERE store_id=? ORDER BY created_at DESC", (store["id"],)) if store else []
    return render_template("my_listings.html", listings=listings, store=store)


@app.post("/listing/<int:listing_id>/toggle")
@customer_required
def toggle_listing(listing_id: int):
    user = current_user()
    listing = query_db(
        "SELECT l.*, s.user_id FROM listings l JOIN stores s ON s.id=l.store_id WHERE l.id=?", (listing_id,), one=True
    )
    if not listing or listing["user_id"] != user["id"]:
        abort(403)
    new_status = "paused" if listing["status"] == "active" else "active"
    execute_db("UPDATE listings SET status=?, updated_at=? WHERE id=?", (new_status, now_iso(), listing_id))
    flash(f"Listing {new_status}.", "success")
    return redirect(request.referrer or url_for("my_listings"))


@app.route("/buy")
@customer_required
def buy():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip().lower()
    sort = request.args.get("sort", "newest")
    sql = """
        SELECT l.*, s.store_name, s.store_id AS public_store_id, s.city, u.is_blacklisted,
               COALESCE((SELECT AVG(r.rating) FROM reviews r WHERE r.listing_id=l.id),0) AS avg_rating
        FROM listings l JOIN stores s ON s.id=l.store_id JOIN users u ON u.id=s.user_id
        WHERE l.status='active' AND u.is_blacklisted=0
    """
    args=[]
    if q:
        sql += " AND (LOWER(l.item_name) LIKE ? OR LOWER(l.about_item) LIKE ? OR LOWER(s.store_name) LIKE ?)"
        like=f"%{q.lower()}%"
        args += [like,like,like]
    if category in MATERIAL_FACTORS:
        sql += " AND l.category=?"
        args.append(category)
    order = {"newest":"l.created_at DESC", "price_low":"l.price ASC", "price_high":"l.price DESC", "quantity":"l.quantity DESC"}.get(sort, "l.created_at DESC")
    sql += f" ORDER BY {order}"
    listings = query_db(sql, args)
    return render_template("buy.html", listings=listings, q=q, category=category, sort=sort)


@app.get("/listing/<int:listing_id>")
@customer_required
def listing_detail(listing_id: int):
    listing = query_db(
        """
        SELECT l.*, s.store_name, s.store_id AS public_store_id, s.city, s.address, s.store_type,
               u.name owner_name, u.is_blacklisted, COALESCE(AVG(r.rating),0) avg_rating, COUNT(r.id) review_count
        FROM listings l JOIN stores s ON s.id=l.store_id JOIN users u ON u.id=s.user_id
        LEFT JOIN reviews r ON r.listing_id=l.id WHERE l.id=? GROUP BY l.id
        """, (listing_id,), one=True)
    if not listing or listing["status"] != "active" or listing["is_blacklisted"]:
        abort(404)
    reviews = query_db(
        "SELECT r.*, u.name buyer_name FROM reviews r JOIN users u ON u.id=r.buyer_id WHERE r.listing_id=? ORDER BY r.created_at DESC",
        (listing_id,),
    )
    return render_template("listing_detail.html", listing=listing, reviews=reviews)


@app.post("/listing/<int:listing_id>/buy")
@customer_required
def place_order(listing_id: int):
    user = current_user()
    try:
        qty = float(request.form.get("quantity", "0"))
    except ValueError:
        qty = 0
    if qty <= 0:
        flash("Enter a valid purchase quantity.", "danger")
        return redirect(url_for("listing_detail", listing_id=listing_id))
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    listing = db.execute(
        """
        SELECT l.*, s.user_id seller_user_id, s.id seller_store_id, u.is_blacklisted seller_blacklisted
        FROM listings l JOIN stores s ON s.id=l.store_id JOIN users u ON u.id=s.user_id WHERE l.id=?
        """, (listing_id,)
    ).fetchone()
    try:
        if not listing or listing["status"] != "active" or listing["seller_blacklisted"] or listing["quantity"] < qty:
            db.rollback()
            flash("This listing is unavailable or the requested quantity is not in stock.", "danger")
            return redirect(url_for("buy"))
        if listing["seller_user_id"] == user["id"]:
            db.rollback()
            flash("You cannot purchase your own listing.", "warning")
            return redirect(url_for("listing_detail", listing_id=listing_id))
        total = qty * listing["price"]
        db.execute(
            "INSERT INTO orders(listing_id,buyer_id,seller_store_id,quantity,total_price,status,created_at) VALUES (?,?,?,?,?,?,?)",
            (listing_id, user["id"], listing["seller_store_id"], qty, total, "placed", now_iso()),
        )
        remaining = listing["quantity"] - qty
        db.execute(
            "UPDATE listings SET quantity=?, status=?, updated_at=? WHERE id=?",
            (remaining, "sold_out" if remaining <= 0 else "active", now_iso(), listing_id),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    flash(f"Order placed successfully for {qty:g} {listing['unit']} of {listing['item_name']}.", "success")
    return redirect(url_for("orders"))


@app.route("/orders")
@customer_required
def orders():
    user = current_user()
    rows = query_db(
        """
        SELECT o.*, l.item_name, l.unit, s.store_name, s.store_id public_store_id,
               s.user_id seller_user_id, su.name seller_name, bu.name buyer_name
        FROM orders o JOIN listings l ON l.id=o.listing_id JOIN stores s ON s.id=o.seller_store_id
        JOIN users su ON su.id=s.user_id JOIN users bu ON bu.id=o.buyer_id
        WHERE o.buyer_id=? OR s.user_id=? ORDER BY o.created_at DESC
        """, (user["id"], user["id"]),
    )
    return render_template("orders.html", orders=rows)


@app.post("/order/<int:order_id>/status")
@customer_required
def update_order_status(order_id: int):
    user = current_user()
    order = query_db(
        """
        SELECT o.*, s.user_id seller_user_id FROM orders o JOIN stores s ON s.id=o.seller_store_id WHERE o.id=?
        """, (order_id,), one=True
    )
    if not order or order["seller_user_id"] != user["id"]:
        abort(403)
    status = request.form.get("status", "")
    if status not in {"accepted", "ready", "completed", "cancelled"}:
        flash("Invalid order status.", "danger")
        return redirect(url_for("orders"))
    execute_db("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    flash("Order status updated.", "success")
    return redirect(url_for("orders"))


@app.post("/order/<int:order_id>/review")
@customer_required
def add_review(order_id: int):
    user = current_user()
    order = query_db("SELECT * FROM orders WHERE id=?", (order_id,), one=True)
    if not order or order["buyer_id"] != user["id"] or order["status"] not in {"completed", "accepted", "ready"}:
        abort(403)
    try:
        rating = int(request.form.get("rating", "0"))
    except ValueError:
        rating = 0
    comment = request.form.get("comment", "").strip()
    if rating not in range(1,6) or not comment:
        flash("Please provide a 1–5 rating and a short review.", "danger")
    elif query_db("SELECT id FROM reviews WHERE order_id=?", (order_id,), one=True):
        flash("You already reviewed this order.", "warning")
    else:
        execute_db("INSERT INTO reviews(order_id,buyer_id,listing_id,rating,comment,created_at) VALUES (?,?,?,?,?,?)",
                   (order_id,user["id"],order["listing_id"],rating,comment,now_iso()))
        flash("Thanks for helping the marketplace stay trustworthy.", "success")
    return redirect(url_for("orders"))


@app.post("/listing/<int:listing_id>/report")
@customer_required
def report_listing(listing_id: int):
    user = current_user()
    reason = request.form.get("reason", "").strip()
    if not reason:
        flash("Please provide a reason for the report.", "danger")
    else:
        execute_db("INSERT INTO reports(listing_id,reporter_id,reason,status,created_at) VALUES (?,?,?,?,?)",
                   (listing_id,user["id"],reason,"open",now_iso()))
        flash("Report submitted to the Waste2Worth admin team.", "success")
    return redirect(url_for("listing_detail", listing_id=listing_id))


@app.route("/impact")
@customer_required
def impact():
    user = current_user()
    owned = query_db(
        "SELECT COALESCE(SUM(l.quantity * ?),0) kg FROM listings l JOIN stores s ON s.id=l.store_id WHERE s.user_id=?",
        (0.25, user["id"]), one=True
    )["kg"]
    traded = query_db(
        "SELECT COALESCE(SUM(o.quantity),0) kg FROM orders o WHERE o.buyer_id=? OR o.seller_store_id IN (SELECT id FROM stores WHERE user_id=?)",
        (user["id"],user["id"]), one=True
    )["kg"]
    score_base = min(100, 20 + int(traded / 10) + (10 if owned else 0))
    return render_template("impact.html", owned=owned, traded=traded, score=score_base)


# -------------------- ADMIN --------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    stats = {
        "users": query_db("SELECT COUNT(*) c FROM users WHERE role='customer'", one=True)["c"],
        "stores": query_db("SELECT COUNT(*) c FROM stores", one=True)["c"],
        "listings": query_db("SELECT COUNT(*) c FROM listings", one=True)["c"],
        "orders": query_db("SELECT COUNT(*) c FROM orders", one=True)["c"],
        "reports": query_db("SELECT COUNT(*) c FROM reports WHERE status='open'", one=True)["c"],
        "blacklisted": query_db("SELECT COUNT(*) c FROM users WHERE is_blacklisted=1", one=True)["c"],
    }
    return render_template("admin_dashboard.html", stats=stats)


@app.route("/admin/sellers")
@admin_required
def admin_sellers():
    sellers = query_db(
        """
        SELECT s.*, u.id user_id, u.email, u.name, u.phone, u.is_blacklisted, u.blacklist_reason,
               (SELECT COUNT(*) FROM listings l WHERE l.store_id=s.id) listing_count,
               (SELECT COALESCE(SUM(o.total_price),0) FROM orders o WHERE o.seller_store_id=s.id) total_sales
        FROM stores s JOIN users u ON u.id=s.user_id ORDER BY s.created_at DESC
        """
    )
    return render_template("admin_sellers.html", sellers=sellers)


@app.route("/admin/buyers")
@admin_required
def admin_buyers():
    buyers = query_db(
        """
        SELECT u.*, COUNT(o.id) order_count, COALESCE(SUM(o.total_price),0) spend
        FROM users u LEFT JOIN orders o ON o.buyer_id=u.id
        WHERE u.role='customer' GROUP BY u.id ORDER BY u.created_at DESC
        """
    )
    return render_template("admin_buyers.html", buyers=buyers)


@app.route("/admin/listings")
@admin_required
def admin_listings():
    listings = query_db(
        """
        SELECT l.*, s.store_name, s.store_id public_store_id, u.email seller_email, u.name seller_name, u.is_blacklisted
        FROM listings l JOIN stores s ON s.id=l.store_id JOIN users u ON u.id=s.user_id ORDER BY l.created_at DESC
        """
    )
    return render_template("admin_listings.html", listings=listings)


@app.route("/admin/orders")
@admin_required
def admin_orders():
    rows = query_db(
        """
        SELECT o.*, l.item_name, l.unit, s.store_name, s.store_id public_store_id,
               su.name seller_name, su.email seller_email, bu.name buyer_name, bu.email buyer_email
        FROM orders o JOIN listings l ON l.id=o.listing_id JOIN stores s ON s.id=o.seller_store_id
        JOIN users su ON su.id=s.user_id JOIN users bu ON bu.id=o.buyer_id ORDER BY o.created_at DESC
        """
    )
    return render_template("admin_orders.html", orders=rows)


@app.route("/admin/reports")
@admin_required
def admin_reports():
    reports = query_db(
        """
        SELECT r.*, l.item_name, s.store_name, u.name reporter_name, u.email reporter_email
        FROM reports r JOIN listings l ON l.id=r.listing_id JOIN stores s ON s.id=l.store_id
        JOIN users u ON u.id=r.reporter_id ORDER BY CASE WHEN r.status='open' THEN 0 ELSE 1 END, r.created_at DESC
        """
    )
    return render_template("admin_reports.html", reports=reports)


@app.post("/admin/user/<int:user_id>/blacklist")
@admin_required
def blacklist_user(user_id: int):
    user = query_db("SELECT * FROM users WHERE id=? AND role='customer'", (user_id,), one=True)
    if not user:
        abort(404)
    reason = request.form.get("reason", "Policy violation / suspicious activity").strip()
    execute_db("UPDATE users SET is_blacklisted=1, blacklist_reason=? WHERE id=?", (reason,user_id))
    execute_db("UPDATE listings SET status='blocked', updated_at=? WHERE store_id IN (SELECT id FROM stores WHERE user_id=?)", (now_iso(),user_id))
    flash(f"{user['email']} has been blacklisted and their active listings blocked.", "success")
    return redirect(request.referrer or url_for("admin_sellers"))


@app.post("/admin/user/<int:user_id>/unblacklist")
@admin_required
def unblacklist_user(user_id: int):
    execute_db("UPDATE users SET is_blacklisted=0, blacklist_reason=NULL WHERE id=? AND role='customer'", (user_id,))
    execute_db("UPDATE listings SET status='active', updated_at=? WHERE status='blocked' AND store_id IN (SELECT id FROM stores WHERE user_id=?) AND quantity>0", (now_iso(),user_id))
    flash("Customer account restored. Listings with stock were reactivated.", "success")
    return redirect(request.referrer or url_for("admin_sellers"))


@app.post("/admin/listing/<int:listing_id>/block")
@admin_required
def block_listing(listing_id: int):
    execute_db("UPDATE listings SET status='blocked', updated_at=? WHERE id=?", (now_iso(),listing_id))
    flash("Listing blocked by admin.", "success")
    return redirect(request.referrer or url_for("admin_listings"))


@app.post("/admin/report/<int:report_id>/resolve")
@admin_required
def resolve_report(report_id: int):
    execute_db("UPDATE reports SET status='resolved' WHERE id=?", (report_id,))
    flash("Report marked as resolved.", "success")
    return redirect(url_for("admin_reports"))


@app.get("/api/search")
@customer_required
def api_search():
    q = request.args.get("q", "").strip()
    rows = query_db(
        """
        SELECT l.id,l.item_name,l.category,l.quantity,l.unit,l.price,s.store_name,s.city
        FROM listings l JOIN stores s ON s.id=l.store_id JOIN users u ON u.id=s.user_id
        WHERE l.status='active' AND u.is_blacklisted=0 AND (l.item_name LIKE ? OR l.category LIKE ?)
        ORDER BY l.created_at DESC LIMIT 20
        """, (f"%{q}%",f"%{q}%")
    )
    return jsonify([dict(r) for r in rows])


@app.errorhandler(413)
def too_large(_):
    flash("Image is too large. Maximum size is 5 MB.", "danger")
    return redirect(request.referrer or url_for("sell"))


@app.cli.command("reset-db")
def reset_db_command():
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
    print("Database reset.")


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))
