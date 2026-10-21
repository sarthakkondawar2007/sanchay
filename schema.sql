CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    barcode TEXT UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
    purchase_price REAL NOT NULL DEFAULT 0 CHECK(purchase_price >= 0),
    selling_price REAL NOT NULL DEFAULT 0 CHECK(selling_price >= 0),
    batch_no TEXT NOT NULL DEFAULT '',
    expiry_date TEXT NOT NULL DEFAULT '',
    low_stock_threshold INTEGER NOT NULL DEFAULT 5,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER,
    invoice_number TEXT NOT NULL DEFAULT '',
    total_amount REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'Received',
    notes TEXT NOT NULL DEFAULT '',
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(supplier_id) REFERENCES suppliers(id),
    FOREIGN KEY(created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS purchase_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_cost REAL NOT NULL CHECK(unit_cost >= 0),
    subtotal REAL NOT NULL CHECK(subtotal >= 0),
    FOREIGN KEY(purchase_id) REFERENCES purchases(id) ON DELETE CASCADE,
    FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_number TEXT NOT NULL UNIQUE,
    subtotal REAL NOT NULL DEFAULT 0,
    discount REAL NOT NULL DEFAULT 0,
    total_amount REAL NOT NULL DEFAULT 0,
    payment_method TEXT NOT NULL DEFAULT 'Cash',
    customer_name TEXT NOT NULL DEFAULT '',
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price REAL NOT NULL CHECK(unit_price >= 0),
    subtotal REAL NOT NULL CHECK(subtotal >= 0),
    FOREIGN KEY(sale_id) REFERENCES sales(id) ON DELETE CASCADE,
    FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS credits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    amount REAL NOT NULL CHECK(amount > 0),
    amount_paid REAL NOT NULL DEFAULT 0 CHECK(amount_paid >= 0),
    due_date TEXT NOT NULL DEFAULT '',
    photo_path TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Open',
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS credit_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credit_id INTEGER NOT NULL,
    amount REAL NOT NULL CHECK(amount > 0),
    notes TEXT NOT NULL DEFAULT '',
    received_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(credit_id) REFERENCES credits(id),
    FOREIGN KEY(received_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_sales_created_at ON sales(created_at);
CREATE INDEX IF NOT EXISTS idx_purchases_created_at ON purchases(created_at);
CREATE INDEX IF NOT EXISTS idx_credits_status ON credits(status);
