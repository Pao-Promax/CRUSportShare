import os
import sqlite3

# Load .env if exists (for local Supabase config)
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.environ.get("VERCEL"):
    DB_PATH = "/tmp/cru_sports.db"
else:
    DB_PATH = os.path.join(BASE_DIR, "database", "cru_sports.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

# Supabase config
SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or "https://ukklvfeuwndspvhtokdg.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVra2x2ZmV1d25kc3B2aHRva2RnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc4ODUzNTcsImV4cCI6MjEwMzQ2MTM1N30.TTsoNfj9B18ORM0xQDWe0D-S7wPWKr_PM6OCAK7Axwg"

USE_SUPABASE = bool(os.environ.get("USE_SUPABASE", "1") == "1")  # default to Supabase when available

supabase_client = None
if USE_SUPABASE and SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Test connection
        # print(f"[DB] Supabase enabled: {SUPABASE_URL}")
    except Exception as e:
        print(f"[DB] Supabase init failed, fallback to SQLite: {e}")
        supabase_client = None

def is_supabase():
    return supabase_client is not None

# SQLite helpers (fallback)
def get_sqlite_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def get_db():
    if is_supabase():
        return SupabaseConnection()
    return get_sqlite_db()

def init_db():
    if is_supabase():
        # Supabase tables already created via migration
        return
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_sqlite_db()
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            sql = f.read()
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()

def ensure_db():
    if is_supabase():
        try:
            check_overdue()
        except Exception as e:
            print(f"[DB] check_overdue supabase skipped: {e}")
        return
    if not os.path.exists(DB_PATH):
        init_db()
        try:
            from seed import seed_data
            seed_data()
        except Exception as e:
            print(f"[DB] seed skipped: {e}")
    else:
        conn = get_sqlite_db()
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
        try:
            check_overdue()
        except:
            pass

def check_overdue():
    if is_supabase():
        try:
            # Update overdue where due_date < today and status in approved/borrowed
            from datetime import date
            today = date.today().isoformat()
            # Use supabase to update
            # Fetch records that should be overdue
            res = supabase_client.table("borrow_records").select("id").in_("status", ["approved","borrowed"]).lt("due_date", today).execute()
            if res.data:
                ids = [r["id"] for r in res.data]
                # Update each to overdue (bulk)
                for bid in ids:
                    supabase_client.table("borrow_records").update({"status": "overdue"}).eq("id", bid).execute()
        except Exception as e:
            print(f"[DB] supabase check_overdue error: {e}")
        return
    conn = get_sqlite_db()
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

# Supabase wrapper to mimic sqlite3 Connection/Cursor for app.py
class SupabaseRow(dict):
    def __getitem__(self, key):
        return super().__getitem__(key)
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

class SupabaseCursor:
    def __init__(self, data=None, rowcount=0):
        self._data = data or []
        # Convert dicts to SupabaseRow with attribute access like sqlite3.Row
        self._rows = [SupabaseRow(r) for r in self._data]
        self.rowcount = rowcount
        self.lastrowid = None

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)

