# CRUSportShare

# CRU Sports Borrow — ระบบยืม-คืนอุปกรณ์กีฬา โรงเรียนชลราษฎรอำรุง (CRU)

ระบบ Full-Stack แก้ปัญหานักเรียนไม่รู้ว่ามีอุปกรณ์อะไรบ้าง อะไรว่าง/ถูกยืม และลดอุปกรณ์สูญหาย  
**Theme:** Navy Blue `#0f2a44` / White / Orange `#ff7a00` — Modern Clean School System

---

## เทคโนโลยี (ฟรีทั้งหมด)

- **Backend:** Python 3.11+, Flask 3, SQLite (sqlite3)
- **Frontend:** HTML5, CSS3, JavaScript, Jinja2
- **Dev:** VS Code, ไม่ใช้บริการเสียเงิน/DB ออนไลน์/API เสียเงิน

---

## โครงสร้างโปรเจค

```
cru_sports_borrow/
├── app.py
├── database.py
├── schema.sql
├── seed.py
├── requirements.txt
├── README.md
├── database/
│   └── cru_sports.db  (สร้างอัตโนมัติ)
├── static/
│   ├── css/style.css
│   ├── js/main.js
│   └── images/cru-logo.png (ถ้าไม่มี ระบบยังรันได้)
└── templates/
    ├── base.html
    ├── login.html
    ├── register.html
    ├── dashboard.html
    ├── equipment_detail.html
    ├── borrow_confirm.html
    ├── history.html
    ├── profile.html
    ├── 404.html
    ├── 500.html
    └── admin/
        ├── login.html
        ├── dashboard.html
        ├── equipment.html
        ├── equipment_form.html
        ├── borrow_records.html
        └── history.html
```

---

## 1. ติดตั้ง Python

ดาวน์โหลด Python 3.11+ จาก https://www.python.org/downloads/  
ตรวจสอบ:

```bash
python --version
pip --version
```

## 2. เปิด VS Code

```bash
code cru_sports_borrow
```
หรือเปิดโฟลเดอร์ `cru_sports_borrow` ใน VS Code

## 3. เปิด Project (Terminal ใน VS Code: Ctrl+`)

```bash
cd cru_sports_borrow
# Windows
dir
# macOS/Linux
ls
```

## 4. สร้าง Virtual Environment

