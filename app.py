import os
import sqlite3
from functools import wraps
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort, jsonify, request
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "local-development-key-change-before-deployment"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

DB_PATH = os.path.join(os.path.dirname(__file__), "sanchay.db")


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Admin', 'Staff')),
                state TEXT NOT NULL,
                district TEXT NOT NULL
            )
        """)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("home", page="signin"))
        return fn(*args, **kwargs)
    return wrapper


def role_required(role):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if session.get("role") != role:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


@app.route("/", methods=["GET", "POST"])
def home():
    page = request.args.get("page", "landing")
    error = None

    if request.method == "POST":
        role = request.form.get("role", "")
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE email = ? OR phone = ?",
                (identifier.lower(), identifier)
            ).fetchone()

        if not user or not check_password_hash(
            user["password_hash"], password
        ):
            page, error = "signin", "Invalid email/phone or password."
        elif user["role"] != role:
            page, error = "signin", "Choose the correct workspace for your account."
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["business"] = user["business"]

            return redirect(url_for(
                "admin" if user["role"] == "Admin" else "staff"
            ))

    return render_template("login.html", page=page, error=error)


@app.route("/signup", methods=["POST"])
def signup():
    business = request.form.get("business", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    state = request.form.get("state", "").strip()
    district = request.form.get("district", "").strip()

    if not all([business, email, phone, password, state, district]):
        flash("Please complete all fields.")
        return redirect(url_for("home", page="signup"))

    if len(password) < 8:
        flash("Use a password with at least 8 characters.")
        return redirect(url_for("home", page="signup"))

    try:
        with get_db() as db:
            count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

            # Prototype policy: first account is Admin, subsequent accounts Staff.
            # Replace with invitation-only staff creation before public deployment.
            role = "Admin" if count == 0 else "Staff"

            db.execute("""
                INSERT INTO users
                (business, email, phone, password_hash, role, state, district)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                business, email, phone,
                generate_password_hash(password),
                role, state, district
            ))
    except sqlite3.IntegrityError:
        flash("That email is already registered.")
        return redirect(url_for("home", page="signup"))

    flash(f"Account created as {role}. Please sign in.")
    return redirect(url_for("home", page="signin"))



def get_dashboard_metrics(user_id=None):
    from datetime import date

    today = date.today().isoformat()
    month = date.today().strftime("%Y-%m")

    with get_db() as db:
        products = db.execute(
            "SELECT COUNT(*) FROM products"
        ).fetchone()[0]
        units = db.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM products"
        ).fetchone()[0]
        stock_value = db.execute(
            "SELECT COALESCE(SUM(quantity * purchase_price), 0) FROM products"
        ).fetchone()[0]
        low_stock = db.execute(
            "SELECT COUNT(*) FROM products WHERE quantity <= low_stock_threshold"
        ).fetchone()[0]

        if user_id is None:
            today_sales = db.execute(
                "SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE date(created_at) = ?",
                (today,)
            ).fetchone()[0]
            month_sales = db.execute(
                "SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE strftime('%Y-%m', created_at) = ?",
                (month,)
            ).fetchone()[0]
            today_transactions = db.execute(
                "SELECT COUNT(*) FROM sales WHERE date(created_at) = ?",
                (today,)
            ).fetchone()[0]
        else:
            today_sales = db.execute(
                "SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE date(created_at) = ? AND created_by = ?",
                (today, user_id)
            ).fetchone()[0]
            month_sales = db.execute(
                "SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE strftime('%Y-%m', created_at) = ? AND created_by = ?",
                (month, user_id)
            ).fetchone()[0]
            today_transactions = db.execute(
                "SELECT COUNT(*) FROM sales WHERE date(created_at) = ? AND created_by = ?",
                (today, user_id)
            ).fetchone()[0]

    return {
        "products": products,
        "units": units,
        "stock_value": stock_value,
        "low_stock": low_stock,
        "today_sales": today_sales,
        "month_sales": month_sales,
        "today_transactions": today_transactions,
    }


@app.route("/admin")
@role_required("Admin")
def admin():
    return render_template(
        "dashboard.html",
        role="Admin",
        business=session.get("business", "Your Business"),
        metrics=get_dashboard_metrics()
    )


@app.route("/staff")
@role_required("Staff")
def staff():
    return render_template(
        "dashboard.html",
        role="Staff",
        business=session.get("business", "Your Business"),
        metrics=get_dashboard_metrics(session["user_id"])
    )




