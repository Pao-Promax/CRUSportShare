import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, g, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db, ensure_db, check_overdue, is_supabase, supabase_client

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "cru-sports-borrow-secret-key-2026-change-in-production")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)

# Debug route to check DB mode
@app.route("/debug/db")
def debug_db():
    try:
        supa = is_supabase()
        info = {
            "supabase_enabled": supa,
            "supabase_url": os.environ.get("SUPABASE_URL", "default"),
            "use_supabase_env": os.environ.get("USE_SUPABASE", "1"),
            "vercel": bool(os.environ.get("VERCEL")),
        }
        if supa and supabase_client:
            try:
                # Try to count equipment via supabase
                res = supabase_client.table("equipment").select("id", count="exact").execute()
                info["equipment_count_supabase"] = res.count if res.count is not None else len(res.data)
            except Exception as e:
                info["supabase_error"] = str(e)
        else:
            import sqlite3
            try:
                conn = get_db()
                cur = conn.execute("SELECT COUNT(*) as c FROM equipment")
                info["equipment_count_sqlite"] = cur.fetchone()["c"]
                conn.close()
            except Exception as e:
                info["sqlite_error"] = str(e)
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Ensure DB on startup
ensure_db()

# ---------- Helpers ----------
def get_current_user():
    if "user_id" in session:
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        conn.close()
        return user
    return None

def get_current_admin():
    if "admin_id" in session:
        conn = get_db()
        admin = conn.execute("SELECT * FROM admins WHERE id=?", (session["admin_id"],)).fetchone()
        conn.close()
        return admin
    return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("กรุณาเข้าสู่ระบบก่อนใช้งาน", "warning")
            return redirect(url_for("login", next=request.path))
        # check overdue on each authenticated request
        try:
            check_overdue()
        except:
            pass
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "admin_id" not in session:
            flash("กรุณาเข้าสู่ระบบผู้ดูแล", "warning")
            return redirect(url_for("admin_login"))
        try:
            check_overdue()
        except:
            pass
        return f(*args, **kwargs)
    return decorated

@app.before_request
def before_request():
    g.user = get_current_user()
    g.admin = get_current_admin()

@app.context_processor
def inject_globals():
    return dict(current_user=g.get("user", None), current_admin=g.get("admin", None))

def equipment_status(eq):
    if eq["available_quantity"] <= 0:
        return "ไม่พร้อมใช้งาน", "unavailable"
    elif eq["available_quantity"] < eq["total_quantity"]:
        # if some borrowed but still available -> "ว่าง"
        # if available >0 and borrowed >0 => show "ว่าง" but with badge borrowed count
        return "ว่าง", "available"
    else:
        return "ว่าง", "available"

def format_thai_date(date_str):
    if not date_str:
        return "-"
    try:
        # date_str could be YYYY-MM-DD or datetime
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(date_str[:19] if len(date_str)>10 else date_str, fmt)
                return dt.strftime("%d/%m/%Y")
            except:
                continue
        return date_str
    except:
        return date_str

app.jinja_env.filters["thai_date"] = format_thai_date
app.jinja_env.globals["equipment_status"] = equipment_status

