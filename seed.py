import sqlite3
import os
from werkzeug.security import generate_password_hash

from database import DB_PATH, init_db

EQUIPMENTS = [
    {
        "name": "ลูกบาสเกตบอล",
        "description": "ลูกบาสเกตบอลมาตรฐาน ขนาด 7 สำหรับการแข่งขันและฝึกซ้อม เหมาะสำหรับสนามในร่มและกลางแจ้ง",
        "image": "https://images.unsplash.com/photo-1546519638-68e109498ffc?w=500&h=500&fit=crop",
        "total_quantity": 20,
        "available_quantity": 15,
    },
    {
        "name": "ลูกฟุตบอล",
        "description": "ลูกฟุตบอลหนัง PU คุณภาพสูง ขนาด 5 มาตรฐานสากล ทนทาน เหมาะสำหรับฝึกซ้อมและแข่งขัน",
        "image": "https://images.unsplash.com/photo-16146325371907-2270a9221d2f?w=500&h=500&fit=crop",
        "total_quantity": 25,
        "available_quantity": 20,
    },
    {
        "name": "ไม้แบดมินตัน",
        "description": "ไม้แบดมินตันน้ำหนักเบา เฟรมคาร์บอน แถมเอ็นขึงพร้อมใช้งาน เหมาะสำหรับนักเรียนทุกระดับ",
        "image": "https://images.unsplash.com/photo-1626224583764-f87db24ac4ea?w=500&h=500&fit=crop",
        "total_quantity": 30,
        "available_quantity": 22,
    },
    {
        "name": "ลูกแบดมินตัน",
        "description": "ลูกแบดมินตันขนห่าน/ไนลอน คุณภาพดี บรรจุหลอดละ 12 ลูก เหมาะสำหรับฝึกซ้อม",
        "image": "https://images.unsplash.com/photo-1554068865-24cecd4e34b8?w=500&h=500&fit=crop",
        "total_quantity": 50,
        "available_quantity": 40,
    },
    {
        "name": "ลูกตะกร้อ",
        "description": "ลูกตะกร้อหวายเทียมมาตรฐานการแข่งขัน น้ำหนักเบา ทนทาน เหมาะสำหรับฝึกซ้อมและแข่งขัน",
        "image": "https://images.unsplash.com/photo-1517649763962-0c623066013b?w=500&h=500&fit=crop",
        "total_quantity": 15,
        "available_quantity": 10,
    },
    {
        "name": "ลูกวอลเลย์บอล",
        "description": "ลูกวอลเลย์บอลหนังนุ่ม ขนาด 5 มาตรฐานสากล ซับแรงกระแทกดี เหมาะสำหรับฝึกซ้อม",
        "image": "https://images.unsplash.com/photo-1612872087720-bb876e2e67d1?w=500&h=500&fit=crop",
        "total_quantity": 18,
        "available_quantity": 12,
    },
]

USERS = [
    {"student_id": "CRU66001", "name": "สมชาย ใจดี", "email": "somchai@cru.ac.th", "password": "123456", "class_name": "ม.5/1"},
    {"student_id": "CRU66002", "name": "สมหญิง รักเรียน", "email": "somying@cru.ac.th", "password": "123456", "class_name": "ม.5/2"},
    {"student_id": "CRU66003", "name": "อนนท์ กีฬาเด่น", "email": "anon@cru.ac.th", "password": "123456", "class_name": "ม.6/1"},
    {"student_id": "CRU66004", "name": "มานี มีวินัย", "email": "manee@cru.ac.th", "password": "123456", "class_name": "ม.4/3"},
    {"student_id": "student", "name": "นักเรียนทดสอบ", "email": "student@cru.ac.th", "password": "student123", "class_name": "ม.6/5"},
]

ADMINS = [
    {"username": "admin", "password": "admin123", "name": "ผู้ดูแลระบบกีฬา"},
    {"username": "cru_admin", "password": "cru1234", "name": "ครูพละ CRU"},
]

