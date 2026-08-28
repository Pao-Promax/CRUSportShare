import os
import sqlite3
import json

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

SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or "https://ukklvfeuwndspvhtokdg.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVra2x2ZmV1d25kc3B2aHRva2RnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc4ODUzNTcsImV4cCI6MjEwMzQ2MTM1N30.TTsoNfj9B18ORM0xQDWe0D-S7wPWKr_PM6OCAK7Axwg"
USE_SUPABASE = os.environ.get("USE_SUPABASE", "1") == "1"

# Try to use httpx for Supabase REST (more reliable on Vercel than supabase-py)
supabase_enabled = False
if USE_SUPABASE and SUPABASE_URL and SUPABASE_KEY:
    try:
        import httpx
        # Test if httpx can be imported, enable supabase mode
        supabase_enabled = True
    except Exception as e:
        print(f"[DB] httpx not available, fallback to SQLite: {e}")
        supabase_enabled = False

def is_supabase():
    return supabase_enabled

# For backward compatibility, expose supabase_client as None (httpx mode)
supabase_client = None

def get_sqlite_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def get_db():
    if is_supabase():
        return SupabaseRestConnection()
    return get_sqlite_db()

def init_db():
    if is_supabase():
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
            from datetime import date
            today = date.today().isoformat()
            # Fetch all borrow_records that are approved/borrowed and due_date < today
            rows = supabase_select("borrow_records", params={"status": "in.(approved,borrowed)", "select": "id,due_date"})
            # Filter in Python for due_date < today (PostgREST lt filter may need proper date)
            # Alternatively use Supabase filter: due_date=lt.today
            # We already filtered status, now filter due_date
            # Do a second query with lt
            rows2 = supabase_select("borrow_records", params={"status": "in.(approved,borrowed)", "due_date": f"lt.{today}", "select": "id"})
            for r in rows2:
                supabase_update("borrow_records", {"status": "overdue"}, {"id": f"eq.{r['id']}"})
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

# Supabase REST helpers using httpx
def supabase_headers(prefer=None):
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h

def supabase_select(table, params=None, headers=None):
    import httpx
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    h = supabase_headers()
    if headers:
        h.update(headers)
    # params is dict of query params
    try:
        resp = httpx.get(url, headers=h, params=params or {}, timeout=10.0)
        if resp.status_code >= 400:
            print(f"[Supabase] GET {table} failed {resp.status_code}: {resp.text[:500]}")
            return []
        return resp.json() if resp.text else []
    except Exception as e:
        print(f"[Supabase] GET error: {e}")
        return []

def supabase_select_one(table, params):
    rows = supabase_select(table, params)
    return rows[0] if rows else None

def supabase_insert(table, data):
    import httpx
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    h = supabase_headers(prefer="return=representation")
    try:
        resp = httpx.post(url, headers=h, json=data, timeout=10.0)
        if resp.status_code >= 400:
            print(f"[Supabase] INSERT {table} failed {resp.status_code}: {resp.text[:500]}")
            return []
        return resp.json() if resp.text else []
    except Exception as e:
        print(f"[Supabase] INSERT error: {e}")
        return []

def supabase_update(table, data, filters):
    import httpx
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    h = supabase_headers(prefer="return=representation")
    try:
        resp = httpx.patch(url, headers=h, params=filters, json=data, timeout=10.0)
        if resp.status_code >= 400:
            print(f"[Supabase] UPDATE {table} failed {resp.status_code}: {resp.text[:500]}")
            return []
        return resp.json() if resp.text else []
    except Exception as e:
        print(f"[Supabase] UPDATE error: {e}")
        return []

def supabase_delete(table, filters):
    import httpx
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    h = supabase_headers(prefer="return=representation")
    try:
        resp = httpx.delete(url, headers=h, params=filters, timeout=10.0)
        if resp.status_code >= 400:
            print(f"[Supabase] DELETE {table} failed {resp.status_code}: {resp.text[:500]}")
            return []
        return resp.json() if resp.text else []
    except Exception as e:
        print(f"[Supabase] DELETE error: {e}")
        return []

def supabase_count(table, filters=None):
    import httpx
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    h = supabase_headers()
    h["Prefer"] = "count=exact"
    params = filters or {}
    params["select"] = "id"
    try:
        # Use HEAD or GET with count
        resp = httpx.get(url, headers=h, params=params, timeout=10.0)
        # Count is in Content-Range header: 0-9/42
        cr = resp.headers.get("content-range", "")
        if "/" in cr:
            try:
                return int(cr.split("/")[-1])
            except:
                pass
        # Fallback to len
        data = resp.json() if resp.text else []
        return len(data)
    except Exception as e:
        print(f"[Supabase] COUNT error: {e}")
        return 0