# ---------- User Routes ----------
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if "admin_id" in session:
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        password = request.form.get("password", "")
        if not student_id or not password:
            flash("กรุณากรอกข้อมูลให้ครบ", "danger")
            return render_template("login.html")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE student_id=?", (student_id,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["student_id"] = user["student_id"]
            session["user_name"] = user["name"]
            session.permanent = True
            flash(f"ยินดีต้อนรับ {user['name']}", "success")
            nxt = request.args.get("next") or url_for("dashboard")
            return redirect(nxt)
        else:
            flash("รหัสนักเรียนหรือรหัสผ่านไม่ถูกต้อง", "danger")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        class_name = request.form.get("class_name", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        # validation
        if not student_id or not name or not password:
            flash("กรุณากรอกข้อมูลที่จำเป็นให้ครบ (รหัสนักเรียน, ชื่อ, รหัสผ่าน)", "danger")
            return render_template("register.html")
        if password != confirm:
            flash("รหัสผ่านไม่ตรงกัน", "danger")
            return render_template("register.html")
        if len(password) < 6:
            flash("รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร", "danger")
            return render_template("register.html")
        conn = get_db()
        try:
            existing = conn.execute("SELECT id FROM users WHERE student_id=?", (student_id,)).fetchone()
            if existing:
                flash("รหัสนักเรียนนี้มีผู้ใช้งานแล้ว", "danger")
                return render_template("register.html")
            if email:
                ex2 = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
                if ex2:
                    flash("อีเมลนี้มีผู้ใช้งานแล้ว", "danger")
                    return render_template("register.html")
            conn.execute("""
                INSERT INTO users (student_id, name, email, password_hash, class_name)
                VALUES (?, ?, ?, ?, ?)
            """, (student_id, name, email or None, generate_password_hash(password), class_name or None))
            conn.commit()
            flash("สมัครสมาชิกสำเร็จ กรุณาเข้าสู่ระบบ", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError as e:
            flash(f"เกิดข้อผิดพลาด: {e}", "danger")
        finally:
            conn.close()
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("ออกจากระบบแล้ว", "info")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()

    query = "SELECT * FROM equipment"
    params = []
    conditions = []
    if search:
        conditions.append("(name LIKE ? OR description LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id ASC"
    equipments = conn.execute(query, params).fetchall()

    # filter by status if requested (derived)
    filtered = []
    for eq in equipments:
        avail = eq["available_quantity"]
        total = eq["total_quantity"]
        borrowed = total - avail
        # status logic
        if avail <= 0:
            st = "ไม่พร้อมใช้งาน"
        elif borrowed > 0:
            st = "ถูกยืมบางส่วน"
        else:
            st = "ว่าง"
        # for display, we show badge based on availability
        eq_dict = dict(eq)
        eq_dict["borrowed_quantity"] = borrowed
        if avail <= 0:
            eq_dict["status_label"] = "ไม่พร้อมใช้งาน"
            eq_dict["status_class"] = "unavailable"
        elif avail < total:
            eq_dict["status_label"] = "ว่าง"
            eq_dict["status_class"] = "available"
        else:
            eq_dict["status_label"] = "ว่าง"
            eq_dict["status_class"] = "available"

        if status_filter:
            if status_filter == "available" and eq_dict["status_class"] != "available":
                continue
            if status_filter == "unavailable" and eq_dict["status_class"] != "unavailable":
                continue
            if status_filter == "borrowed" and borrowed == 0:
                continue
        filtered.append(eq_dict)

    # stats for dashboard header
    total_eq = conn.execute("SELECT COALESCE(SUM(total_quantity),0) as s FROM equipment").fetchone()["s"]
    total_avail = conn.execute("SELECT COALESCE(SUM(available_quantity),0) as s FROM equipment").fetchone()["s"]
    total_borrowed = total_eq - total_avail

    # user stats
    user_id = session["user_id"]
    my_pending = conn.execute("SELECT COUNT(*) as c FROM borrow_records WHERE user_id=? AND status='pending'", (user_id,)).fetchone()["c"]
    my_borrowed = conn.execute("SELECT COUNT(*) as c FROM borrow_records WHERE user_id=? AND status IN ('approved','borrowed')", (user_id,)).fetchone()["c"]
    my_overdue = conn.execute("SELECT COUNT(*) as c FROM borrow_records WHERE user_id=? AND status='overdue'", (user_id,)).fetchone()["c"]

    conn.close()
    return render_template("dashboard.html",
                           equipments=filtered,
                           search=search,
                           status_filter=status_filter,
                           total_eq=total_eq,
                           total_avail=total_avail,
                           total_borrowed=total_borrowed,
                           my_pending=my_pending,
                           my_borrowed=my_borrowed,
                           my_overdue=my_overdue)

@app.route("/equipment")
@login_required
def equipment_list():
    return redirect(url_for("dashboard"))

@app.route("/equipment/<int:eq_id>")
@login_required
def equipment_detail(eq_id):
    conn = get_db()
    eq = conn.execute("SELECT * FROM equipment WHERE id=?", (eq_id,)).fetchone()
    if not eq:
        conn.close()
        abort(404)
    eq_dict = dict(eq)
    eq_dict["borrowed_quantity"] = eq["total_quantity"] - eq["available_quantity"]
    if eq["available_quantity"] <= 0:
        eq_dict["status_label"] = "ไม่พร้อมใช้งาน"
        eq_dict["status_class"] = "unavailable"
    else:
        eq_dict["status_label"] = "ว่าง"
        eq_dict["status_class"] = "available"

    # history related to this equipment for current user (recent)
    history = conn.execute("""
        SELECT br.*, e.name as eq_name FROM borrow_records br
        JOIN equipment e ON e.id=br.equipment_id
        WHERE br.equipment_id=? AND br.user_id=?
        ORDER BY br.created_at DESC LIMIT 5
    """, (eq_id, session["user_id"])).fetchall()
    conn.close()
    return render_template("equipment_detail.html", eq=eq_dict, history=history)

@app.route("/borrow/<int:eq_id>", methods=["GET", "POST"])
@login_required
def borrow_confirm(eq_id):
    conn = get_db()
    eq = conn.execute("SELECT * FROM equipment WHERE id=?", (eq_id,)).fetchone()
    if not eq:
        conn.close()
        abort(404)
    eq_dict = dict(eq)
    eq_dict["borrowed_quantity"] = eq["total_quantity"] - eq["available_quantity"]

    if request.method == "POST":
        try:
            quantity = int(request.form.get("quantity", "1"))
        except:
            flash("จำนวนไม่ถูกต้อง", "danger")
            return render_template("borrow_confirm.html", eq=eq_dict)

        due_date_str = request.form.get("due_date", "").strip()

        # validations
        if quantity <= 0:
            flash("จำนวนต้องมากกว่า 0", "danger")
            return render_template("borrow_confirm.html", eq=eq_dict)
        # re-fetch to ensure not stale
        fresh = conn.execute("SELECT * FROM equipment WHERE id=?", (eq_id,)).fetchone()
        if fresh["available_quantity"] <= 0:
            flash("อุปกรณ์ไม่พร้อมใช้งาน ไม่สามารถยืมได้", "danger")
            conn.close()
            return redirect(url_for("equipment_detail", eq_id=eq_id))
        if quantity > fresh["available_quantity"]:
            flash(f"จำนวนที่ขอยืมเกินจำนวนที่ว่าง (ว่าง {fresh['available_quantity']} ชิ้น)", "danger")
            return render_template("borrow_confirm.html", eq=eq_dict)
        # due date validation
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            max_due = today + timedelta(days=30)
            if due_date <= today:
                flash("วันกำหนดคืนต้องเป็นวันถัดไปเป็นต้นไป", "danger")
                return render_template("borrow_confirm.html", eq=eq_dict)
            if due_date > max_due:
                flash("ยืมได้ไม่เกิน 30 วัน", "danger")
                return render_template("borrow_confirm.html", eq=eq_dict)
        except ValueError:
            flash("รูปแบบวันกำหนดคืนไม่ถูกต้อง", "danger")
            return render_template("borrow_confirm.html", eq=eq_dict)

        # check if user already has overdue
        overdue_cnt = conn.execute("SELECT COUNT(*) as c FROM borrow_records WHERE user_id=? AND status='overdue'", (session["user_id"],)).fetchone()["c"]
        if overdue_cnt > 0:
            flash("คุณมีรายการเกินกำหนด กรุณาคืนอุปกรณ์ก่อนทำรายการใหม่", "danger")
            return render_template("borrow_confirm.html", eq=eq_dict)

        # create borrow record with pending status
        conn.execute("""
            INSERT INTO borrow_records (user_id, equipment_id, quantity, due_date, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (session["user_id"], eq_id, quantity, due_date_str))
        conn.commit()
        conn.close()
        flash("ส่งคำขอยืมเรียบร้อย รอผู้ดูแลอนุมัติ", "success")
        return redirect(url_for("history"))

    # GET: prepare default due date = +7 days
    default_due = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    conn.close()
    return render_template("borrow_confirm.html", eq=eq_dict, default_due=default_due)

@app.route("/history")
@login_required
def history():
    conn = get_db()
    # update overdue before showing
    try:
        check_overdue()
    except:
        pass
    records = conn.execute("""
        SELECT br.*, e.name as eq_name, e.image as eq_image
        FROM borrow_records br
        JOIN equipment e ON e.id=br.equipment_id
        WHERE br.user_id=?
        ORDER BY br.created_at DESC
    """, (session["user_id"],)).fetchall()
    conn.close()
    return render_template("history.html", records=records)

@app.route("/return/<int:record_id>", methods=["POST"])
@login_required
def return_equipment(record_id):
    conn = get_db()
    rec = conn.execute("SELECT * FROM borrow_records WHERE id=? AND user_id=?", (record_id, session["user_id"])).fetchone()
    if not rec:
        conn.close()
        flash("ไม่พบรายการยืม", "danger")
        return redirect(url_for("history"))
    if rec["status"] not in ("approved", "borrowed", "overdue"):
        conn.close()
        flash("รายการนี้ไม่สามารถคืนได้ (สถานะ: {})".format(rec["status"]), "warning")
        return redirect(url_for("history"))
    # For user-initiated return, we set to pending return? But spec says return increments available.
    # We'll allow user to mark as wants to return, but actual increments only after admin confirms.
    # However to keep simple and satisfy business logic, we support direct user return that increments quantity
    # If overdue handling is via admin, but user can also trigger return.
    # Alternative: user request return -> we keep status borrowed but flash message to contact admin
    # Let's implement: user return marks as 'returned' directly and increments stock, to allow testing
    # Check: we could also require admin to confirm return via /admin/return/<id>
    # We'll implement user self-return for demo: update to returned and restore stock
    # But prevent double return
    # Restore stock
    try:
        # Ensure available_quantity won't exceed total
        eq = conn.execute("SELECT * FROM equipment WHERE id=?", (rec["equipment_id"],)).fetchone()
        new_avail = eq["available_quantity"] + rec["quantity"]
        if new_avail > eq["total_quantity"]:
            new_avail = eq["total_quantity"]
        conn.execute("UPDATE equipment SET available_quantity=? WHERE id=?", (new_avail, eq["id"]))
        conn.execute("UPDATE borrow_records SET status='returned', return_date=date('now','localtime') WHERE id=?", (record_id,))
        conn.commit()
        flash("คืนอุปกรณ์เรียบร้อย ขอบคุณค่ะ/ครับ", "success")
    except Exception as e:
        flash(f"เกิดข้อผิดพลาดในการคืน: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("history"))

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        class_name = request.form.get("class_name", "").strip()
        new_password = request.form.get("new_password", "").strip()
        if not name:
            flash("ชื่อห้ามว่าง", "danger")
            conn.close()
            return render_template("profile.html", user=user)
        try:
            if new_password:
                if len(new_password) < 6:
                    flash("รหัสผ่านใหม่ต้องมีอย่างน้อย 6 ตัวอักษร", "danger")
                    return render_template("profile.html", user=user)
                conn.execute("UPDATE users SET name=?, email=?, class_name=?, password_hash=? WHERE id=?",
                             (name, email or None, class_name or None, generate_password_hash(new_password), user["id"]))
            else:
                conn.execute("UPDATE users SET name=?, email=?, class_name=? WHERE id=?",
                             (name, email or None, class_name or None, user["id"]))
            conn.commit()
            flash("อัปเดตโปรไฟล์สำเร็จ", "success")
            # update session
            session["user_name"] = name
        except sqlite3.IntegrityError as e:
            flash(f"เกิดข้อผิดพลาด: {e}", "danger")
        user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    # stats
    stats = {}
    stats["total_borrows"] = conn.execute("SELECT COUNT(*) as c FROM borrow_records WHERE user_id=?", (user["id"],)).fetchone()["c"]
    stats["pending"] = conn.execute("SELECT COUNT(*) as c FROM borrow_records WHERE user_id=? AND status='pending'", (user["id"],)).fetchone()["c"]
    stats["borrowed"] = conn.execute("SELECT COUNT(*) as c FROM borrow_records WHERE user_id=? AND status IN ('approved','borrowed')", (user["id"],)).fetchone()["c"]
    stats["returned"] = conn.execute("SELECT COUNT(*) as c FROM borrow_records WHERE user_id=? AND status='returned'", (user["id"],)).fetchone()["c"]
    stats["overdue"] = conn.execute("SELECT COUNT(*) as c FROM borrow_records WHERE user_id=? AND status='overdue'", (user["id"],)).fetchone()["c"]
    conn.close()
    return render_template("profile.html", user=user, stats=stats)

# ---------- Admin Routes ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if "admin_id" in session:
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("กรุณากรอกข้อมูลให้ครบ", "danger")
            return render_template("admin/login.html")
        conn = get_db()
        admin = conn.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
        conn.close()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            session["admin_name"] = admin["name"]
            session.permanent = True
            flash(f"ยินดีต้อนรับผู้ดูแล {admin['name']}", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "danger")
    return render_template("admin/login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("ออกจากระบบผู้ดูแลแล้ว", "info")
    return redirect(url_for("admin_login"))

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db()
    check_overdue()
    total_eq = conn.execute("SELECT COALESCE(SUM(total_quantity),0) as s FROM equipment").fetchone()["s"]
    total_avail = conn.execute("SELECT COALESCE(SUM(available_quantity),0) as s FROM equipment").fetchone()["s"]
    total_borrowed = total_eq - total_avail
    overdue_count = conn.execute("SELECT COUNT(*) as c FROM borrow_records WHERE status='overdue'").fetchone()["c"]
    total_borrows = conn.execute("SELECT COUNT(*) as c FROM borrow_records").fetchone()["c"]
    pending_count = conn.execute("SELECT COUNT(*) as c FROM borrow_records WHERE status='pending'").fetchone()["c"]

    # recent records
    recent = conn.execute("""
        SELECT br.*, u.name as user_name, u.student_id, e.name as eq_name
        FROM borrow_records br
        JOIN users u ON u.id=br.user_id
        JOIN equipment e ON e.id=br.equipment_id
        ORDER BY br.created_at DESC LIMIT 8
    """).fetchall()

    # equipment stats for chart (borrowed per equipment)
    eq_stats = conn.execute("""
        SELECT e.name, e.total_quantity, e.available_quantity, (e.total_quantity - e.available_quantity) as borrowed
        FROM equipment e ORDER BY borrowed DESC
    """).fetchall()

    # monthly stats (last 6 months) - count borrows per month
    monthly = conn.execute("""
        SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as cnt
        FROM borrow_records
        GROUP BY month
        ORDER BY month DESC LIMIT 6
    """).fetchall()
    monthly = list(reversed(monthly))

    conn.close()
    return render_template("admin/dashboard.html",
                           total_eq=total_eq,
                           total_avail=total_avail,
                           total_borrowed=total_borrowed,
                           overdue_count=overdue_count,
                           total_borrows=total_borrows,
                           pending_count=pending_count,
                           recent=recent,
                           eq_stats=eq_stats,
                           monthly=monthly)

@app.route("/admin/equipment")
@admin_required
def admin_equipment():
    conn = get_db()
    equipments = conn.execute("SELECT * FROM equipment ORDER BY id ASC").fetchall()
    # add borrowed
    data = []
    for eq in equipments:
        d = dict(eq)
        d["borrowed_quantity"] = eq["total_quantity"] - eq["available_quantity"]
        data.append(d)
    conn.close()
    return render_template("admin/equipment.html", equipments=data)

@app.route("/admin/equipment/add", methods=["GET", "POST"])
@admin_required
def admin_equipment_add():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        image = request.form.get("image", "").strip()
        try:
            total_quantity = int(request.form.get("total_quantity", "0"))
            available_quantity = int(request.form.get("available_quantity", "0"))
        except:
            flash("จำนวนต้องเป็นตัวเลข", "danger")
            return render_template("admin/equipment_form.html", mode="add")
        if not name:
            flash("กรุณากรอกชื่ออุปกรณ์", "danger")
            return render_template("admin/equipment_form.html", mode="add")
        if total_quantity < 0 or available_quantity < 0:
            flash("จำนวนต้องไม่ติดลบ", "danger")
            return render_template("admin/equipment_form.html", mode="add")
        if available_quantity > total_quantity:
            flash("จำนวนที่ว่างต้องไม่เกินจำนวนทั้งหมด", "danger")
            return render_template("admin/equipment_form.html", mode="add")
        if not image:
            image = "https://images.unsplash.com/photo-1517649763962-0c623066013b?w=500&h=500&fit=crop"
        conn = get_db()
        conn.execute("""
            INSERT INTO equipment (name, description, image, total_quantity, available_quantity)
            VALUES (?, ?, ?, ?, ?)
        """, (name, description, image, total_quantity, available_quantity))
        conn.commit()
        conn.close()
        flash("เพิ่มอุปกรณ์สำเร็จ", "success")
        return redirect(url_for("admin_equipment"))
    return render_template("admin/equipment_form.html", mode="add")

@app.route("/admin/equipment/edit/<int:eq_id>", methods=["GET", "POST"])
@admin_required
def admin_equipment_edit(eq_id):
    conn = get_db()
    eq = conn.execute("SELECT * FROM equipment WHERE id=?", (eq_id,)).fetchone()
    if not eq:
        conn.close()
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        image = request.form.get("image", "").strip()
        try:
            total_quantity = int(request.form.get("total_quantity", "0"))
            available_quantity = int(request.form.get("available_quantity", "0"))
        except:
            flash("จำนวนต้องเป็นตัวเลข", "danger")
            return render_template("admin/equipment_form.html", mode="edit", eq=eq)
        if not name:
            flash("กรุณากรอกชื่ออุปกรณ์", "danger")
            return render_template("admin/equipment_form.html", mode="edit", eq=eq)
        if total_quantity < 0 or available_quantity < 0:
            flash("จำนวนต้องไม่ติดลบ", "danger")
            return render_template("admin/equipment_form.html", mode="edit", eq=eq)
        if available_quantity > total_quantity:
            flash("จำนวนที่ว่างต้องไม่เกินจำนวนทั้งหมด", "danger")
            return render_template("admin/equipment_form.html", mode="edit", eq=eq)
        # ensure not setting available less than borrowed count inconsistency? We allow but check
        borrowed = eq["total_quantity"] - eq["available_quantity"]
        # if reducing total below borrowed, adjust available
        # Actually borrowed = total - avail, so if new total < borrowed, we need to clamp
        if total_quantity < (eq["total_quantity"] - eq["available_quantity"]):
            # borrowed items still out, so available should be total - borrowed, but if total < borrowed, set avail 0
            # Let's prevent invalid: total cannot be less than currently borrowed count
            currently_borrowed = eq["total_quantity"] - eq["available_quantity"]
            if total_quantity < currently_borrowed:
                flash(f"จำนวนทั้งหมดต้องไม่น้อยกว่าจำนวนที่ถูกยืมอยู่ ({currently_borrowed} ชิ้น)", "danger")
                return render_template("admin/equipment_form.html", mode="edit", eq=eq)
        conn.execute("""
            UPDATE equipment SET name=?, description=?, image=?, total_quantity=?, available_quantity=?
            WHERE id=?
        """, (name, description, image or eq["image"], total_quantity, available_quantity, eq_id))
        conn.commit()
        conn.close()
        flash("แก้ไขอุปกรณ์สำเร็จ", "success")
        return redirect(url_for("admin_equipment"))
    conn.close()
    return render_template("admin/equipment_form.html", mode="edit", eq=eq)

@app.route("/admin/equipment/delete/<int:eq_id>", methods=["POST"])
@admin_required
def admin_equipment_delete(eq_id):
    conn = get_db()
    eq = conn.execute("SELECT * FROM equipment WHERE id=?", (eq_id,)).fetchone()
    if not eq:
        conn.close()
        abort(404)
    # check if has active borrows
    active = conn.execute("SELECT COUNT(*) as c FROM borrow_records WHERE equipment_id=? AND status IN ('pending','approved','borrowed','overdue')", (eq_id,)).fetchone()["c"]
    if active > 0:
        conn.close()
        flash("ไม่สามารถลบอุปกรณ์ที่มีรายการยืมค้างอยู่ได้", "danger")
        return redirect(url_for("admin_equipment"))
    conn.execute("DELETE FROM equipment WHERE id=?", (eq_id,))
    conn.commit()
    conn.close()
    flash("ลบอุปกรณ์สำเร็จ", "success")
    return redirect(url_for("admin_equipment"))

@app.route("/admin/borrow-records")
@admin_required
def admin_borrow_records():
    conn = get_db()
    check_overdue()
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()

    query = """
        SELECT br.*, u.name as user_name, u.student_id, u.class_name, e.name as eq_name, e.image as eq_image
        FROM borrow_records br
        JOIN users u ON u.id=br.user_id
        JOIN equipment e ON e.id=br.equipment_id
    """
    params = []
    conditions = []
    if search:
        conditions.append("(u.name LIKE ? OR u.student_id LIKE ? OR e.name LIKE ? OR br.id LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
    if status_filter:
        conditions.append("br.status=?")
        params.append(status_filter)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY br.created_at DESC"
    records = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("admin/borrow_records.html", records=records, search=search, status_filter=status_filter)

@app.route("/admin/borrow/<int:record_id>/approve", methods=["POST"])
@admin_required
def admin_borrow_approve(record_id):
    conn = get_db()
    rec = conn.execute("SELECT * FROM borrow_records WHERE id=?", (record_id,)).fetchone()
    if not rec:
        conn.close()
        abort(404)
    if rec["status"] != "pending":
        conn.close()
        flash("รายการนี้ไม่อยู่ในสถานะรอการอนุมัติ", "warning")
        return redirect(url_for("admin_borrow_records"))
    eq = conn.execute("SELECT * FROM equipment WHERE id=?", (rec["equipment_id"],)).fetchone()
    if eq["available_quantity"] < rec["quantity"]:
        conn.close()
        flash(f"อุปกรณ์ไม่พอให้ยืม (ว่าง {eq['available_quantity']} ชิ้น)", "danger")
        return redirect(url_for("admin_borrow_records"))
    if eq["available_quantity"] - rec["quantity"] < 0:
        conn.close()
        flash("จำนวนอุปกรณ์จะติดลบ ไม่สามารถอนุมัติได้", "danger")
        return redirect(url_for("admin_borrow_records"))
    # deduct
    new_avail = eq["available_quantity"] - rec["quantity"]
    conn.execute("UPDATE equipment SET available_quantity=? WHERE id=?", (new_avail, eq["id"]))
    conn.execute("""
        UPDATE borrow_records SET status='approved', borrow_date=date('now','localtime'), approved_by=?
        WHERE id=?
    """, (session["admin_id"], record_id))
    # also set to borrowed automatically? Spec has pending->approved->borrowed separate.
    # We'll keep approved, but also treat approved as borrowed for availability. Overdue checks include approved.
    # Optionally auto set to borrowed
    # Let's keep approved, user considered borrowed after approval.
    conn.commit()
    conn.close()
    flash("อนุมัติการยืมเรียบร้อย", "success")
    return redirect(url_for("admin_borrow_records"))

@app.route("/admin/borrow/<int:record_id>/reject", methods=["POST"])
@admin_required
def admin_borrow_reject(record_id):
    conn = get_db()
    rec = conn.execute("SELECT * FROM borrow_records WHERE id=?", (record_id,)).fetchone()
    if not rec:
        conn.close()
        abort(404)
    if rec["status"] != "pending":
        conn.close()
        flash("รายการนี้ไม่อยู่ในสถานะรอการอนุมัติ", "warning")
        return redirect(url_for("admin_borrow_records"))
    conn.execute("UPDATE borrow_records SET status='rejected', approved_by=? WHERE id=?", (session["admin_id"], record_id))
    conn.commit()
    conn.close()
    flash("ปฏิเสธการยืมเรียบร้อย", "info")
    return redirect(url_for("admin_borrow_records"))

@app.route("/admin/return/<int:record_id>", methods=["POST"])
@admin_required
def admin_return(record_id):
    conn = get_db()
    rec = conn.execute("SELECT * FROM borrow_records WHERE id=?", (record_id,)).fetchone()
    if not rec:
        conn.close()
        abort(404)
    if rec["status"] not in ("approved", "borrowed", "overdue"):
        conn.close()
        flash("รายการนี้ไม่สามารถบันทึกการคืนได้", "warning")
        return redirect(url_for("admin_borrow_records"))
    eq = conn.execute("SELECT * FROM equipment WHERE id=?", (rec["equipment_id"],)).fetchone()
    new_avail = eq["available_quantity"] + rec["quantity"]
    if new_avail > eq["total_quantity"]:
        new_avail = eq["total_quantity"]
    # Also ensure not negative – already handled
    conn.execute("UPDATE equipment SET available_quantity=? WHERE id=?", (new_avail, eq["id"]))
    conn.execute("UPDATE borrow_records SET status='returned', return_date=date('now','localtime') WHERE id=?", (record_id,))
    conn.commit()
    conn.close()
    flash("บันทึกการคืนเรียบร้อย", "success")
    return redirect(url_for("admin_borrow_records"))

@app.route("/admin/history")
@admin_required
def admin_history():
    conn = get_db()
    records = conn.execute("""
        SELECT br.*, u.name as user_name, u.student_id, e.name as eq_name
        FROM borrow_records br
        JOIN users u ON u.id=br.user_id
        JOIN equipment e ON e.id=br.equipment_id
        ORDER BY br.created_at DESC
    """).fetchall()
    # also search filters
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()
    # if filters provided, re-query (simple)
    if search or status_filter:
        query = """
            SELECT br.*, u.name as user_name, u.student_id, e.name as eq_name
            FROM borrow_records br
            JOIN users u ON u.id=br.user_id
            JOIN equipment e ON e.id=br.equipment_id
        """
        params = []
        conds = []
        if search:
            conds.append("(u.name LIKE ? OR u.student_id LIKE ? OR e.name LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        if status_filter:
            conds.append("br.status=?")
            params.append(status_filter)
        if conds:
            query += " WHERE " + " AND ".join(conds)
        query += " ORDER BY br.created_at DESC"
        records = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("admin/history.html", records=records, search=search, status_filter=status_filter)

# ---------- Error Handlers ----------
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500

# also handle generic exception for 500
@app.errorhandler(Exception)
def handle_exception(e):
    # if it's HTTPException, let it pass
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    print(f"[Error] {e}")
    return render_template("500.html"), 500

if __name__ == "__main__":
    ensure_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