def seed_data():
    # ensure DB exists
    if not os.path.exists(DB_PATH):
        init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # check if already seeded
    cur.execute("SELECT COUNT(*) as c FROM equipment")
    if cur.fetchone()["c"] > 0:
        # check users too
        cur.execute("SELECT COUNT(*) as c FROM users")
        if cur.fetchone()["c"] > 0:
            print("Seed skipped: data already exists")
            conn.close()
            return

    print("Seeding database...")

    # clear old if partial
    cur.execute("DELETE FROM borrow_records")
    cur.execute("DELETE FROM equipment")
    cur.execute("DELETE FROM users")
    cur.execute("DELETE FROM admins")

    for eq in EQUIPMENTS:
        cur.execute("""
            INSERT INTO equipment (name, description, image, total_quantity, available_quantity)
            VALUES (?, ?, ?, ?, ?)
        """, (eq["name"], eq["description"], eq["image"], eq["total_quantity"], eq["available_quantity"]))

    for u in USERS:
        cur.execute("""
            INSERT INTO users (student_id, name, email, password_hash, class_name)
            VALUES (?, ?, ?, ?, ?)
        """, (u["student_id"], u["name"], u["email"], generate_password_hash(u["password"]), u["class_name"]))

    for a in ADMINS:
        cur.execute("""
            INSERT INTO admins (username, password_hash, name)
            VALUES (?, ?, ?)
        """, (a["username"], generate_password_hash(a["password"]), a["name"]))

    # create sample borrow records
    # need ids
    cur.execute("SELECT id FROM users WHERE student_id='CRU66001'")
    u1 = cur.fetchone()["id"]
    cur.execute("SELECT id FROM users WHERE student_id='CRU66002'")
    u2 = cur.fetchone()["id"]
    cur.execute("SELECT id FROM equipment WHERE name='ลูกบาสเกตบอล'")
    eq_basket = cur.fetchone()["id"]
    cur.execute("SELECT id FROM equipment WHERE name='ไม้แบดมินตัน'")
    eq_badminton = cur.fetchone()["id"]
    cur.execute("SELECT id FROM admins WHERE username='admin'")
    admin_id = cur.fetchone()["id"]

    # sample: approved/borrowed
    cur.execute("""
        INSERT INTO borrow_records (user_id, equipment_id, quantity, borrow_date, due_date, status, approved_by)
        VALUES (?, ?, ?, date('now','localtime'), date('now','+7 days'), 'borrowed', ?)
    """, (u1, eq_basket, 2, admin_id))
    # decrement available for borrowed sample - to keep consistent, update equipment
    cur.execute("UPDATE equipment SET available_quantity = available_quantity - 2 WHERE id=?", (eq_basket,))

    cur.execute("""
        INSERT INTO borrow_records (user_id, equipment_id, quantity, borrow_date, due_date, status, approved_by)
        VALUES (?, ?, ?, date('now','localtime'), date('now','+3 days'), 'approved', ?)
    """, (u2, eq_badminton, 1, admin_id))
    cur.execute("UPDATE equipment SET available_quantity = available_quantity - 1 WHERE id=?", (eq_badminton,))

    # pending sample
    cur.execute("""
        INSERT INTO borrow_records (user_id, equipment_id, quantity, due_date, status)
        VALUES (?, ?, ?, date('now','+7 days'), 'pending')
    """, (u1, eq_badminton, 2))

    # overdue sample (borrowed but due yesterday)
    cur.execute("""
        INSERT INTO borrow_records (user_id, equipment_id, quantity, borrow_date, due_date, status, approved_by)
        VALUES (?, ?, ?, date('now','-10 days'), date('now','-3 days'), 'overdue', ?)
    """, (u2, eq_basket, 1, admin_id))
    cur.execute("UPDATE equipment SET available_quantity = available_quantity - 1 WHERE id=?", (eq_basket,))

    # returned sample
    cur.execute("""
        INSERT INTO borrow_records (user_id, equipment_id, quantity, borrow_date, due_date, return_date, status, approved_by)
        VALUES (?, ?, ?, date('now','-10 days'), date('now','-3 days'), date('now','-2 days'), 'returned', ?)
    """, (u1, eq_basket, 1, admin_id))

    conn.commit()
    conn.close()
    print("Seeding complete.")

if __name__ == "__main__":
    init_db()
    seed_data()
