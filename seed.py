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
        "available_quantity": 20,
    },
    {
        "name": "ลูกฟุตบอล",
        "description": "ลูกฟุตบอลหนัง PU คุณภาพสูง ขนาด 5 มาตรฐานสากล ทนทาน เหมาะสำหรับฝึกซ้อมและแข่งขัน",
        "image": "https://images.unsplash.com/photo-16146325371907-2270a9221d2f?w=500&h=500&fit=crop",
        "total_quantity": 25,
        "available_quantity": 25,
    },
    {
        "name": "ไม้แบดมินตัน",
        "description": "ไม้แบดมินตันน้ำหนักเบา เฟรมคาร์บอน แถมเอ็นขึงพร้อมใช้งาน เหมาะสำหรับนักเรียนทุกระดับ",
        "image": "https://images.unsplash.com/photo-1626224583764-f87db24ac4ea?w=500&h=500&fit=crop",
        "total_quantity": 30,
        "available_quantity": 30,
    },
    {
        "name": "ลูกแบดมินตัน",
        "description": "ลูกแบดมินตันขนห่าน/ไนลอน คุณภาพดี บรรจุหลอดละ 12 ลูก เหมาะสำหรับฝึกซ้อม",
        "image": "https://images.unsplash.com/photo-1554068865-24cecd4e34b8?w=500&h=500&fit=crop",
        "total_quantity": 50,
        "available_quantity": 50,
    },
    {
        "name": "ลูกตะกร้อ",
        "description": "ลูกตะกร้อหวายเทียมมาตรฐานการแข่งขัน น้ำหนักเบา ทนทาน เหมาะสำหรับฝึกซ้อมและแข่งขัน",
        "image": "https://images.unsplash.com/photo-1517649763962-0c623066013b?w=500&h=500&fit=crop",
        "total_quantity": 15,
        "available_quantity": 15,
    },
    {
        "name": "ลูกวอลเลย์บอล",
        "description": "ลูกวอลเลย์บอลหนังนุ่ม ขนาด 5 มาตรฐานสากล ซับแรงกระแทกดี เหมาะสำหรับฝึกซ้อม",
        "image": "https://images.unsplash.com/photo-1612872087720-bb876e2e67d1?w=500&h=500&fit=crop",
        "total_quantity": 18,
        "available_quantity": 18,
    },
]

# Clean data - no mock borrow records, only essential accounts
USERS = [
    {"student_id": "student", "name": "นักเรียนทดสอบ", "email": "student@cru.ac.th", "password": "student123", "class_name": "ม.6/5"},
    {"student_id": "CRU66001", "name": "สมชาย ใจดี", "email": "somchai@cru.ac.th", "password": "123456", "class_name": "ม.5/1"},
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

    # No mock borrow_records - clean start with 0 borrows
    # Equipment available_quantity remains equal to total_quantity
    conn.commit()
    conn.close()
    print("Seeding complete - clean data (no mock borrow records).")

if __name__ == "__main__":
    init_db()
    seed_data()