@app.route("/products", methods=["GET", "POST"])
@role_required("Admin")
def products():
    error = None
    if request.method == "POST":
        sku = request.form.get("sku", "").strip()
        barcode = request.form.get("barcode", "").strip() or None
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        batch_no = request.form.get("batch_no", "").strip()
        expiry_date = request.form.get("expiry_date", "").strip()

        try:
            quantity = int(request.form.get("quantity", "0"))
            purchase_price = float(request.form.get("purchase_price", "0"))
            selling_price = float(request.form.get("selling_price", "0"))
            threshold = int(request.form.get("low_stock_threshold", "5"))

            if not sku or not name:
                raise ValueError("SKU and product name are required.")
            if quantity < 0 or purchase_price < 0 or selling_price < 0 or threshold < 0:
                raise ValueError("Quantity, prices and threshold cannot be negative.")

            with get_db() as db:
                db.execute("""
                    INSERT INTO products
                    (sku, barcode, name, category, quantity, purchase_price,
                     selling_price, batch_no, expiry_date, low_stock_threshold)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (sku, barcode, name, category, quantity, purchase_price,
                      selling_price, batch_no, expiry_date, threshold))
            return redirect(url_for("products"))

        except ValueError as exc:
            error = str(exc) or "Enter valid numeric values."
        except sqlite3.IntegrityError:
            error = "SKU or barcode already exists. Use a unique value."

    search = request.args.get("q", "").strip()
    with get_db() as db:
        if search:
            rows = db.execute("""
                SELECT * FROM products
                WHERE name LIKE ? OR sku LIKE ? OR barcode LIKE ?
                   OR category LIKE ? OR batch_no LIKE ?
                ORDER BY name
            """, tuple(["%" + search + "%"] * 5)).fetchall()
        else:
            rows = db.execute("SELECT * FROM products ORDER BY name").fetchall()

        summary = db.execute("""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(quantity), 0) AS units,
                   COALESCE(SUM(quantity * purchase_price), 0) AS value,
                   COALESCE(SUM(quantity * selling_price), 0) AS retail_value,
                   COALESCE(SUM(CASE WHEN quantity <= low_stock_threshold
                                     THEN 1 ELSE 0 END), 0) AS low_stock
            FROM products
        """).fetchone()

    return render_template("products.html", products=rows,
                           summary=summary, error=error, search=search)


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@role_required("Admin")
def edit_product(product_id):
    error = None
    with get_db() as db:
        product = db.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()

    if product is None:
        abort(404)

    if request.method == "POST":
        sku = request.form.get("sku", "").strip()
        barcode = request.form.get("barcode", "").strip() or None
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        batch_no = request.form.get("batch_no", "").strip()
        expiry_date = request.form.get("expiry_date", "").strip()

        try:
            quantity = int(request.form.get("quantity", "0"))
            purchase_price = float(request.form.get("purchase_price", "0"))
            selling_price = float(request.form.get("selling_price", "0"))
            threshold = int(request.form.get("low_stock_threshold", "5"))

            if not sku or not name:
                raise ValueError("SKU and product name are required.")
            if min(quantity, purchase_price, selling_price, threshold) < 0:
                raise ValueError("Numbers cannot be negative.")

            with get_db() as db:
                db.execute("""
                    UPDATE products SET sku=?, barcode=?, name=?, category=?,
                    quantity=?, purchase_price=?, selling_price=?, batch_no=?,
                    expiry_date=?, low_stock_threshold=?
                    WHERE id=?
                """, (sku, barcode, name, category, quantity, purchase_price,
                      selling_price, batch_no, expiry_date, threshold, product_id))
            return redirect(url_for("products"))

        except ValueError as exc:
            error = str(exc) or "Enter valid numeric values."
        except sqlite3.IntegrityError:
            error = "SKU or barcode already exists."

    return render_template("product_edit.html", product=product, error=error)


@app.route("/products/<int:product_id>/delete", methods=["POST"])
@role_required("Admin")
def delete_product(product_id):
    with get_db() as db:
        product = db.execute(
            "SELECT id FROM products WHERE id=?", (product_id,)
        ).fetchone()
        if product is None:
            abort(404)

        # Keep products referenced by existing purchase/sale history.
        references = db.execute("""
            SELECT
              (SELECT COUNT(*) FROM sale_items WHERE product_id=?) +
              (SELECT COUNT(*) FROM purchase_items WHERE product_id=?)
        """, (product_id, product_id)).fetchone()[0]

        if references:
            flash("This product has transaction history and cannot be deleted. Set its stock to zero instead.")
        else:
            db.execute("DELETE FROM products WHERE id=?", (product_id,))
            flash("Product deleted.")

    return redirect(url_for("products"))


@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.errorhandler(403)
def forbidden(error):
    return (
        "<h1>403 — Access denied</h1>"
        "<p>You do not have permission to access this workspace.</p>"
        '<p><a href="/">Return to SANCHAY</a></p>',
        403
    )


init_db()


def init_all_tables():
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as schema_file:
        schema = schema_file.read()
    with get_db() as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(schema)

init_all_tables()


@app.route("/sales", methods=["GET", "POST"])
@login_required
def sales():
    cart = session.setdefault("sales_cart", {})

    if request.method == "POST":
        try:
            product_id = int(request.form.get("product_id", "0"))
            quantity = int(request.form.get("quantity", "0"))
        except (ValueError, TypeError):
            flash("Enter a valid product and quantity.", "error")
            return redirect(url_for("sales"))

        if quantity < 1:
            flash("Quantity must be at least 1.", "error")
            return redirect(url_for("sales"))

        with get_db() as db:
            product = db.execute(
                "SELECT id, name, quantity FROM products WHERE id = ?",
                (product_id,)
            ).fetchone()

        if not product:
            flash("Product not found.", "error")
        elif quantity > product["quantity"]:
            flash("Not enough stock available.", "error")
        else:
            key = str(product_id)
            cart[key] = int(cart.get(key, 0)) + quantity
            session["sales_cart"] = cart
            session.modified = True
            flash("Product added to cart.", "success")

        return redirect(url_for("sales"))

    with get_db() as db:
        products = db.execute(
            """SELECT id, sku, name, quantity, selling_price
               FROM products WHERE quantity > 0 ORDER BY name"""
        ).fetchall()

        recent_sales = db.execute(
            """SELECT id, receipt_number, total_amount, payment_method,
                      customer_name, created_at
               FROM sales ORDER BY id DESC LIMIT 20"""
        ).fetchall()

        cart_items = []
        cart_total = 0.0
        for key, qty in cart.items():
            product = db.execute(
                """SELECT id, sku, name, quantity, selling_price
                   FROM products WHERE id = ?""", (int(key),)
            ).fetchone()
            if product:
                item = dict(product)
                item["cart_quantity"] = int(qty)
                item["line_total"] = float(product["selling_price"]) * int(qty)
                cart_items.append(item)
                cart_total += item["line_total"]

    return render_template(
        "sales.html", products=products, cart_items=cart_items,
        cart_total=cart_total, recent_sales=recent_sales
    )


@app.route("/sales/cart/remove/<int:product_id>", methods=["POST"])
@login_required
def remove_from_sales_cart(product_id):
    cart = session.get("sales_cart", {})
    cart.pop(str(product_id), None)
    session["sales_cart"] = cart
    session.modified = True
    return redirect(url_for("sales"))


@app.route("/sales/cart/clear", methods=["POST"])
@login_required
def clear_sales_cart():
    session["sales_cart"] = {}
    return redirect(url_for("sales"))


@app.route("/sales/checkout", methods=["POST"])
@login_required
def checkout_sale():
    from datetime import datetime

    cart = session.get("sales_cart", {})
    if not cart:
        flash("Your cart is empty.", "error")
        return redirect(url_for("sales"))

    customer = request.form.get("customer_name", "").strip()[:120]
    payment = request.form.get("payment_method", "Cash").strip()
    if payment not in ("Cash", "UPI", "Card", "Other"):
        payment = "Cash"

    receipt_number = "SC-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
    sale_id = None

    try:
        with get_db() as db:
            db.execute("BEGIN IMMEDIATE")
            subtotal = 0.0
            verified_items = []

            for key, qty in cart.items():
                product = db.execute(
                    """SELECT id, name, quantity, selling_price
                       FROM products WHERE id = ?""", (int(key),)
                ).fetchone()

                qty = int(qty)
                if not product or qty < 1 or qty > product["quantity"]:
                    raise ValueError("Stock changed or is insufficient. Please review your cart.")

                line_total = float(product["selling_price"]) * qty
                subtotal += line_total
                verified_items.append((product, qty, line_total))

            cursor = db.execute(
                """INSERT INTO sales
                   (receipt_number, subtotal, discount, total_amount,
                    payment_method, customer_name, created_by)
                   VALUES (?, ?, 0, ?, ?, ?, ?)""",
                (receipt_number, subtotal, subtotal, payment, customer,
                 session.get("user_id"))
            )
            sale_id = cursor.lastrowid

            for product, qty, line_total in verified_items:
                db.execute(
                    """INSERT INTO sale_items
                       (sale_id, product_id, product_name, quantity,
                        unit_price, subtotal)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (sale_id, product["id"], product["name"], qty,
                     product["selling_price"], line_total)
                )
                db.execute(
                    "UPDATE products SET quantity = quantity - ? WHERE id = ?",
                    (qty, product["id"])
                )

            db.commit()

    except (ValueError, Exception) as e:
        # Do not create a partial sale if any step fails.
        flash("Sale was not completed: " + str(e), "error")
        return redirect(url_for("sales"))

    session["sales_cart"] = {}
    return redirect(url_for("sale_receipt", sale_id=sale_id))


