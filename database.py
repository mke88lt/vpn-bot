import sqlite3
from datetime import datetime, timedelta

def init_db():
    conn = sqlite3.connect("vpn_bot.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        joined_at TEXT,
        is_banned INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        plan TEXT,
        config TEXT,
        start_date TEXT,
        end_date TEXT,
        volume_gb INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        plan TEXT,
        amount INTEGER,
        status TEXT DEFAULT 'pending',
        receipt_file_id TEXT,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        config_text TEXT,
        is_used INTEGER DEFAULT 0,
        plan TEXT
    )""")
    conn.commit()
    conn.close()

def add_user(user_id, username, full_name):
    conn = sqlite3.connect("vpn_bot.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at) VALUES (?,?,?,?)",
              (user_id, username, full_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("vpn_bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id, username, full_name, joined_at FROM users WHERE is_banned=0")
    rows = c.fetchall()
    conn.close()
    return rows

def create_order(user_id, plan, amount):
    conn = sqlite3.connect("vpn_bot.db")
    c = conn.cursor()
    c.execute("INSERT INTO orders (user_id, plan, amount, created_at) VALUES (?,?,?,?)",
              (user_id, plan, amount, datetime.now().isoformat()))
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    return order_id

def update_order_receipt(order_id, receipt_file_id):
    conn = sqlite3.connect("vpn_bot.db")
    c = conn.cursor()
    c.execute("UPDATE orders SET receipt_file_id=?, status='waiting' WHERE id=?",
              (receipt_file_id, order_id))
    conn.commit()
    conn.close()

def get_pending_orders():
    conn = sqlite3.connect("vpn_bot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE status='waiting'")
    rows = c.fetchall()
    conn.close()
    return rows

def approve_order(order_id):
    conn = sqlite3.connect("vpn_bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id, plan FROM orders WHERE id=?", (order_id,))
    order = c.fetchone()
    if not order:
        conn.close()
        return None
    user_id, plan_key = order
    c.execute("SELECT id, config_text FROM configs WHERE is_used=0 AND plan=? LIMIT 1", (plan_key,))
    cfg = c.fetchone()
    if not cfg:
        conn.close()
        return None
    cfg_id, config_text = cfg
    from config import PLANS
    plan = PLANS[plan_key]
    days = plan["days"]
    volume_gb = plan["volume_gb"]
    start = datetime.now()
    end = start + timedelta(days=days)
    c.execute("INSERT INTO subscriptions (user_id, plan, config, start_date, end_date, volume_gb) VALUES (?,?,?,?,?,?)",
              (user_id, plan_key, config_text, start.isoformat(), end.isoformat(), volume_gb))
    c.execute("UPDATE configs SET is_used=1 WHERE id=?", (cfg_id,))
    c.execute("UPDATE orders SET status='approved' WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    return user_id, config_text, plan_key

def reject_order(order_id):
    conn = sqlite3.connect("vpn_bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    row = c.fetchone()
    c.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    return row[0] if row else None

def get_user_subscription(user_id):
    conn = sqlite3.connect("vpn_bot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions WHERE user_id=? AND is_active=1 ORDER BY id DESC LIMIT 1", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def add_config(config_text, plan):
    conn = sqlite3.connect("vpn_bot.db")
    c = conn.cursor()
    c.execute("INSERT INTO configs (config_text, plan) VALUES (?,?)", (config_text, plan))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect("vpn_bot.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM subscriptions WHERE is_active=1")
    active_subs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders WHERE status='approved'")
    total_sales = c.fetchone()[0]
    c.execute("SELECT SUM(amount) FROM orders WHERE status='approved'")
    total_revenue = c.fetchone()[0] or 0
    conn.close()
    return total_users, active_subs, total_sales, total_revenue
