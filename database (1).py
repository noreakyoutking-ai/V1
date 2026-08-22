import logging
import os
import sqlite3
from contextlib import contextmanager
from premium_emoji import entities_for
from config import DB_PATH, OWNER_IDS

logger = logging.getLogger(__name__)

# One-time database reset switch. Set the RESET_DB=1 environment variable and
# restart the service to wipe the existing (stale) database file so a fresh,
# empty one is created by init_db() on startup. Remove/unset the variable
# afterwards - leaving it set to 1 would wipe the DB on every restart.
if os.getenv("RESET_DB") == "1":
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        logger.info(f"RESET_DB=1 - deleted existing database: {DB_PATH}")
    else:
        logger.info(f"RESET_DB=1 - no existing database found at {DB_PATH}, nothing to delete")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        description TEXT DEFAULT '',
        photo_file_id TEXT,
        delivery_info TEXT DEFAULT '',
        totp_secret TEXT DEFAULT '',
        quantity INTEGER DEFAULT 1,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        buyer_chat_id INTEGER NOT NULL,
        buyer_username TEXT,
        payment_photo_file_id TEXT,
        status TEXT DEFAULT 'pending',
        khqr_md5 TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        approved_at TEXT
    )""")
    # --- lightweight migrations for DBs created before these columns existed ---
    for table, col, decl in [
        ("items", "totp_secret", "TEXT DEFAULT ''"),
        ("orders", "khqr_md5", "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass  # column already exists
    c.execute("""CREATE TABLE IF NOT EXISTS admins (
        chat_id INTEGER PRIMARY KEY,
        username TEXT,
        added_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        username TEXT,
        first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
        last_seen TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS guides (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        video_url TEXT NOT NULL,
        added_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS coupons (
        code TEXT PRIMARY KEY,
        discount_type TEXT NOT NULL,
        amount REAL NOT NULL,
        max_uses INTEGER NOT NULL,
        used_count INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS coupon_redemptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        buyer_chat_id INTEGER NOT NULL,
        order_id INTEGER,
        redeemed_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(code, buyer_chat_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS spin_pool (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        weight REAL NOT NULL,
        active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS spin_credits (
        chat_id INTEGER PRIMARY KEY,
        credits INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS spin_wins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        username TEXT,
        reward_name TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        delivered_at TEXT
    )""")

    # Migrations for columns added after initial release - safe to re-run on existing databases.
    # NOTE: published defaults to 1 in the migration so existing live stock stays visible after
    # upgrading - only NEWLY added items default to draft (published=0) going forward.
    for stmt in [
        "ALTER TABLE items ADD COLUMN warranty_days INTEGER DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN approved_at TEXT",
        "ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'km'",
        "ALTER TABLE items ADD COLUMN published INTEGER DEFAULT 1",
        "ALTER TABLE items ADD COLUMN released_at TEXT",
        "ALTER TABLE orders ADD COLUMN coupon_code TEXT",
        "ALTER TABLE orders ADD COLUMN discount_amount REAL DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN final_price REAL",
    ]:
        try:
            c.execute(stmt)
        except sqlite3.OperationalError:
            pass  # column already exists

    conn.commit()
    conn.close()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()


# ---- Items ----

def add_item(category, name, price, description, photo_file_id, delivery_info, quantity, warranty_days=0, published=0):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO items (category, name, price, description, photo_file_id, delivery_info, quantity, warranty_days, published) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (category, name, price, description, photo_file_id, delivery_info, quantity, warranty_days, published),
        )
        return cur.lastrowid


def get_items_by_category(category, only_active=True):
    with get_conn() as conn:
        q = "SELECT * FROM items WHERE category = ?"
        if only_active:
            q += " AND active = 1 AND quantity > 0 AND published = 1"
        q += " ORDER BY id DESC"
        return conn.execute(q, (category,)).fetchall()


def get_all_items():
    """Everything, any status - for the ADMIN side (listitems, admin panel)."""
    with get_conn() as conn:
        return conn.execute("SELECT * FROM items ORDER BY category, id DESC").fetchall()


def get_published_items():
    """Only live/visible-to-buyers items - for the STORE side (Store Bot, Mini App)."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM items WHERE published = 1 AND active = 1 AND quantity > 0 ORDER BY category, id DESC"
        ).fetchall()


def get_draft_items():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM items WHERE published = 0 ORDER BY id DESC").fetchall()


def release_all_drafts():
    """Publish every draft item at once, stamping released_at so 'New/Restocked' badges
    can be computed from it. Returns the list of items that were just published."""
    with get_conn() as conn:
        drafts = conn.execute("SELECT * FROM items WHERE published = 0").fetchall()
        conn.execute("UPDATE items SET published = 1, released_at = CURRENT_TIMESTAMP WHERE published = 0")
    return drafts


def get_item(item_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()


def update_item_field(item_id, field, value):
    allowed = {"category", "name", "price", "description", "photo_file_id",
               "delivery_info", "totp_secret", "quantity", "active", "warranty_days", "published"}
    if field not in allowed:
        raise ValueError("bad field")
    with get_conn() as conn:
        conn.execute(f"UPDATE items SET {field} = ? WHERE id = ?", (value, item_id))


def delete_item(item_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))


def decrement_stock(item_id):
    with get_conn() as conn:
        conn.execute("UPDATE items SET quantity = MAX(quantity - 1, 0) WHERE id = ?", (item_id,))
        row = conn.execute("SELECT quantity FROM items WHERE id = ?", (item_id,)).fetchone()
        if row and row["quantity"] <= 0:
            conn.execute("UPDATE items SET active = 0 WHERE id = ?", (item_id,))


# ---- Orders ----

def create_order(item_id, buyer_chat_id, buyer_username, payment_photo_file_id,
                  coupon_code=None, discount_amount=0, final_price=None):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO orders (item_id, buyer_chat_id, buyer_username, payment_photo_file_id, "
            "coupon_code, discount_amount, final_price) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (item_id, buyer_chat_id, buyer_username, payment_photo_file_id, coupon_code, discount_amount, final_price),
        )
        return cur.lastrowid


def get_order(order_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def get_orders_by_status(status="pending"):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders WHERE status = ? ORDER BY id DESC", (status,)).fetchall()


def update_order_status(order_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))


def set_order_approved(order_id):
    with get_conn() as conn:
        conn.execute("UPDATE orders SET status = 'approved', approved_at = CURRENT_TIMESTAMP WHERE id = ?", (order_id,))


def set_order_khqr_md5(order_id, md5):
    with get_conn() as conn:
        conn.execute("UPDATE orders SET khqr_md5 = ? WHERE id = ?", (md5, order_id))


def get_orders_by_buyer(chat_id, limit=20):
    with get_conn() as conn:
        return conn.execute(
            """SELECT orders.*, items.name AS item_name, items.category AS item_category,
                      items.warranty_days AS warranty_days
               FROM orders JOIN items ON orders.item_id = items.id
               WHERE orders.buyer_chat_id = ?
               ORDER BY orders.id DESC LIMIT ?""",
            (chat_id, limit),
        ).fetchall()


def get_recent_orders(limit=20):
    with get_conn() as conn:
        return conn.execute(
            """SELECT orders.*, items.name AS item_name, items.category AS item_category
               FROM orders JOIN items ON orders.item_id = items.id
               ORDER BY orders.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()


# ---- Admins / sellers ----

def add_seller(chat_id, username=None):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO admins (chat_id, username) VALUES (?, ?)", (chat_id, username))


def remove_seller(chat_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM admins WHERE chat_id = ?", (chat_id,))


def list_sellers():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM admins ORDER BY added_at").fetchall()


def is_admin_id(chat_id):
    if chat_id in OWNER_IDS:
        return True
    with get_conn() as conn:
        row = conn.execute("SELECT 1 FROM admins WHERE chat_id = ?", (chat_id,)).fetchone()
        return row is not None


def all_admin_ids():
    with get_conn() as conn:
        rows = conn.execute("SELECT chat_id FROM admins").fetchall()
    return list(set(OWNER_IDS) | {r["chat_id"] for r in rows})


# ---- Settings (payment QR / note / rules / codes / tierlist) ----

def set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


def get_setting(key, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


# ---- Users (who uses the store bot) ----

def track_user(chat_id, username):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (chat_id, username) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET username = excluded.username, last_seen = CURRENT_TIMESTAMP",
            (chat_id, username),
        )


def count_users():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]


def set_user_lang(chat_id, lang):
    with get_conn() as conn:
        conn.execute("UPDATE users SET lang = ? WHERE chat_id = ?", (lang, chat_id))


def get_user_lang(chat_id):
    with get_conn() as conn:
        row = conn.execute("SELECT lang FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
    return row["lang"] if row and row["lang"] else "km"


def list_users(limit=30):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users ORDER BY last_seen DESC LIMIT ?", (limit,)).fetchall()


def count_orders_by_status():
    with get_conn() as conn:
        rows = conn.execute("SELECT status, COUNT(*) c FROM orders GROUP BY status").fetchall()
    return {r["status"]: r["c"] for r in rows}


# ---- Guides (tutorial video links) ----

def add_guide(title, video_url):
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO guides (title, video_url) VALUES (?, ?)", (title, video_url))
        return cur.lastrowid


def list_guides():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM guides ORDER BY id").fetchall()


def get_guide(guide_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM guides WHERE id = ?", (guide_id,)).fetchone()


def delete_guide(guide_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM guides WHERE id = ?", (guide_id,))


# ---- Coupons ----

def add_coupon(code, discount_type, amount, max_uses):
    code = code.strip().upper()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO coupons (code, discount_type, amount, max_uses, used_count, active) "
            "VALUES (?, ?, ?, ?, 0, 1)",
            (code, discount_type, amount, max_uses),
        )
    return code


def get_coupon(code):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM coupons WHERE code = ?", (code.strip().upper(),)).fetchone()


def list_coupons():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM coupons ORDER BY created_at DESC").fetchall()


def disable_coupon(code):
    with get_conn() as conn:
        conn.execute("UPDATE coupons SET active = 0 WHERE code = ?", (code.strip().upper(),))


def validate_coupon(code, buyer_chat_id):
    """Checks a coupon is usable by this specific buyer right now. Returns (coupon_row, None)
    on success or (None, error_code) on failure. Does NOT consume it - call redeem_coupon
    only once the order is actually placed, so a browsed-but-abandoned checkout doesn't burn it."""
    coupon = get_coupon(code)
    if not coupon or not coupon["active"]:
        return None, "not_found"
    if coupon["used_count"] >= coupon["max_uses"]:
        return None, "exhausted"
    with get_conn() as conn:
        already = conn.execute(
            "SELECT 1 FROM coupon_redemptions WHERE code = ? AND buyer_chat_id = ?",
            (coupon["code"], buyer_chat_id),
        ).fetchone()
    if already:
        return None, "already_used"
    return coupon, None


def redeem_coupon(code, buyer_chat_id, order_id=None):
    """Atomically records the redemption and bumps used_count. Call this only after
    validate_coupon succeeded, at the moment the order is actually created."""
    code = code.strip().upper()
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO coupon_redemptions (code, buyer_chat_id, order_id) VALUES (?, ?, ?)",
                (code, buyer_chat_id, order_id),
            )
        except sqlite3.IntegrityError:
            return False  # already redeemed by this buyer (race condition safety net)
        conn.execute("UPDATE coupons SET used_count = used_count + 1 WHERE code = ?", (code,))
    return True


def apply_discount(price, coupon):
    if coupon["discount_type"] == "percent":
        discount = round(price * (coupon["amount"] / 100), 2)
    else:
        discount = min(coupon["amount"], price)
    final_price = max(0, round(price - discount, 2))
    return final_price, discount


# ---- Spin wheel (free - unlocked after buying an Account, NOT a paid gambling mechanic) ----

def add_spin_item(name, weight):
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO spin_pool (name, weight) VALUES (?, ?)", (name, weight))
        return cur.lastrowid


def list_spin_items(only_active=True):
    with get_conn() as conn:
        q = "SELECT * FROM spin_pool"
        if only_active:
            q += " WHERE active = 1"
        q += " ORDER BY weight DESC"
        return conn.execute(q).fetchall()


def remove_spin_item(item_id):
    with get_conn() as conn:
        conn.execute("UPDATE spin_pool SET active = 0 WHERE id = ?", (item_id,))


def grant_spin_credit(chat_id, amount=1):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO spin_credits (chat_id, credits) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET credits = credits + excluded.credits",
            (chat_id, amount),
        )


def get_spin_credits(chat_id):
    with get_conn() as conn:
        row = conn.execute("SELECT credits FROM spin_credits WHERE chat_id = ?", (chat_id,)).fetchone()
    return row["credits"] if row else 0


def consume_spin_credit(chat_id):
    """Atomically consumes one credit if available. Returns True if a credit was spent."""
    with get_conn() as conn:
        row = conn.execute("SELECT credits FROM spin_credits WHERE chat_id = ?", (chat_id,)).fetchone()
        if not row or row["credits"] < 1:
            return False
        conn.execute("UPDATE spin_credits SET credits = credits - 1 WHERE chat_id = ?", (chat_id,))
        return True


def record_spin_win(chat_id, username, reward_name):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO spin_wins (chat_id, username, reward_name) VALUES (?, ?, ?)",
            (chat_id, username, reward_name),
        )
        return cur.lastrowid


def get_pending_spin_wins():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM spin_wins WHERE status = 'pending' ORDER BY id").fetchall()


def mark_spin_delivered(win_id):
    with get_conn() as conn:
        conn.execute("UPDATE spin_wins SET status = 'delivered', delivered_at = CURRENT_TIMESTAMP WHERE id = ?", (win_id,))