@app.route("/sales/receipt/<int:sale_id>")
@login_required
def sale_receipt(sale_id):
    with get_db() as db:
        sale = db.execute(
            "SELECT * FROM sales WHERE id = ?", (sale_id,)
        ).fetchone()
        if not sale:
            abort(404)
        items = db.execute(
            "SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)
        ).fetchall()

    return render_template("sale_receipt.html", sale=sale, items=items)



def inventory_admin_required():
    if session.get("role") != "Admin":
        abort(403)


@app.route("/suppliers", methods=["GET", "POST"])
@login_required
def suppliers():
    inventory_admin_required()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()
        notes = request.form.get("notes", "").strip()

        if not name:
            flash("Supplier name is required.", "error")
            return redirect(url_for("suppliers"))

        with get_db() as db:
            db.execute(
                """INSERT INTO suppliers (name, phone, email, address, notes)
                   VALUES (?, ?, ?, ?, ?)""",
                (name, phone, email, address, notes)
            )
            db.commit()

        flash("Supplier added successfully.", "success")
        return redirect(url_for("suppliers"))

    with get_db() as db:
        supplier_rows = db.execute(
            """SELECT s.*,
                      (SELECT COUNT(*) FROM purchases p
                       WHERE p.supplier_id = s.id) AS purchase_count
               FROM suppliers s ORDER BY s.name"""
        ).fetchall()

    return render_template("suppliers.html", suppliers=supplier_rows)