```bash
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1
# ถ้าติด Policy: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

## 5. ติดตั้ง Dependencies

```bash
pip install -r requirements.txt
```

## 6. สร้าง Database

อัตโนมัติเมื่อรัน `app.py` ครั้งแรก หรือรันเอง:

```bash
python -c "from database import init_db; init_db(); print('DB created')"
```

## 7. เพิ่มข้อมูลตัวอย่าง (Seed)

```bash
python seed.py
```

จะสร้าง:
- อุปกรณ์ 6 ชนิด: ลูกบาสเกตบอล, ลูกฟุตบอล, ไม้แบดมินตัน, ลูกแบดมินตัน, ลูกตะกร้อ, ลูกวอลเลย์บอล
- นักเรียน 5 คน + Admin 2 คน
- ตัวอย่าง borrow_records 5 รายการ (pending/approved/borrowed/overdue/returned)

> รันซ้ำได้ — ถ้ามีข้อมูลอยู่แล้วจะข้าม seeding

## 8. รัน Flask

```bash
python app.py
```
หรือ:
```bash
flask --app app run --debug --port 5000
```

## 9. เปิดเว็บไซต์

- นักเรียน: http://127.0.0.1:5000/  → redirect ไป `/login`
- ผู้ดูแล: http://127.0.0.1:5000/admin/login

---

## 10. วิธี Login (นักเรียน)

- ไป http://127.0.0.1:5000/login
- ใช้บัญชีทดสอบ:

| Role | รหัสนักเรียน / Username | รหัสผ่าน |
|------|--------------------------|-----------|
| นักเรียน | `student` | `student123` |
| นักเรียน | `CRU66001` | `123456` |
| นักเรียน | `CRU66002` | `123456` |

หลัง login จะไป `/dashboard`

## 11. วิธีสมัคร/เพิ่มนักเรียน

- กด “สมัครสมาชิก” ที่หน้า login หรือไป http://127.0.0.1:5000/register
- กรอก: รหัสนักเรียน*, ชื่อ*, อีเมล, ชั้น, รหัสผ่าน* (≥6 ตัว), ยืนยันรหัสผ่าน
- ระบบ hash รหัสผ่านด้วย `werkzeug.security.generate_password_hash` ไม่เก็บ plain text

## 12. วิธีใช้งานระบบยืม

1. ที่ `/dashboard` ดู Card อุปกรณ์: รูป, ชื่อ, ทั้งหมด/ว่าง/ถูกยืม, สถานะ (ว่าง/ไม่พร้อมใช้งาน)
2. ใช้ Search และ filter (ว่าง/ถูกยืมบางส่วน/ไม่พร้อมใช้งาน)
3. กด “รายละเอียด” → `/equipment/<id>`
4. กด “ยืม” → `/borrow/<id>` เลือกจำนวน (≤ว่าง) และวันกำหนดคืน (1–30 วันข้างหน้า)
5. กด “ยืนยันการยืม” → สร้างรายการ `pending` → ไป `/history`
6. รอผู้ดูแลอนุมัติที่ `/admin/borrow-records` → อนุมัติแล้ว `available_quantity` จะลดลง

**Business Logic:** ถ้า `available_quantity==0` ห้ามยืม, ถ้า `available_quantity >= จำนวนที่ขอยืม` จึงสร้างรายการได้

## 13. วิธีคืน

- **นักเรียน:** ที่ `/history` กด “คืนอุปกรณ์” (สำหรับสถานะ approved/borrowed/overdue) → `POST /return/<id>` → `available_quantity` เพิ่มกลับ, สถานะ `returned`
- **ผู้ดูแล:** ที่ `/admin/borrow-records` กด “บันทึกคืน” → `POST /admin/return/<id>` → ผลเดียวกัน

ห้าม `available_quantity` ติดลบ และไม่เกิน `total_quantity`

## 14. วิธีเข้า Admin

- ไป http://127.0.0.1:5000/admin/login
- บัญชีทดสอบ:

| Username | Password | ชื่อ |
|----------|----------|------|
| `admin` | `admin123` | ผู้ดูแลระบบกีฬา |
| `cru_admin` | `cru1234` | ครูพละ CRU |

หลัง login ไป `/admin/dashboard` แสดง: อุปกรณ์ทั้งหมด, ว่าง, ถูกยืม, เกินกำหนด, การยืมทั้งหมด, กราฟสถิติ

## 15. วิธีจัดการอุปกรณ์ (Admin)

- **ดู:** `/admin/equipment`
- **เพิ่ม:** `/admin/equipment/add` — กรอกชื่อ, คำอธิบาย, URL รูป, ทั้งหมด, ว่าง (ว่าง≤ทั้งหมด, ห้ามติดลบ)
- **แก้ไข:** `/admin/equipment/edit/<id>` — ห้ามลดทั้งหมดต่ำกว่าจำนวนที่ถูกยืมอยู่
- **ลบ:** `POST /admin/equipment/delete/<id>` — ห้ามลบถ้ามีรายการค้าง (pending/approved/borrowed/overdue)
- **ดูรายการยืม:** `/admin/borrow-records` — ค้นหานักเรียน/อุปกรณ์, กรองสถานะ, อนุมัติ/ปฏิเสธ/บันทึกคืน
- **ประวัติ:** `/admin/history` — ดูประวัติทั้งหมด พร้อมค้นหา/กรอง

---

## Routes ทั้งหมด

```
/, /login, /logout, /register
/dashboard, /equipment, /equipment/<id>, /borrow/<id>, /history, /return/<id>, /profile
/admin/login, /admin/logout, /admin/dashboard, /admin/equipment, /admin/equipment/add,
//admin/equipment/edit/<id>, /admin/equipment/delete/<id>, /admin/borrow-records,
//admin/borrow/<id>/approve, /admin/borrow/<id>/reject, /admin/return/<id>, /admin/history
```

## Database Schema

- `users(id, student_id, name, email, password_hash, class_name, created_at)`
- `admins(id, username, password_hash, name, created_at)`
- `equipment(id, name, description, image, total_quantity, available_quantity, created_at)`
- `borrow_records(id, user_id, equipment_id, quantity, borrow_date, due_date, return_date, status, approved_by, created_at)`  
  `status ∈ {pending, approved, borrowed, returned, overdue, rejected}`

Seed สร้าง DB อัตโนมัติเมื่อเริ่มโปรแกรมครั้งแรก (เรียก `ensure_db()` ใน `app.py`)

## Security

- `Flask session` + `login_required` / `admin_required` decorators
- `check_password_hash` / `generate_password_hash`
- Parameterized SQL (`?` placeholders) ป้องกัน SQL Injection
- Input validation (จำนวน, วันกำหนดคืน, รหัสผ่าน)
- ป้องกัน User เข้า `/admin/*` โดยไม่ได้รับอนุญาต

## Error Handling

- `404.html`, `500.html`
- ไม่ crash เมื่อ ID ไม่ถูกต้อง, อุปกรณ์ไม่มี, จำนวนไม่พอ, DB ไม่มีข้อมูล

## ทดสอบรัน

```bash
# ตรวจสอบ syntax
python -m py_compile app.py database.py seed.py

# รันและทดสอบ flow
python app.py
# เปิดเบราว์เซอร์:
# 1. Login student/student123 → Dashboard → ยืมลูกฟุตบอล 1 ชิ้น → History (pending)
# 2. เปิดอีกเบราว์เซอร์/Admin: admin/admin123 → Borrow Records → อนุมัติ → ตรวจสอบว่าจำนวนว่างลดลง
# 3. กลับฝั่งนักเรียน: History → คืนอุปกรณ์ → ตรวจสอบว่าจำนวนว่างเพิ่มกลับ
# 4. ทดสอบ overdue: ระบบเช็ค overdue อัตโนมัติทุก request (due_date < today → status overdue)
```

## การใส่โลโก้

วางไฟล์ที่ `static/images/cru-logo.png` (PNG/SVG) — ถ้าไม่มี ระบบจะแสดงตัวอักษร “CRU” แทนโดยไม่ error

## License

MIT — ใช้เพื่อการศึกษาสำหรับโรงเรียนชลราษฎรอำรุง

