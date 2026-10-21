import os
import sqlite3
from functools import wraps
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort
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

if __name__ == "__main__":
    app.run(debug=True)