@app.route("/purchases", methods=["GET", "POST"])
@login_required
def purchases():
    inventory_admin_required()

    if request.method == "POST":
        try:
            supplier_id = int(request.form.get("supplier_id", "0"))
            product_id = int(request.form.get("product_id", "0"))
            quantity = int(request.form.get("quantity", "0"))
            unit_cost = float(request.form.get("unit_cost", "0"))
        except (ValueError, TypeError):
            flash("Enter valid supplier, product, quantity and cost.", "error")
            return redirect(url_for("purchases"))

        invoice = request.form.get("invoice_number", "").strip()[:100]
        notes = request.form.get("notes", "").strip()[:1000]

        if quantity < 1 or unit_cost < 0:
            flash("Quantity must be positive and cost cannot be negative.", "error")
            return redirect(url_for("purchases"))

        total = round(quantity * unit_cost, 2)

        try:
            with get_db() as db:
                db.execute("BEGIN IMMEDIATE")

                supplier = db.execute(
                    "SELECT id FROM suppliers WHERE id = ?",
                    (supplier_id,)
                ).fetchone()
                product = db.execute(
                    "SELECT id FROM products WHERE id = ?",
                    (product_id,)
                ).fetchone()

                if not supplier or not product:
                    raise ValueError("Select an existing supplier and product.")

                cur = db.execute(
                    """INSERT INTO purchases
                       (supplier_id, invoice_number, total_amount, status,
                        notes, created_by)
                       VALUES (?, ?, ?, 'Received', ?, ?)""",
                    (supplier_id, invoice, total, notes,
                     session.get("user_id"))
                )
                purchase_id = cur.lastrowid

                db.execute(
                    """INSERT INTO purchase_items
                       (purchase_id, product_id, quantity, unit_cost, subtotal)
                       VALUES (?, ?, ?, ?, ?)""",
                    (purchase_id, product_id, quantity, unit_cost, total)
                )

                db.execute(
                    """UPDATE products
                       SET quantity = quantity + ?, purchase_price = ?
                       WHERE id = ?""",
                    (quantity, unit_cost, product_id)
                )

                db.commit()

        except Exception as e:
            flash("Purchase not saved: " + str(e), "error")
            return redirect(url_for("purchases"))

        flash("Purchase recorded and stock updated.", "success")
        return redirect(url_for("purchases"))

    with get_db() as db:
        supplier_rows = db.execute(
            "SELECT id, name FROM suppliers ORDER BY name"
        ).fetchall()
        product_rows = db.execute(
            "SELECT id, sku, name, quantity FROM products ORDER BY name"
        ).fetchall()
        purchase_rows = db.execute(
            """SELECT p.id, p.invoice_number, p.total_amount, p.status,
                      p.created_at, s.name AS supplier_name
               FROM purchases p
               LEFT JOIN suppliers s ON s.id = p.supplier_id
               ORDER BY p.id DESC LIMIT 100"""
        ).fetchall()

    return render_template(
        "purchases.html", suppliers=supplier_rows,
        products=product_rows, purchases=purchase_rows
    )