# Wrapper to mimic sqlite3
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
        self._rows = [SupabaseRow(r) for r in self._data]
        self.rowcount = rowcount
        self.lastrowid = self._rows[0].get("id") if self._rows and "id" in self._rows[0] else None

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)

class SupabaseRestConnection:
    def execute(self, sql, params=()):
        sql_norm = " ".join(sql.strip().split()).lower()
        params = params or ()
        try:
            # SELECT * FROM users WHERE student_id=?
            if "from users where student_id=?" in sql_norm:
                sid = params[0]
                rows = supabase_select("users", {"student_id": f"eq.{sid}", "select": "*"})
                return SupabaseCursor(rows)

            if "from users where id=?" in sql_norm:
                uid = params[0]
                rows = supabase_select("users", {"id": f"eq.{uid}", "select": "*"})
                return SupabaseCursor(rows)

            if "from users where email=?" in sql_norm:
                email = params[0]
                rows = supabase_select("users", {"email": f"eq.{email}", "select": "*"})
                return SupabaseCursor(rows)

            if "select id from users where student_id=?" in sql_norm:
                sid = params[0]
                rows = supabase_select("users", {"student_id": f"eq.{sid}", "select": "id"})
                return SupabaseCursor(rows)

            if "from admins where username=?" in sql_norm:
                uname = params[0]
                rows = supabase_select("admins", {"username": f"eq.{uname}", "select": "*"})
                return SupabaseCursor(rows)

            if "from admins where id=?" in sql_norm:
                aid = params[0]
                rows = supabase_select("admins", {"id": f"eq.{aid}", "select": "*"})
                return SupabaseCursor(rows)

            if sql_norm.startswith("select * from equipment where id=?"):
                eid = params[0]
                rows = supabase_select("equipment", {"id": f"eq.{eid}", "select": "*"})
                return SupabaseCursor(rows)

            if sql_norm.startswith("select * from equipment"):
                # search handling
                if params:
                    search = params[0].replace("%", "")
                    # Use or filter
                    rows = supabase_select("equipment", {"or": f"(name.ilike.*{search}*,description.ilike.*{search}*)", "select": "*", "order": "id"})
                    # Supabase or syntax may need proper encoding, fallback to python filter if fails
                    if not rows:
                        # fallback: fetch all and filter
                        all_rows = supabase_select("equipment", {"select": "*", "order": "id"})
                        rows = [r for r in all_rows if search.lower() in r["name"].lower() or search.lower() in (r["description"] or "").lower()]
                    return SupabaseCursor(rows)
                rows = supabase_select("equipment", {"select": "*", "order": "id"})
                return SupabaseCursor(rows)

            if "coalesce(sum(total_quantity),0)" in sql_norm:
                rows = supabase_select("equipment", {"select": "total_quantity"})
                total = sum(r["total_quantity"] for r in rows) if rows else 0
                return SupabaseCursor([{"s": total}])

            if "coalesce(sum(available_quantity),0)" in sql_norm:
                rows = supabase_select("equipment", {"select": "available_quantity"})
                total = sum(r["available_quantity"] for r in rows) if rows else 0
                return SupabaseCursor([{"s": total}])

            if sql_norm.startswith("select count(*) as c from borrow_records"):
                # Build filters
                filters = {}
                # user_id=?
                if "user_id=?" in sql_norm and params:
                    filters["user_id"] = f"eq.{params[0]}"
                    if "status='pending'" in sql_norm:
                        filters["status"] = "eq.pending"
                    elif "status in ('approved','borrowed')" in sql_norm:
                        filters["status"] = "in.(approved,borrowed)"
                    elif "status='overdue'" in sql_norm:
                        filters["status"] = "eq.overdue"
                    elif "status='returned'" in sql_norm:
                        filters["status"] = "eq.returned"
                    elif "status in ('approved','borrowed','overdue')" in sql_norm:
                        filters["status"] = "in.(approved,borrowed,overdue)"
                    elif "status=?" in sql_norm and len(params) > 1:
                        filters["status"] = f"eq.{params[1]}"
                elif "status='overdue'" in sql_norm and "user_id" not in sql_norm:
                    filters["status"] = "eq.overdue"
                elif "status='pending'" in sql_norm and "user_id" not in sql_norm:
                    filters["status"] = "eq.pending"
                elif "equipment_id=?" in sql_norm:
                    filters["equipment_id"] = f"eq.{params[0]}"
                    if "status in ('pending','approved','borrowed','overdue')" in sql_norm:
                        filters["status"] = "in.(pending,approved,borrowed,overdue)"
                if "status=?" in sql_norm and "user_id" not in sql_norm and "equipment_id" not in sql_norm and params:
                    filters["status"] = f"eq.{params[0]}"
                # If no filters, count all
                cnt = supabase_count("borrow_records", filters if filters else None)
                return SupabaseCursor([{"c": cnt}])

            if "from borrow_records br" in sql_norm and "join equipment e" in sql_norm and "join users u" in sql_norm:
                # Admin borrow_records
                # Fetch all borrow_records
                br_rows = supabase_select("borrow_records", {"select": "*", "order": "created_at.desc"})
                # Apply status/search filters in Python
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
                    br_rows = [r for r in br_rows if r["status"] == status_filter]
                # Enrich
                enriched = []
                for br in br_rows:
                    u_rows = supabase_select("users", {"id": f"eq.{br['user_id']}", "select": "name,student_id,class_name"})
                    e_rows = supabase_select("equipment", {"id": f"eq.{br['equipment_id']}", "select": "name,image"})
                    u = u_rows[0] if u_rows else {"name": "Unknown", "student_id": "?", "class_name": ""}
                    e = e_rows[0] if e_rows else {"name": "Unknown", "image": ""}
                    row = dict(br)
                    row["user_name"] = u["name"]
                    row["student_id"] = u["student_id"]
                    row["class_name"] = u.get("class_name")
                    row["eq_name"] = e["name"]
                    row["eq_image"] = e["image"]
                    enriched.append(row)
                if search:
                    sl = search.lower()
                    enriched = [r for r in enriched if sl in r["user_name"].lower() or sl in r["student_id"].lower() or sl in r["eq_name"].lower() or sl in str(r["id"])]
                return SupabaseCursor(enriched)

            if "from borrow_records br" in sql_norm and "join equipment e" in sql_norm and "join users u" not in sql_norm:
                # User history
                br_params = {}
                if "br.user_id=?" in sql_norm and "br.equipment_id=?" in sql_norm:
                    br_params["equipment_id"] = f"eq.{params[0]}"
                    br_params["user_id"] = f"eq.{params[1]}"
                elif "br.user_id=?" in sql_norm:
                    br_params["user_id"] = f"eq.{params[0]}"
                elif "br.equipment_id=?" in sql_norm:
                    br_params["equipment_id"] = f"eq.{params[0]}"
                br_params["select"] = "*"
                br_params["order"] = "created_at.desc"
                if "limit 5" in sql_norm:
                    # Use limit via header? For REST, use limit param
                    br_params["limit"] = "5"
                if "limit 8" in sql_norm:
                    br_params["limit"] = "8"
                br_rows = supabase_select("borrow_records", br_params)
                enriched = []
                for br in br_rows:
                    e_rows = supabase_select("equipment", {"id": f"eq.{br['equipment_id']}", "select": "name,image"})
                    e = e_rows[0] if e_rows else {"name": "Unknown", "image": ""}
                    row = dict(br)
                    row["eq_name"] = e["name"]
                    row["eq_image"] = e["image"]
                    enriched.append(row)
                return SupabaseCursor(enriched)

            if "select e.name, e.total_quantity" in sql_norm:
                rows = supabase_select("equipment", {"select": "*"})
                out = []
                for r in rows:
                    out.append({
                        "name": r["name"],
                        "total_quantity": r["total_quantity"],
                        "available_quantity": r["available_quantity"],
                        "borrowed": r["total_quantity"] - r["available_quantity"]
                    })
                out = sorted(out, key=lambda x: x["borrowed"], reverse=True)
                return SupabaseCursor(out)

            if "strftime" in sql_norm:
                rows = supabase_select("borrow_records", {"select": "created_at"})
                from collections import Counter
                from datetime import datetime
                months = []
                for r in rows:
                    ca = r["created_at"]
                    try:
                        dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
                        months.append(dt.strftime("%Y-%m"))
                    except:
                        continue
                cnt = Counter(months)
                sorted_months = sorted(cnt.items(), key=lambda x: x[0], reverse=True)[:6]
                sorted_months = list(reversed(sorted_months))
                out = [{"month": m, "cnt": c} for m, c in sorted_months]
                return SupabaseCursor(out)

            if "select br.*, u.name as user_name" in sql_norm and "limit 8" in sql_norm:
                br_rows = supabase_select("borrow_records", {"select": "*", "order": "created_at.desc", "limit": "8"})
                enriched = []
                for br in br_rows:
                    u_rows = supabase_select("users", {"id": f"eq.{br['user_id']}", "select": "name,student_id"})
                    e_rows = supabase_select("equipment", {"id": f"eq.{br['equipment_id']}", "select": "name"})
                    u = u_rows[0] if u_rows else {"name": "?", "student_id": "?"}
                    e = e_rows[0] if e_rows else {"name": "?"}
                    row = dict(br)
                    row["user_name"] = u["name"]
                    row["student_id"] = u["student_id"]
                    row["eq_name"] = e["name"]
                    enriched.append(row)
                return SupabaseCursor(enriched)

            if "select br.*, u.name as user_name" in sql_norm and "from borrow_records br" in sql_norm:
                br_rows = supabase_select("borrow_records", {"select": "*", "order": "created_at.desc"})
                # Handle search/status
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
                    br_rows = [r for r in br_rows if r["status"] == status_filter]
                enriched = []
                for br in br_rows:
                    u_rows = supabase_select("users", {"id": f"eq.{br['user_id']}", "select": "name,student_id"})
                    e_rows = supabase_select("equipment", {"id": f"eq.{br['equipment_id']}", "select": "name"})
                    u = u_rows[0] if u_rows else {"name": "?", "student_id": "?"}
                    e = e_rows[0] if e_rows else {"name": "?"}
                    row = dict(br)
                    row["user_name"] = u["name"]
                    row["student_id"] = u["student_id"]
                    row["eq_name"] = e["name"]
                    enriched.append(row)
                if search:
                    sl = search.lower()
                    enriched = [r for r in enriched if sl in r["user_name"].lower() or sl in r["student_id"].lower() or sl in r["eq_name"].lower()]
                return SupabaseCursor(enriched)

            if sql_norm.startswith("insert into users"):
                sid, name, email, pw_hash, class_name = params
                data = {"student_id": sid, "name": name, "email": email, "password_hash": pw_hash, "class_name": class_name}
                # Remove None email to avoid unique violation with null?
                if email is None:
                    data["email"] = None
                rows = supabase_insert("users", data)
                cur = SupabaseCursor(rows)
                return cur

            if sql_norm.startswith("insert into admins"):
                username, pw_hash, name = params
                rows = supabase_insert("admins", {"username": username, "password_hash": pw_hash, "name": name})
                return SupabaseCursor(rows)

            if sql_norm.startswith("insert into equipment"):
                name, desc, image, total, avail = params
                rows = supabase_insert("equipment", {"name": name, "description": desc, "image": image, "total_quantity": total, "available_quantity": avail})
                return SupabaseCursor(rows)

            if "insert into borrow_records" in sql_norm and "due_date, status" in sql_norm and "'pending'" in sql_norm:
                uid, eid, qty, due = params
                rows = supabase_insert("borrow_records", {"user_id": uid, "equipment_id": eid, "quantity": qty, "due_date": due, "status": "pending"})
                return SupabaseCursor(rows)

            if sql_norm.startswith("insert into borrow_records"):
                import re
                m = re.search(r"insert into borrow_records \((.*?)\)", sql_norm)
                if m:
                    cols = [c.strip() for c in m.group(1).split(",")]
                    data = {}
                    for i, col in enumerate(cols):
                        if i < len(params):
                            data[col] = params[i]
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
                    if "borrow_date" not in data and "borrow_date" in sql_norm:
                        from datetime import date
                        data["borrow_date"] = date.today().isoformat()
                    if "due_date" not in data and "due_date" in sql_norm:
                        from datetime import date, timedelta
                        if "+7 days" in sql:
                            data["due_date"] = (date.today() + timedelta(days=7)).isoformat()
                        elif "+3 days" in sql:
                            data["due_date"] = (date.today() + timedelta(days=3)).isoformat()
                        elif "-3 days" in sql:
                            data["due_date"] = (date.today() - timedelta(days=3)).isoformat()
                    rows = supabase_insert("borrow_records", data)
                    return SupabaseCursor(rows)
                return SupabaseCursor([])

            if "update equipment set available_quantity=?" in sql_norm:
                avail, eid = params
                supabase_update("equipment", {"available_quantity": avail}, {"id": f"eq.{eid}"})
                return SupabaseCursor([], rowcount=1)

            if "update equipment set name=?" in sql_norm:
                name, desc, image, total, avail, eid = params
                supabase_update("equipment", {"name": name, "description": desc, "image": image, "total_quantity": total, "available_quantity": avail}, {"id": f"eq.{eid}"})
                return SupabaseCursor([], rowcount=1)

            if "update users set name=?" in sql_norm and "password_hash=?" in sql_norm:
                name, email, class_name, pw_hash, uid = params
                supabase_update("users", {"name": name, "email": email, "class_name": class_name, "password_hash": pw_hash}, {"id": f"eq.{uid}"})
                return SupabaseCursor([], rowcount=1)

            if "update users set name=?" in sql_norm and "class_name=?" in sql_norm and "password_hash" not in sql_norm:
                name, email, class_name, uid = params
                supabase_update("users", {"name": name, "email": email, "class_name": class_name}, {"id": f"eq.{uid}"})
                return SupabaseCursor([], rowcount=1)

            if "update borrow_records set status='approved'" in sql_norm:
                approved_by, bid = params
                from datetime import date
                supabase_update("borrow_records", {"status": "approved", "borrow_date": date.today().isoformat(), "approved_by": approved_by}, {"id": f"eq.{bid}"})
                return SupabaseCursor([], rowcount=1)

            if "update borrow_records set status='rejected'" in sql_norm:
                approved_by, bid = params
                supabase_update("borrow_records", {"status": "rejected", "approved_by": approved_by}, {"id": f"eq.{bid}"})
                return SupabaseCursor([], rowcount=1)

            if "update borrow_records set status='returned'" in sql_norm:
                bid = params[0]
                from datetime import date
                supabase_update("borrow_records", {"status": "returned", "return_date": date.today().isoformat()}, {"id": f"eq.{bid}"})
                return SupabaseCursor([], rowcount=1)

            if "update borrow_records set status='overdue'" in sql_norm:
                from datetime import date
                today = date.today().isoformat()
                rows = supabase_select("borrow_records", {"status": "in.(approved,borrowed)", "select": "id,due_date"})
                for r in rows:
                    if r["due_date"] and r["due_date"] < today:
                        supabase_update("borrow_records", {"status": "overdue"}, {"id": f"eq.{r['id']}"})
                return SupabaseCursor([], rowcount=1)

            if "delete from equipment where id=?" in sql_norm:
                eid = params[0]
                supabase_delete("equipment", {"id": f"eq.{eid}"})
                return SupabaseCursor([], rowcount=1)

            if "delete from borrow_records" in sql_norm and "where" not in sql_norm:
                # Delete all - need to handle via supabase: delete where id not null
                # Use gt 0
                supabase_delete("borrow_records", {"id": "gt.0"})
                return SupabaseCursor([], rowcount=1)
            if "delete from equipment" in sql_norm and "where" not in sql_norm:
                supabase_delete("equipment", {"id": "gt.0"})
                return SupabaseCursor([], rowcount=1)
            if "delete from users" in sql_norm and "where" not in sql_norm:
                supabase_delete("users", {"id": "gt.0"})
                return SupabaseCursor([], rowcount=1)
            if "delete from admins" in sql_norm and "where" not in sql_norm:
                supabase_delete("admins", {"id": "gt.0"})
                return SupabaseCursor([], rowcount=1)

            if "select count(*) as c from equipment" in sql_norm:
                cnt = supabase_count("equipment")
                return SupabaseCursor([{"c": cnt}])
            if "select count(*) as c from users" in sql_norm:
                cnt = supabase_count("users")
                return SupabaseCursor([{"c": cnt}])

            if "from borrow_records where id=? and user_id=?" in sql_norm:
                bid, uid = params
                rows = supabase_select("borrow_records", {"id": f"eq.{bid}", "user_id": f"eq.{uid}", "select": "*"})
                return SupabaseCursor(rows)

            if sql_norm.startswith("select * from borrow_records where id=?"):
                bid = params[0]
                rows = supabase_select("borrow_records", {"id": f"eq.{bid}", "select": "*"})
                return SupabaseCursor(rows)

            if "sqlite_master" in sql_norm:
                return SupabaseCursor([])

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
        pass

# For backward compat, keep old names
SupabaseConnection = SupabaseRestConnection
