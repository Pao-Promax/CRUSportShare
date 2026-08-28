import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "cru_sports.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            sql = f.read()
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()

def ensure_db():
    if not os.path.exists(DB_PATH):
        init_db()
        # auto seed if fresh
        try:
            from seed import seed_data
            seed_data()
        except Exception as e:
            print(f"[DB] seed skipped: {e}")
    else:
        # ensure tables exist even if file exists but empty
        conn = get_db()
        try:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if cur.fetchone() is None:
                conn.close()
                init_db()
                from seed import seed_data
                seed_data()
                return
        finally:
            try:
                conn.close()
            except:
                pass
        # auto-check overdue on startup
        try:
            check_overdue()
        except:
            pass

def check_overdue():
    conn = get_db()
    try:
        conn.execute("""
            UPDATE borrow_records
            SET status='overdue'
            WHERE status IN ('approved','borrowed')
              AND due_date < date('now','localtime')
        """)
        conn.commit()
    finally:
        conn.close()