@app.route("/credits", methods=["GET", "POST"])
@login_required
def credits():
    import os
    import uuid
    from werkzeug.utils import secure_filename

    upload_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "static", "credit_evidence"
    )
    os.makedirs(upload_dir, exist_ok=True)

    if request.method == "POST":
        customer = request.form.get("customer_name", "").strip()
        phone = request.form.get("phone", "").strip()
        due_date = request.form.get("due_date", "").strip()
        notes = request.form.get("notes", "").strip()
        consent = request.form.get("photo_consent") == "yes"

        try:
            amount = float(request.form.get("amount", "0"))
        except (ValueError, TypeError):
            amount = 0

        if not customer or amount <= 0:
            flash("Enter a customer name and a positive amount.", "error")
            return redirect(url_for("credits"))

        photo_path = ""
        photo = request.files.get("photo")
        if photo and photo.filename:
            if not consent:
                flash("Customer consent is required to save photo evidence.", "error")
                return redirect(url_for("credits"))

            ext = os.path.splitext(secure_filename(photo.filename))[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                flash("Use a JPG, PNG or WEBP photo.", "error")
                return redirect(url_for("credits"))

            filename = uuid.uuid4().hex + ext
            photo.save(os.path.join(upload_dir, filename))
            photo_path = "credit_evidence/" + filename

        with get_db() as db:
            db.execute(
                """INSERT INTO credits
                   (customer_name, phone, amount, amount_paid, due_date,
                    photo_path, notes, status, created_by)
                   VALUES (?, ?, ?, 0, ?, ?, ?, 'Open', ?)""",
                (customer, phone, amount, due_date, photo_path, notes,
                 session.get("user_id"))
            )
            db.commit()

        flash("Borrowing record saved.", "success")
        return redirect(url_for("credits"))

    with get_db() as db:
        if session.get("role") == "Admin":
            records = db.execute(
                """SELECT c.*, u.email AS creator
                   FROM credits c LEFT JOIN users u ON u.id = c.created_by
                   ORDER BY c.id DESC"""
            ).fetchall()
        else:
            records = db.execute(
                """SELECT c.*, u.email AS creator
                   FROM credits c LEFT JOIN users u ON u.id = c.created_by
                   WHERE c.created_by = ? ORDER BY c.id DESC""",
                (session.get("user_id"),)
            ).fetchall()

        total_outstanding = sum(
            max(0, float(r["amount"]) - float(r["amount_paid"]))
            for r in records
        )

    return render_template(
        "credits.html", credits=records,
        total_outstanding=total_outstanding
    )


@app.route("/credits/<int:credit_id>/payment", methods=["POST"])
@login_required
def credit_payment(credit_id):
    try:
        amount = float(request.form.get("amount", "0"))
    except (ValueError, TypeError):
        amount = 0

    notes = request.form.get("notes", "").strip()[:500]
    if amount <= 0:
        flash("Repayment must be greater than zero.", "error")
        return redirect(url_for("credits"))

    try:
        with get_db() as db:
            db.execute("BEGIN IMMEDIATE")
            if session.get("role") == "Admin":
                record = db.execute(
                    "SELECT * FROM credits WHERE id = ?", (credit_id,)
                ).fetchone()
            else:
                record = db.execute(
                    """SELECT * FROM credits
                       WHERE id = ? AND created_by = ?""",
                    (credit_id, session.get("user_id"))
                ).fetchone()

            if not record:
                raise ValueError("Borrowing record not found or access denied.")

            outstanding = float(record["amount"]) - float(record["amount_paid"])
            if amount > outstanding + 0.000001:
                raise ValueError("Repayment cannot exceed the outstanding balance.")

            new_paid = float(record["amount_paid"]) + amount
            status = "Paid" if new_paid >= float(record["amount"]) else "Open"

            db.execute(
                """INSERT INTO credit_payments
                   (credit_id, amount, notes, received_by)
                   VALUES (?, ?, ?, ?)""",
                (credit_id, amount, notes, session.get("user_id"))
            )
            db.execute(
                "UPDATE credits SET amount_paid = ?, status = ? WHERE id = ?",
                (new_paid, status, credit_id)
            )
            db.commit()

    except Exception as e:
        flash("Repayment not saved: " + str(e), "error")
        return redirect(url_for("credits"))

    flash("Repayment recorded successfully.", "success")
    return redirect(url_for("credits"))


@app.route("/credits/<int:credit_id>/history")
@login_required
def credit_history(credit_id):
    with get_db() as db:
        if session.get("role") == "Admin":
            record = db.execute(
                "SELECT * FROM credits WHERE id = ?", (credit_id,)
            ).fetchone()
        else:
            record = db.execute(
                """SELECT * FROM credits WHERE id = ? AND created_by = ?""",
                (credit_id, session.get("user_id"))
            ).fetchone()

        if not record:
            abort(404)

        payments = db.execute(
            """SELECT cp.*, u.email AS receiver
               FROM credit_payments cp
               LEFT JOIN users u ON u.id = cp.received_by
               WHERE cp.credit_id = ? ORDER BY cp.id DESC""",
            (credit_id,)
        ).fetchall()

    return render_template(
        "credit_history.html", credit=record, payments=payments
    )



@app.route("/reports")
@login_required
def reports():
    from datetime import date, timedelta

    today = date.today()
    start = request.args.get(
        "start", today.replace(day=1).isoformat()
    )
    end = request.args.get("end", today.isoformat())

    try:
        date.fromisoformat(start)
        date.fromisoformat(end)
        if start > end:
            raise ValueError("Start date must not be after end date.")
    except ValueError:
        flash("Please select a valid date range.", "error")
        return redirect(url_for("reports"))

    with get_db() as db:
        sales = db.execute("""
            SELECT COUNT(*) AS transactions,
                   COALESCE(SUM(total_amount), 0) AS revenue,
                   COALESCE(SUM(discount), 0) AS discounts
            FROM sales
            WHERE date(created_at) BETWEEN ? AND ?
        """, (start, end)).fetchone()

        purchases = db.execute("""
            SELECT COUNT(*) AS transactions,
                   COALESCE(SUM(total_amount), 0) AS total
            FROM purchases
            WHERE date(created_at) BETWEEN ? AND ?
              AND status = 'Received'
        """, (start, end)).fetchone()

        top_products = db.execute("""
            SELECT si.product_name AS name,
                   SUM(si.quantity) AS units,
                   SUM(si.subtotal) AS revenue
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            WHERE date(s.created_at) BETWEEN ? AND ?
            GROUP BY si.product_name
            ORDER BY units DESC, revenue DESC
            LIMIT 10
        """, (start, end)).fetchall()

        low_stock = db.execute("""
            SELECT name, sku, quantity, low_stock_threshold
            FROM products
            WHERE quantity <= low_stock_threshold
            ORDER BY quantity ASC, name ASC
            LIMIT 20
        """).fetchall()

        daily_sales = db.execute("""
            SELECT date(created_at) AS day,
                   COUNT(*) AS transactions,
                   COALESCE(SUM(total_amount), 0) AS revenue
            FROM sales
            WHERE date(created_at) BETWEEN ? AND ?
            GROUP BY date(created_at)
            ORDER BY day DESC
        """, (start, end)).fetchall()

    return render_template(
        "reports.html",
        start=start,
        end=end,
        sales=sales,
        purchases=purchases,
        top_products=top_products,
        low_stock=low_stock,
        daily_sales=daily_sales
    )

import re
import re
import sqlite3
from flask import jsonify, request, session

UNKNOWN = "Sorry, I don't know."

FAQ_GROUPS = {
    "inventory": (
        "Inventory is the list of products your business tracks, including quantities and prices.",
        ["what is inventory", "explain inventory", "what does inventory mean", "what is stock management", "tell me about inventory"]
    ),
    "add_product": (
        "To add a product, open Inventory, complete the product details, including its name, quantity and prices, and save it. This module is available to Admin accounts.",
        ["how do i add a product", "how to add a new product", "where can i add products", "steps to create a product", "how can i enter a new item"]
    ),
    "edit_product": (
        "Open Inventory, find the product, choose its edit option, update the required fields and save your changes. This module is available to Admin accounts.",
        ["how do i edit a product", "how to update product details", "how can i change a product price", "how do i update stock details", "where can i edit an item"]
    ),
    "delete_product": (
        "If your account has permission, open Inventory and use the product's delete option. Check the product carefully before confirming because deleting records may affect your workflow.",
        ["how do i delete a product", "how can i remove an item", "where can i delete products", "how to remove a product from inventory", "can i delete an item"]
    ),
    "sku": (
        "SKU means Stock Keeping Unit. It is an identifier used to distinguish and track a product in your inventory.",
        ["what is sku", "what does sku mean", "explain stock keeping unit", "why use a sku", "what is a product sku"]
    ),
    "barcode": (
        "A barcode is a machine-readable code used to identify a product. Whether scanning is available depends on the controls implemented in your current SANCHAY version.",
        ["what is a barcode", "why are barcodes used", "what does a product barcode do", "explain barcode tracking", "can a barcode identify an item"]
    ),
    "low_stock": (
        "Low stock identifies products whose available quantity is at or below their configured low-stock threshold. Review these products and plan replenishment.",
        ["what is low stock", "what does low stock mean", "how is low stock identified", "when is an item low in stock", "explain low stock alerts"]
    ),
    "purchase_price": (
        "Purchase price is the cost paid to acquire a product. Use the actual recorded cost when reviewing inventory value or margins.",
        ["what is purchase price", "explain product cost", "what does buying price mean", "difference between purchase and selling price", "what is cost price"]
    ),
    "selling_price": (
        "Selling price is the price charged to a customer for a product. Check the saved product record for the actual price.",
        ["what is selling price", "what price do i charge customers", "explain sale price", "what does retail price mean", "how is selling price different from cost"]
    ),
    "profit": (
        "A basic product-level gross margin estimate is selling price minus purchase cost. Actual profit may also depend on discounts, expenses, taxes and other costs.",
        ["how do i estimate product profit", "what is gross margin", "how is profit calculated on an item", "what is the difference between revenue and profit", "does sales revenue equal profit"]
    ),
    "sales": (
        "Open Sales & Billing to record a sale and review the sales workflow available to your account.",
        ["how do i record a sale", "where do i create a bill", "how can i sell a product", "how do i use sales and billing", "where can i manage sales"]
    ),
    "receipt": (
        "After a sale is completed, use the receipt option associated with that transaction if available.",
        ["how do i get a sales receipt", "where can i find a receipt", "how do i view a bill", "how can i open a sale receipt", "where is the transaction receipt"]
    ),
    "purchases": (
        "Open Purchases to record a stock purchase and enter the relevant supplier, invoice and item details. This module is available to Admin accounts.",
        ["how do i record a purchase", "where can i enter stock purchases", "how do i register a supplier purchase", "how to track purchases", "where is the purchases module"]
    ),
    "suppliers": (
        "Open Suppliers to view and manage supplier records. This module is available to Admin accounts.",
        ["how do i manage suppliers", "where can i add a supplier", "how do i find supplier details", "what is the suppliers module", "where are supplier records"]
    ),
    "credits": (
        "Open Credit & Borrowing to manage customer credit records and repayments. This module is available to Admin accounts.",
        ["how do i record customer credit", "where can i manage borrowing", "how do i track customer dues", "where is credit management", "how can i record a repayment"]
    ),
    "reports": (
        "Open Reports & Analytics to review the reports provided by your SANCHAY account.",
        ["where can i find reports", "how do i view business reports", "where is analytics", "how can i review sales reports", "what is the reports module"]
    ),
    "supplier_meaning": (
        "A supplier is a person or business from which your business obtains products or stock.",
        ["what is a supplier", "explain supplier management", "why do i need supplier records", "what does supplier mean", "who is a supplier in inventory"]
    ),
    "expiry": (
        "Track expiry dates where relevant to your products. Review the saved expiry date and follow the handling requirements that apply to your goods.",
        ["how do i track expiry dates", "why record product expiry", "what is expiry tracking", "how should i check product expiry", "why is expiry date important"]
    ),
    "stock_value": (
        "Stock purchase value is generally estimated from the quantity on hand multiplied by the recorded purchase cost. Check the dashboard or reports for the figures available in your account.",
        ["what is stock value", "how is inventory value estimated", "what does stock purchase value mean", "how do i value current stock", "what is inventory valuation"]
    ),
    "staff_admin": (
        "SANCHAY has Admin and Staff roles. Admin access includes additional management modules; the options visible to Staff are more limited.",
        ["what is the difference between admin and staff", "what can an admin do", "why can staff not access every module", "what are user roles", "why is a module unavailable to me"]
    ),
    "login": (
        "Sign in using the account credentials registered for SANCHAY. If you cannot sign in, verify your email or phone and password.",
        ["how do i log in", "how can i sign in", "i cannot log in what should i check", "how do i access my account", "where do i sign in"]
    ),
    "logout": (
        "Use the Log out option in the application navigation to end your current session.",
        ["how do i log out", "where is the logout button", "how can i sign out", "how do i end my session", "how to exit my account safely"]
    ),
    "data_accuracy": (
        "For actual business figures, use the records saved in SANCHAY. The chatbot only answers supported questions and does not invent missing quantities, prices or transactions.",
        ["how do i verify stock figures", "are chatbot answers based on my records", "can the chatbot guess missing stock", "how do i check data accuracy", "what if the chatbot does not know an answer"]
    ),
    "unknown_help": (
        "I can help with supported SANCHAY inventory, sales, purchases, suppliers, credit and reports questions.",
        ["what can you help me with", "what can i ask the chatbot", "what topics do you support", "how can you help me", "show me what you can answer"]
    ),
}

FAQS = {}
for answer, aliases in FAQ_GROUPS.values():
    for alias in aliases:
        FAQS[re.sub(r"[^a-z0-9 ]", "", alias.lower()).strip()] = answer


def register_chatbot(app, get_db, login_required):
    @app.route("/api/chat", methods=["POST"])
    @login_required
    def chatbot_api():
        body = request.get_json(silent=True) or {}
        question = body.get("message", "")
        if not isinstance(question, str):
            return jsonify({"answer": UNKNOWN}), 200

        question = re.sub(r"\s+", " ", question.strip().lower())
        normalized = re.sub(r"[^a-z0-9 ]", "", question).strip()
        if not normalized or len(normalized) > 250:
            return jsonify({"answer": UNKNOWN}), 200

        user_id = session.get("user_id")
        role = session.get("role")

        # Deterministic answers based only on saved database records.
        try:
            with get_db() as db:
                if normalized in {
                    "how many products", "how many products do i have",
                    "total products", "count my products", "number of products"
                }:
                    row = db.execute("SELECT COUNT(*) AS n FROM products").fetchone()
                    answer = f"There are {row['n']} products in the inventory."

                elif normalized in {
                    "how many units in stock", "total units in stock",
                    "total stock", "how many items are in stock",
                    "what is my total stock quantity"
                }:
                    row = db.execute("SELECT COALESCE(SUM(quantity), 0) AS n FROM products").fetchone()
                    answer = f"The recorded total stock quantity is {row['n']} units."

                elif normalized in {
                    "show low stock", "which products are low in stock",
                    "list low stock products", "what items need restocking",
                    "which products need restocking",
                    "which items need restocking",
                    "what products need restocking",
                    "which items are low in stock",
                    "show me low stock items",
                    "what should i restock",
                    "what needs restocking"
                }:
                    rows = db.execute("""
                        SELECT name, quantity, low_stock_threshold
                        FROM products
                        WHERE quantity <= low_stock_threshold
                        ORDER BY quantity, name LIMIT 10
                    """).fetchall()
                    answer = (
                        "Low-stock products: " + "; ".join(
                            f"{r['name']} ({r['quantity']} left; threshold {r['low_stock_threshold']})"
                            for r in rows
                        ) if rows else "No products currently meet the saved low-stock threshold."
                    )

                elif normalized in {
                    "how many suppliers", "count suppliers", "total suppliers",
                    "number of suppliers"
                } and role == "Admin":
                    row = db.execute("SELECT COUNT(*) AS n FROM suppliers").fetchone()
                    answer = f"There are {row['n']} supplier records."

                elif normalized in {
                    "how much credit is outstanding", "total outstanding credit",
                    "how much do customers owe", "total customer dues",
                    "what is the outstanding balance"
                } and role == "Admin":
                    row = db.execute("""
                        SELECT COALESCE(SUM(MAX(amount - amount_paid, 0)), 0) AS n
                        FROM credits
                    """).fetchone()
                    answer = f"The recorded outstanding customer credit is ₹{row['n']:.2f}."

                else:
                    answer = None

                if answer is not None:
                    return jsonify({"answer": answer})

                # Explicit product lookups only; ambiguous names are not guessed.
                match = re.match(
                    r"^(?:stock|quantity|selling price|purchase price|price|details) of (.+)$",
                    normalized
                )
                if match:
                    term = match.group(1).strip()
                    rows = db.execute("""
                        SELECT name, quantity, selling_price, purchase_price
                        FROM products
                        WHERE lower(name) = ?
                           OR lower(sku) = ?
                           OR lower(barcode) = ?
                        LIMIT 2
                    """, (term, term, term)).fetchall()
                    if len(rows) == 1:
                        p = rows[0]
                        if normalized.startswith(("stock of ", "quantity of ")):
                            answer = f"{p['name']}: {p['quantity']} units in recorded stock."
                        elif normalized.startswith("selling price of "):
                            answer = f"{p['name']}: recorded selling price ₹{p['selling_price']:.2f}."
                        elif normalized.startswith("purchase price of "):
                            answer = f"{p['name']}: recorded purchase price ₹{p['purchase_price']:.2f}."
                        else:
                            answer = (
                                f"{p['name']}: {p['quantity']} units; "
                                f"selling price ₹{p['selling_price']:.2f}; "
                                f"purchase price ₹{p['purchase_price']:.2f}."
                            )
                        return jsonify({"answer": answer})
                    return jsonify({"answer": UNKNOWN})

        except (sqlite3.Error, KeyError, TypeError, ValueError):
            app.logger.exception("Chatbot database lookup failed")
            return jsonify({"answer": UNKNOWN}), 200

        answer = FAQS.get(normalized)

        # Match common variations without guessing unrelated answers.
        if answer is None:
            from difflib import SequenceMatcher

            best_score = 0
            best_answer = None

            question_words = set(normalized.split())

            for alias, candidate_answer in FAQS.items():
                alias_words = set(alias.split())

                if alias in normalized or normalized in alias:
                    best_answer = candidate_answer
                    best_score = 1
                    break

                if not alias_words or not question_words:
                    continue

                overlap = len(question_words & alias_words) / len(
                    question_words | alias_words
                )
                similarity = SequenceMatcher(
                    None, normalized, alias
                ).ratio()
                score = max(overlap, similarity)

                if score > best_score:
                    best_score = score
                    best_answer = candidate_answer

            answer = best_answer if best_score >= 0.72 else UNKNOWN

        return jsonify({"answer": answer})

register_chatbot(app, get_db, login_required)

if __name__ == "__main__":
    app.run(debug=True)
