"""
database.py — AssignEval database schema
Tables: institutions, users, assignments, submissions, rubric_templates
"""
import sqlite3, os
DB_PATH = os.path.join(os.path.dirname(__file__), "evaluator.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    db = get_db()

    db.execute("""CREATE TABLE IF NOT EXISTS institutions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, code TEXT UNIQUE NOT NULL,
        domain TEXT, created_at TEXT NOT NULL)""")

    db.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'teacher',
        full_name TEXT, institution TEXT, department TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL, last_login TEXT)""")

    db.execute("""CREATE TABLE IF NOT EXISTS assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        assignment_id TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL, subject TEXT NOT NULL,
        max_marks INTEGER NOT NULL, deadline TEXT NOT NULL,
        rubric TEXT NOT NULL, teacher_name TEXT NOT NULL,
        teacher_id INTEGER, institution TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (teacher_id) REFERENCES users(id))""")

    db.execute("""CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id TEXT UNIQUE NOT NULL,
        assignment_id TEXT NOT NULL,
        student_name TEXT NOT NULL, roll_number TEXT NOT NULL,
        email TEXT, student_id INTEGER, filename TEXT NOT NULL,
        submission_type TEXT NOT NULL, extracted_text TEXT,
        ai_marks INTEGER, ai_feedback TEXT, ai_breakdown TEXT,
        teacher_marks INTEGER, teacher_feedback TEXT,
        teacher_approved INTEGER DEFAULT 0,
        final_marks INTEGER, max_marks INTEGER NOT NULL,
        needs_review INTEGER DEFAULT 0,
        submitted_at TEXT NOT NULL, reviewed_at TEXT,
        FOREIGN KEY (assignment_id) REFERENCES assignments(assignment_id),
        FOREIGN KEY (student_id) REFERENCES users(id))""")

    db.execute("""CREATE TABLE IF NOT EXISTS rubric_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, subject TEXT NOT NULL,
        rubric_text TEXT NOT NULL, teacher_id INTEGER,
        is_public INTEGER DEFAULT 0, created_at TEXT NOT NULL,
        FOREIGN KEY (teacher_id) REFERENCES users(id))""")

    _migrate(db)
    db.commit()
    db.close()
    print("✅ Database ready")

def _migrate(db):
    sub_cols = {
        "ai_marks":"INTEGER","ai_feedback":"TEXT","ai_breakdown":"TEXT",
        "teacher_marks":"INTEGER","teacher_feedback":"TEXT",
        "teacher_approved":"INTEGER DEFAULT 0","final_marks":"INTEGER",
        "reviewed_at":"TEXT","student_id":"INTEGER"
    }
    assign_cols = {"teacher_id":"INTEGER","institution":"TEXT"}
    _add_cols(db,"submissions",sub_cols)
    _add_cols(db,"assignments",assign_cols)
    try:
        _add_cols(db,"users",{"full_name":"TEXT","institution":"TEXT",
                               "department":"TEXT","is_active":"INTEGER DEFAULT 1","last_login":"TEXT"})
    except: pass

def _add_cols(db, table, cols):
    existing = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
    for col, typ in cols.items():
        if col not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")

if __name__ == "__main__":
    init_db()