class SupabaseConnection:
    def __init__(self):
        self.client = supabase_client

    def execute(self, sql, params=()):
        # Normalize sql for pattern matching
        sql_norm = " ".join(sql.strip().split()).lower()
        params = params or ()
        # Need to handle many patterns used in app.py
        # We use if/elif chain
        try:
            # SELECT * FROM users WHERE student_id=?
            if "from users where student_id=?" in sql_norm:
                sid = params[0]
                res = self.client.table("users").select("*").eq("student_id", sid).execute()
                return SupabaseCursor(res.data)

            # SELECT * FROM users WHERE id=?
            if "from users where id=?" in sql_norm:
                uid = params[0]
                res = self.client.table("users").select("*").eq("id", uid).execute()
                return SupabaseCursor(res.data)

            # SELECT * FROM users WHERE email=?
            if "from users where email=?" in sql_norm:
                email = params[0]
                res = self.client.table("users").select("*").eq("email", email).execute()
                return SupabaseCursor(res.data)

            # SELECT id FROM users WHERE student_id=?
            if "select id from users where student_id=?" in sql_norm:
                sid = params[0]
                res = self.client.table("users").select("id").eq("student_id", sid).execute()
                return SupabaseCursor(res.data)

            # SELECT * FROM admins WHERE username=?
            if "from admins where username=?" in sql_norm:
                uname = params[0]
                res = self.client.table("admins").select("*").eq("username", uname).execute()
                return SupabaseCursor(res.data)

            # SELECT * FROM admins WHERE id=?
            if "from admins where id=?" in sql_norm:
                aid = params[0]
                res = self.client.table("admins").select("*").eq("id", aid).execute()
                return SupabaseCursor(res.data)

            # SELECT * FROM equipment WHERE id=?
            if sql_norm.startswith("select * from equipment where id=?"):
                eid = params[0]
                res = self.client.table("equipment").select("*").eq("id", eid).execute()
                return SupabaseCursor(res.data)

            # SELECT * FROM equipment (with optional search)
            if sql_norm.startswith("select * from equipment"):
                # Handle search: query = "SELECT * FROM equipment" plus optional WHERE
                # params may contain search patterns like %xxx%
                q = self.client.table("equipment").select("*")
                # If params has search, we need to filter
                # In app.py, search uses (name LIKE ? OR description LIKE ?) with %search%
                if params:
                    # params will be ["%search%", "%search%"] for one condition
                    # Extract search term without %
                    search = params[0].replace("%", "")
                    # Supabase ilike
                    # We need OR: name ilike %search% OR description ilike %search%
                    # PostgREST or syntax: or=(name.ilike.%search%,description.ilike.%search%)
                    # Supabase-py supports .or_
                    try:
                        q = q.or_(f"name.ilike.%{search}%,description.ilike.%{search}%")
                    except:
                        # fallback: filter via Python after fetch
                        res = q.execute()
                        filtered = [r for r in res.data if search.lower() in r["name"].lower() or search.lower() in (r["description"] or "").lower()]
                        # Apply ordering if needed
                        filtered = sorted(filtered, key=lambda x: x["id"])
                        return SupabaseCursor(filtered)
                # Order by id ASC is default in app.py after query building
                res = q.order("id").execute()
                return SupabaseCursor(res.data)

            # SELECT COALESCE(SUM(total_quantity),0) as s FROM equipment
            if "coalesce(sum(total_quantity),0)" in sql_norm:
                res = self.client.table("equipment").select("total_quantity").execute()
                total = sum(r["total_quantity"] for r in res.data) if res.data else 0
                return SupabaseCursor([{"s": total}])

            # SELECT COALESCE(SUM(available_quantity),0) as s FROM equipment
            if "coalesce(sum(available_quantity),0)" in sql_norm:
                res = self.client.table("equipment").select("available_quantity").execute()
                total = sum(r["available_quantity"] for r in res.data) if res.data else 0
                return SupabaseCursor([{"s": total}])

            # SELECT COUNT(*) as c FROM borrow_records WHERE ...
            if sql_norm.startswith("select count(*) as c from borrow_records"):
                # Need to parse conditions
                # Common patterns:
                # WHERE user_id=? AND status='pending'
                # WHERE user_id=? AND status IN ('approved','borrowed')
                # WHERE status='overdue'
                # etc.
                q = self.client.table("borrow_records").select("*", count="exact")
                # Handle params and status literals in sql
                # For params, they are user_id etc.
                # Extract user_id if in params
                # Simple: if params has one value and sql contains user_id=?
                if "user_id=?" in sql_norm and params:
                    # Find position of user_id param: first param is user_id if sql contains user_id=?
                    # In our queries, user_id is always first param when present
                    q = q.eq("user_id", params[0])
                    # Check status conditions in sql
                    if "status='pending'" in sql_norm:
                        q = q.eq("status", "pending")
                    elif "status in ('approved','borrowed')" in sql_norm:
                        q = q.in_("status", ["approved","borrowed"])
                    elif "status='overdue'" in sql_norm:
                        q = q.eq("status", "overdue")
                    elif "status='returned'" in sql_norm:
                        q = q.eq("status", "returned")
                    elif "status in ('approved','borrowed','overdue')" in sql_norm:
                        q = q.in_("status", ["approved","borrowed","overdue"])
                    elif "status in ('pending','approved','borrowed','overdue')" in sql_norm:
                        q = q.in_("status", ["pending","approved","borrowed","overdue"])
                    elif "status=?" in sql_norm and len(params) > 1:
                        # status filter with placeholder
                        # e.g., WHERE ... AND status=?
                        # params[1] is status
                        q = q.eq("status", params[1])
                elif "status='overdue'" in sql_norm and "user_id" not in sql_norm:
                    q = q.eq("status", "overdue")
                elif "status='pending'" in sql_norm and "user_id" not in sql_norm:
                    q = q.eq("status", "pending")
                elif "status in" not in sql_norm and "user_id" not in sql_norm:
                    # SELECT COUNT(*) FROM borrow_records (no where)
                    pass
                elif "equipment_id=?" in sql_norm:
                    # For delete check: equipment_id=? AND status IN ...
                    eid = params[0]
                    q = q.eq("equipment_id", eid)
                    if "status in ('pending','approved','borrowed','overdue')" in sql_norm:
                        q = q.in_("status", ["pending","approved","borrowed","overdue"])
                # Handle status=? with param
                if "status=?" in sql_norm and "user_id" not in sql_norm and "equipment_id" not in sql_norm and params:
                    q = q.eq("status", params[0])
                res = q.execute()
                cnt = res.count if res.count is not None else len(res.data)
                return SupabaseCursor([{"c": cnt}])

            # SELECT br.*, e.name as eq_name, e.image as eq_image FROM borrow_records ... JOIN ...
            # For history and admin borrow_records with joins
            if "from borrow_records br" in sql_norm and "join equipment e" in sql_norm and "join users u" in sql_norm:
                # Admin borrow_records with all joins
                # Need to handle search and status filter
                # Use supabase select with embedded
                # For simplicity, fetch borrow_records then enrich with users and equipment via separate queries
                # Determine filters
                # Query is: SELECT br.*, u.name as user_name, u.student_id, u.class_name, e.name as eq_name, e.image as eq_image
                # FROM borrow_records br JOIN users u ON u.id=br.user_id JOIN equipment e ON e.id=br.equipment_id
                # WHERE ... ORDER BY br.created_at DESC
                # Params may contain search and status
                # We'll fetch all then filter in Python for simplicity if needed, but better to use supabase filters
                # Fetch borrow_records with join via select
                # Supabase can do: select("*, users(name, student_id, class_name), equipment(name, image)")
                # But need foreign key relationship names: by default, PostgREST uses foreign key to infer
                # We have FKs, so we can do:
                # select("*, users!inner(name, student_id, class_name), equipment!inner(name, image)")
                # However, to keep simple, we will fetch borrow_records and then enrich
                # For now, fetch all borrow_records
                br_res = self.client.table("borrow_records").select("*").order("created_at", desc=True).execute()
                br_data = br_res.data or []
                # If search or status filter in sql, apply Python filtering
                # Extract status_filter if present in params
                status_filter = None
                search = None
                if params:
                    # For admin_borrow_records: params may be [search, search, search, search, status] or [status] etc.
                    # Detect: if sql contains status=? and search, last param is status, earlier are search
                    if "status=?" in sql_norm:
                        status_filter = params[-1]
                        if len(params) > 1:
                            # first params are search patterns
                            search = params[0].replace("%", "")
                    elif any("%" in str(p) for p in params):
                        search = str(params[0]).replace("%", "")
                # Filter by status if needed
                if status_filter:
                    br_data = [r for r in br_data if r["status"] == status_filter]
                # For search, need to enrich first then filter, but we can filter after enriching
                # Enrich each record with user and equipment
                enriched = []
                for br in br_data:
                    # fetch user and equipment
                    u_res = self.client.table("users").select("name, student_id, class_name").eq("id", br["user_id"]).execute()
                    e_res = self.client.table("equipment").select("name, image").eq("id", br["equipment_id"]).execute()
                    u = u_res.data[0] if u_res.data else {"name": "Unknown", "student_id": "?", "class_name": ""}
                    e = e_res.data[0] if e_res.data else {"name": "Unknown", "image": ""}
                    row = dict(br)
                    row["user_name"] = u["name"]
                    row["student_id"] = u["student_id"]
                    row["class_name"] = u.get("class_name")
                    row["eq_name"] = e["name"]
                    row["eq_image"] = e["image"]
                    enriched.append(row)
                if search:
                    search_lower = search.lower()
                    enriched = [r for r in enriched if search_lower in r["user_name"].lower() or search_lower in r["student_id"].lower() or search_lower in r["eq_name"].lower() or search_lower in str(r["id"])]
                return SupabaseCursor(enriched)

            if "from borrow_records br" in sql_norm and "join equipment e" in sql_norm and "join users u" not in sql_norm:
                # For user history: SELECT br.*, e.name as eq_name, e.image as eq_image FROM borrow_records br JOIN equipment e ON e.id=br.equipment_id WHERE br.user_id=? ORDER BY ...
                # Or for equipment detail history: WHERE br.equipment_id=? AND br.user_id=?
                # Handle both
                # Determine params: could be user_id alone, or equipment_id and user_id
                br_q = self.client.table("borrow_records").select("*")
                if "br.user_id=?" in sql_norm and "br.equipment_id=?" in sql_norm:
                    # equipment detail history: equipment_id, user_id
                    eid = params[0]
                    uid = params[1]
                    br_q = br_q.eq("equipment_id", eid).eq("user_id", uid)
                elif "br.user_id=?" in sql_norm:
                    uid = params[0]
                    br_q = br_q.eq("user_id", uid)
                elif "br.equipment_id=?" in sql_norm:
                    eid = params[0]
                    br_q = br_q.eq("equipment_id", eid)
                br_q = br_q.order("created_at", desc=True)
                if "limit 5" in sql_norm:
                    br_q = br_q.limit(5)
                if "limit 8" in sql_norm:
                    br_q = br_q.limit(8)
                res = br_q.execute()
                enriched = []
                for br in (res.data or []):
                    # Handle LIMIT in Python if needed (supabase limit already handles)
                    e_res = self.client.table("equipment").select("name, image").eq("id", br["equipment_id"]).execute()
                    e = e_res.data[0] if e_res.data else {"name": "Unknown", "image": ""}
                    # Also need user info if query includes users? This branch is without users, but we still handle
                    # For history, need eq_name and eq_image
                    row = dict(br)
                    row["eq_name"] = e["name"]
                    row["eq_image"] = e["image"]
                    # For detail history, also need e.name as eq_name (already)
                    # If the original query also selects u.name etc., but this branch not, so skip
                    enriched.append(row)
                return SupabaseCursor(enriched)

            # SELECT e.name, e.total_quantity ... FROM equipment e ORDER BY borrowed DESC
            if "select e.name, e.total_quantity" in sql_norm:
                res = self.client.table("equipment").select("*").execute()
                rows = []
                for r in res.data:
                    rows.append({
                        "name": r["name"],
                        "total_quantity": r["total_quantity"],
                        "available_quantity": r["available_quantity"],
                        "borrowed": r["total_quantity"] - r["available_quantity"]
                    })
                rows = sorted(rows, key=lambda x: x["borrowed"], reverse=True)
                return SupabaseCursor(rows)

            # SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as cnt FROM borrow_records GROUP BY month ORDER BY month DESC LIMIT 6
            if "strftime('%y-%m'" in sql_norm or "strftime('%Y-%m'" in sql_norm:
                res = self.client.table("borrow_records").select("created_at").execute()
                from collections import Counter
                from datetime import datetime
                months = []
                for r in res.data:
                    ca = r["created_at"]
                    # Parse timestamptz
                    try:
                        # Supabase returns ISO format
                        dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
                        month = dt.strftime("%Y-%m")
                        months.append(month)
                    except:
                        continue
                cnt = Counter(months)
                # Get sorted months desc, limit 6, then reversed
                sorted_months = sorted(cnt.items(), key=lambda x: x[0], reverse=True)[:6]
                sorted_months = list(reversed(sorted_months))
                rows = [{"month": m, "cnt": c} for m, c in sorted_months]
                return SupabaseCursor(rows)

            # SELECT br.*, u.name as user_name, u.student_id, e.name as eq_name FROM borrow_records ... (for admin dashboard recent)
            if "select br.*, u.name as user_name" in sql_norm and "limit 8" in sql_norm:
                # Recent 8
                res = self.client.table("borrow_records").select("*").order("created_at", desc=True).limit(8).execute()
                enriched = []
                for br in (res.data or []):
                    u_res = self.client.table("users").select("name, student_id").eq("id", br["user_id"]).execute()
                    e_res = self.client.table("equipment").select("name").eq("id", br["equipment_id"]).execute()
                    u = u_res.data[0] if u_res.data else {"name": "?", "student_id": "?"}
                    e = e_res.data[0] if e_res.data else {"name": "?"}
                    row = dict(br)
                    row["user_name"] = u["name"]
                    row["student_id"] = u["student_id"]
                    row["eq_name"] = e["name"]
                    enriched.append(row)
                return SupabaseCursor(enriched)

            # SELECT br.*, u.name as user_name, u.student_id, e.name as eq_name FROM borrow_records ... (admin history without limit)
            if "select br.*, u.name as user_name" in sql_norm and "from borrow_records br" in sql_norm:
                # Generic admin history
                # Check for search/status filters similar to earlier
                # For simplicity, fetch all and filter
                br_res = self.client.table("borrow_records").select("*").order("created_at", desc=True).execute()
                br_data = br_res.data or []
                # Handle search/status if params
                status_filter = None
                search = None
                if params:
                    if "status=?" in sql_norm:
                        status_filter = params[-1]
                        if len(params) > 1:
                            search = str(params[0]).replace("%", "")
                    elif any("%" in str(p) for p in params):
                        search = str(params[0]).replace("%", "")
                if status_filter:
                    br_data = [r for r in br_data if r["status"] == status_filter]
                enriched = []
                for br in br_data:
                    u_res = self.client.table("users").select("name, student_id").eq("id", br["user_id"]).execute()
                    e_res = self.client.table("equipment").select("name").eq("id", br["equipment_id"]).execute()
                    u = u_res.data[0] if u_res.data else {"name": "?", "student_id": "?"}
                    e = e_res.data[0] if e_res.data else {"name": "?"}
                    row = dict(br)
                    row["user_name"] = u["name"]
                    row["student_id"] = u["student_id"]
                    row["eq_name"] = e["name"]
                    enriched.append(row)
                if search:
                    search_lower = search.lower()
                    enriched = [r for r in enriched if search_lower in r["user_name"].lower() or search_lower in r["student_id"].lower() or search_lower in r["eq_name"].lower()]
                return SupabaseCursor(enriched)

            # INSERT INTO users ...
            if sql_norm.startswith("insert into users"):
                sid, name, email, pw_hash, class_name = params
                data = {
                    "student_id": sid,
                    "name": name,
                    "email": email,
                    "password_hash": pw_hash,
                    "class_name": class_name
                }
                res = self.client.table("users").insert(data).execute()
                # Return cursor with lastrowid
                cur = SupabaseCursor(res.data)
                if res.data:
                    cur.lastrowid = res.data[0].get("id")
                return cur

            # INSERT INTO admins ...
            if sql_norm.startswith("insert into admins"):
                username, pw_hash, name = params
                res = self.client.table("admins").insert({"username": username, "password_hash": pw_hash, "name": name}).execute()
                cur = SupabaseCursor(res.data)
                if res.data:
                    cur.lastrowid = res.data[0].get("id")
                return cur

            # INSERT INTO equipment ...
            if sql_norm.startswith("insert into equipment"):
                name, desc, image, total, avail = params
                res = self.client.table("equipment").insert({
                    "name": name,
                    "description": desc,
                    "image": image,
                    "total_quantity": total,
                    "available_quantity": avail
                }).execute()
                cur = SupabaseCursor(res.data)
                if res.data:
                    cur.lastrowid = res.data[0].get("id")
                return cur

            # INSERT INTO borrow_records (user_id, equipment_id, quantity, due_date, status) VALUES (?, ?, ?, ?, 'pending')
            if "insert into borrow_records" in sql_norm and "due_date, status" in sql_norm and "'pending'" in sql_norm:
                # Handle pending insert: (user_id, equipment_id, quantity, due_date)
                # params: user_id, equipment_id, quantity, due_date
                uid, eid, qty, due = params
                res = self.client.table("borrow_records").insert({
                    "user_id": uid,
                    "equipment_id": eid,
                    "quantity": qty,
                    "due_date": due,
                    "status": "pending"
                }).execute()
                cur = SupabaseCursor(res.data)
                if res.data:
                    cur.lastrowid = res.data[0].get("id")
                return cur

            # INSERT INTO borrow_records ... with borrow_date etc. (for seed, not used now)
            if sql_norm.startswith("insert into borrow_records"):
                # Generic insert - try to parse columns
                # For now, handle the 4 cases in seed, but seed no longer uses borrow_records mock
                # This will be for any other insert
                # Extract column list between ( and )
                import re
                m = re.search(r"insert into borrow_records \((.*?)\)", sql_norm)
                if m:
                    cols = [c.strip() for c in m.group(1).split(",")]
                    data = {}
                    for i, col in enumerate(cols):
                        if i < len(params):
                            data[col] = params[i]
                        else:
                            # Handle literals like 'pending' in sql
                            pass
                    # Handle status literal if in sql
                    if "'borrowed'" in sql_norm:
                        data["status"] = "borrowed"
                    elif "'approved'" in sql_norm:
                        data["status"] = "approved"
                    elif "'pending'" in sql_norm:
                        data["status"] = "pending"
                    elif "'overdue'" in sql_norm:
                        data["status"] = "overdue"
                    elif "'returned'" in sql_norm:
                        data["status"] = "returned"
                    # Handle borrow_date etc. with date('now')
                    if "borrow_date" not in data and "borrow_date" in sql_norm:
                        from datetime import date
                        data["borrow_date"] = date.today().isoformat()
                    if "due_date" not in data and "due_date" in sql_norm:
                        # due_date with date('now','+7 days') etc.
                        from datetime import date, timedelta
                        if "+7 days" in sql:
                            data["due_date"] = (date.today() + timedelta(days=7)).isoformat()
                        elif "+3 days" in sql:
                            data["due_date"] = (date.today() + timedelta(days=3)).isoformat()
                        elif "-3 days" in sql:
                            data["due_date"] = (date.today() - timedelta(days=3)).isoformat()
                    res = self.client.table("borrow_records").insert(data).execute()
                    cur = SupabaseCursor(res.data)
                    if res.data:
                        cur.lastrowid = res.data[0].get("id")
                    return cur
                return SupabaseCursor([])

            # UPDATE equipment SET available_quantity=? WHERE id=?
            if "update equipment set available_quantity=?" in sql_norm:
                avail, eid = params
                self.client.table("equipment").update({"available_quantity": avail}).eq("id", eid).execute()
                return SupabaseCursor([], rowcount=1)

            # UPDATE equipment SET name=?, description=?, image=?, total_quantity=?, available_quantity=? WHERE id=?
            if "update equipment set name=?" in sql_norm:
                name, desc, image, total, avail, eid = params
                self.client.table("equipment").update({
                    "name": name,
                    "description": desc,
                    "image": image,
                    "total_quantity": total,
                    "available_quantity": avail
                }).eq("id", eid).execute()
                return SupabaseCursor([], rowcount=1)

            # UPDATE users SET name=?, email=?, class_name=?, password_hash=? WHERE id=?
            if "update users set name=?" in sql_norm and "password_hash=?" in sql_norm:
                name, email, class_name, pw_hash, uid = params
                self.client.table("users").update({
                    "name": name,
                    "email": email,
                    "class_name": class_name,
                    "password_hash": pw_hash
                }).eq("id", uid).execute()
                return SupabaseCursor([], rowcount=1)

            # UPDATE users SET name=?, email=?, class_name=? WHERE id=?
            if "update users set name=?" in sql_norm and "class_name=?" in sql_norm and "password_hash" not in sql_norm:
                name, email, class_name, uid = params
                self.client.table("users").update({
                    "name": name,
                    "email": email,
                    "class_name": class_name
                }).eq("id", uid).execute()
                return SupabaseCursor([], rowcount=1)

            # UPDATE borrow_records SET status='approved', borrow_date=date('now','localtime'), approved_by=? WHERE id=?
            if "update borrow_records set status='approved'" in sql_norm:
                approved_by, bid = params
                from datetime import date
                self.client.table("borrow_records").update({
                    "status": "approved",
                    "borrow_date": date.today().isoformat(),
                    "approved_by": approved_by
                }).eq("id", bid).execute()
                return SupabaseCursor([], rowcount=1)

            # UPDATE borrow_records SET status='rejected', approved_by=? WHERE id=?
            if "update borrow_records set status='rejected'" in sql_norm:
                approved_by, bid = params
                self.client.table("borrow_records").update({
                    "status": "rejected",
                    "approved_by": approved_by
                }).eq("id", bid).execute()
                return SupabaseCursor([], rowcount=1)

            # UPDATE borrow_records SET status='returned', return_date=date('now','localtime') WHERE id=?
            if "update borrow_records set status='returned'" in sql_norm:
                bid = params[0]
                from datetime import date
                self.client.table("borrow_records").update({
                    "status": "returned",
                    "return_date": date.today().isoformat()
                }).eq("id", bid).execute()
                return SupabaseCursor([], rowcount=1)

            # UPDATE borrow_records SET status='overdue' WHERE ...
            if "update borrow_records set status='overdue'" in sql_norm:
                from datetime import date
                today = date.today().isoformat()
                # Find records to update
                res = self.client.table("borrow_records").select("id, due_date, status").in_("status", ["approved","borrowed"]).execute()
                for r in (res.data or []):
                    if r["due_date"] and r["due_date"] < today:
                        self.client.table("borrow_records").update({"status": "overdue"}).eq("id", r["id"]).execute()
                return SupabaseCursor([], rowcount=1)

            # DELETE FROM equipment WHERE id=?
            if "delete from equipment where id=?" in sql_norm:
                eid = params[0]
                self.client.table("equipment").delete().eq("id", eid).execute()
                return SupabaseCursor([], rowcount=1)

            # DELETE FROM borrow_records etc. (for seed clear)
            if "delete from borrow_records" in sql_norm:
                # For seed, delete all
                # Supabase requires filter, so delete where id >0
                self.client.table("borrow_records").delete().gt("id", 0).execute()
                return SupabaseCursor([], rowcount=1)
            if "delete from equipment" in sql_norm and "where" not in sql_norm:
                self.client.table("equipment").delete().gt("id", 0).execute()
                return SupabaseCursor([], rowcount=1)
            if "delete from users" in sql_norm and "where" not in sql_norm:
                self.client.table("users").delete().gt("id", 0).execute()
                return SupabaseCursor([], rowcount=1)
            if "delete from admins" in sql_norm and "where" not in sql_norm:
                self.client.table("admins").delete().gt("id", 0).execute()
                return SupabaseCursor([], rowcount=1)
            if "delete from users where student_id not in" in sql_norm:
                # For clean, not needed in supabase mode
                return SupabaseCursor([], rowcount=0)
            if "delete from admins where username not in" in sql_norm:
                return SupabaseCursor([], rowcount=0)

            # SELECT COUNT(*) as c FROM users etc. (for seed check)
            if "select count(*) as c from equipment" in sql_norm:
                res = self.client.table("equipment").select("*", count="exact").execute()
                cnt = res.count if res.count is not None else len(res.data)
                return SupabaseCursor([{"c": cnt}])
            if "select count(*) as c from users" in sql_norm:
                res = self.client.table("users").select("*", count="exact").execute()
                cnt = res.count if res.count is not None else len(res.data)
                return SupabaseCursor([{"c": cnt}])

            # SELECT * FROM borrow_records WHERE id=? AND user_id=?
            if "from borrow_records where id=? and user_id=?" in sql_norm:
                bid, uid = params
                res = self.client.table("borrow_records").select("*").eq("id", bid).eq("user_id", uid).execute()
                return SupabaseCursor(res.data)

            # SELECT * FROM borrow_records WHERE id=?
            if sql_norm.startswith("select * from borrow_records where id=?"):
                bid = params[0]
                res = self.client.table("borrow_records").select("*").eq("id", bid).execute()
                return SupabaseCursor(res.data)

            # SELECT * FROM equipment WHERE id=? (already handled)
            # SELECT name FROM sqlite_master ... (for ensure_db, return empty to skip)
            if "sqlite_master" in sql_norm:
                return SupabaseCursor([])

            # Fallback: log unhandled query
            print(f"[Supabase] Unhandled SQL: {sql} params={params}")
            return SupabaseCursor([])

        except Exception as e:
            print(f"[Supabase] execute error: {e} for sql: {sql} params={params}")
            import traceback
            traceback.print_exc()
            return SupabaseCursor([])

    def commit(self):
        pass

    def close(self):
        pass

    def executescript(self, sql):
        # For init_db, ignore
        pass
