from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import os, uuid, json, shutil
from datetime import datetime
from database import init_db, get_db
from evaluator import evaluate_submission
from excel_generator import generate_excel
from auth import hash_password, check_password, create_token, require_auth, require_teacher, require_admin, decode_token
import fitz

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app, supports_credentials=True)
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Static ────────────────────────────────────────────────────────────────────
@app.route("/")
def index(): return send_from_directory("../frontend","index.html")

@app.route("/pages/<path:filename>")
def serve_pages(filename):
    return send_from_directory(os.path.join(os.path.dirname(__file__),"../frontend/pages"), filename)

@app.route("/<path:path>")
def serve_static(path):
    if path.startswith("api/"): from flask import abort; abort(404)
    fp = os.path.join(os.path.dirname(__file__),"../frontend",path)
    return send_from_directory(os.path.dirname(fp), os.path.basename(fp)) if os.path.exists(fp) else send_from_directory("../frontend","index.html")

# ── AUTH ──────────────────────────────────────────────────────────────────────
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    for f in ["username","email","password","full_name"]:
        if not data.get(f): return jsonify({"error": f"Missing: {f}"}), 400
    if len(data["password"]) < 6: return jsonify({"error":"Password must be at least 6 characters"}), 400
    db = get_db()
    if db.execute("SELECT id FROM users WHERE email=?",(data["email"],)).fetchone():
        return jsonify({"error":"Email already registered"}), 409
    if db.execute("SELECT id FROM users WHERE username=?",(data["username"],)).fetchone():
        return jsonify({"error":"Username already taken"}), 409
    db.execute("INSERT INTO users (username,email,password,role,full_name,institution,department,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (data["username"],data["email"],hash_password(data["password"]),
         data.get("role","teacher"),data["full_name"],
         data.get("institution",""),data.get("department",""),datetime.now().isoformat()))
    db.commit()
    user = db.execute("SELECT * FROM users WHERE email=?",(data["email"],)).fetchone()
    token = create_token(user["id"],user["username"],user["role"],user["institution"] or "")
    return jsonify({"success":True,"token":token,"user":{"username":user["username"],"full_name":user["full_name"],"role":user["role"],"institution":user["institution"]}})

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data.get("email") or not data.get("password"):
        return jsonify({"error":"Email and password required"}), 400
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?",(data["email"],)).fetchone()
    if not user or not check_password(data["password"],user["password"]):
        return jsonify({"error":"Invalid email or password"}), 401
    if not user["is_active"]:
        return jsonify({"error":"Account deactivated. Contact your administrator."}), 403
    db.execute("UPDATE users SET last_login=? WHERE id=?",(datetime.now().isoformat(),user["id"]))
    db.commit()
    token = create_token(user["id"],user["username"],user["role"],user["institution"] or "")
    return jsonify({"success":True,"token":token,"user":{
        "id":user["id"],"username":user["username"],
        "full_name":user["full_name"] or user["username"],
        "role":user["role"],"institution":user["institution"] or "",
        "department":user["department"] or ""}})

@app.route("/api/auth/student-register", methods=["POST"])
def student_register():
    data = request.get_json()
    for f in ["roll_number","email","password","full_name"]:
        if not data.get(f): return jsonify({"error":f"Missing: {f}"}), 400
    db = get_db()
    if db.execute("SELECT id FROM users WHERE username=?",(data["roll_number"],)).fetchone():
        return jsonify({"error":"Roll number already registered"}), 409
    if db.execute("SELECT id FROM users WHERE email=?",(data["email"],)).fetchone():
        return jsonify({"error":"Email already registered"}), 409
    db.execute("INSERT INTO users (username,email,password,role,full_name,institution,department,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (data["roll_number"],data["email"],hash_password(data["password"]),"student",
         data["full_name"],data.get("institution",""),data.get("department",""),datetime.now().isoformat()))
    db.commit()
    user = db.execute("SELECT * FROM users WHERE username=?",(data["roll_number"],)).fetchone()
    token = create_token(user["id"],user["username"],"student",user["institution"] or "")
    return jsonify({"success":True,"token":token,"user":{"username":user["username"],"full_name":user["full_name"],"role":"student"}})

@app.route("/api/auth/me")
@require_auth
def get_me():
    db = get_db()
    user = db.execute("SELECT id,username,email,role,full_name,institution,department,last_login FROM users WHERE id=?",
                      (request.user_id,)).fetchone()
    if not user: return jsonify({"error":"User not found"}), 404
    return jsonify(dict(user))

@app.route("/api/auth/change-password", methods=["POST"])
@require_auth
def change_password():
    data = request.get_json()
    if not data.get("current_password") or not data.get("new_password"):
        return jsonify({"error":"Both passwords required"}), 400
    if len(data["new_password"]) < 6:
        return jsonify({"error":"New password must be at least 6 characters"}), 400
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?",(request.user_id,)).fetchone()
    if not check_password(data["current_password"],user["password"]):
        return jsonify({"error":"Current password is incorrect"}), 401
    db.execute("UPDATE users SET password=? WHERE id=?",(hash_password(data["new_password"]),request.user_id))
    db.commit()
    return jsonify({"success":True,"message":"Password updated"})

# ── ADMIN ─────────────────────────────────────────────────────────────────────
@app.route("/api/admin/users")
@require_admin
def admin_list_users():
    db = get_db()
    rows = db.execute("SELECT id,username,email,role,full_name,institution,department,is_active,created_at,last_login FROM users ORDER BY created_at DESC").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/admin/users/<int:user_id>/toggle", methods=["POST"])
@require_admin
def admin_toggle_user(user_id):
    db   = get_db()
    user = db.execute("SELECT is_active FROM users WHERE id=?",(user_id,)).fetchone()
    if not user: return jsonify({"error":"Not found"}), 404
    new  = 0 if user["is_active"] else 1
    db.execute("UPDATE users SET is_active=? WHERE id=?",(new,user_id))
    db.commit()
    return jsonify({"success":True,"is_active":new})

@app.route("/api/admin/stats")
@require_admin
def admin_stats():
    db = get_db()
    return jsonify({
        "total_users":       db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "total_teachers":    db.execute("SELECT COUNT(*) FROM users WHERE role='teacher'").fetchone()[0],
        "total_students":    db.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
        "total_assignments": db.execute("SELECT COUNT(*) FROM assignments").fetchone()[0],
        "total_submissions": db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0],
        "pending_review":    db.execute("SELECT COUNT(*) FROM submissions WHERE teacher_approved=0 AND ai_marks IS NOT NULL").fetchone()[0],
    })

# ── TEACHER ───────────────────────────────────────────────────────────────────
@app.route("/api/teacher/create-assignment", methods=["POST"])
def create_assignment():
    data = request.get_json()
    for f in ["title","subject","max_marks","deadline","rubric","teacher_name"]:
        if not data.get(f): return jsonify({"error":f"Missing: {f}"}), 400
    teacher_id = None
    token = request.headers.get("Authorization","").replace("Bearer ","").strip()
    if token:
        try: teacher_id = decode_token(token)["user_id"]
        except: pass
    aid = str(uuid.uuid4())[:8].upper()
    db  = get_db()
    db.execute("INSERT INTO assignments (assignment_id,title,subject,max_marks,deadline,rubric,teacher_name,teacher_id,institution,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (aid,data["title"],data["subject"],data["max_marks"],data["deadline"],
         data["rubric"],data["teacher_name"],teacher_id,data.get("institution",""),datetime.now().isoformat()))
    db.commit()
    return jsonify({"success":True,"assignment_id":aid})

@app.route("/api/teacher/assignments/<teacher_name>")
def get_teacher_assignments(teacher_name):
    db   = get_db()
    rows = db.execute("""
        SELECT a.*, COUNT(s.id) as submission_count,
        SUM(CASE WHEN (s.teacher_approved=0 OR s.teacher_approved IS NULL) AND s.ai_marks IS NOT NULL THEN 1 ELSE 0 END) as pending_review
        FROM assignments a LEFT JOIN submissions s ON a.assignment_id=s.assignment_id
        WHERE a.teacher_name=? GROUP BY a.assignment_id ORDER BY a.created_at DESC
    """,(teacher_name,)).fetchall()
    result = []
    for a in rows:
        d = dict(a)
        d["is_expired"] = datetime.now() > datetime.fromisoformat(d["deadline"])
        result.append(d)
    return jsonify(result)

@app.route("/api/teacher/results/<assignment_id>")
def get_results(assignment_id):
    db   = get_db()
    a    = db.execute("SELECT * FROM assignments WHERE assignment_id=?",(assignment_id,)).fetchone()
    if not a: return jsonify({"error":"Not found"}), 404
    subs = db.execute("SELECT * FROM submissions WHERE assignment_id=? ORDER BY submitted_at DESC",(assignment_id,)).fetchall()
    real_max = dict(a).get("max_marks",100)
    result = []
    for s in subs:
        d = dict(s)
        try: d["ai_breakdown"] = json.loads(d["ai_breakdown"]) if d.get("ai_breakdown") else []
        except: d["ai_breakdown"] = []
        d["final_marks"] = d["teacher_marks"] if d.get("teacher_marks") is not None else d.get("ai_marks",0)
        d["max_marks"]   = real_max
        result.append(d)
    return jsonify({"assignment":dict(a),"submissions":result})

@app.route("/api/teacher/submission/<submission_id>")
def get_single_submission(submission_id):
    db  = get_db()
    row = db.execute("""SELECT s.*, a.title, a.subject, a.rubric, a.teacher_name, a.max_marks as assignment_max
        FROM submissions s JOIN assignments a ON s.assignment_id=a.assignment_id
        WHERE s.submission_id=?""",(submission_id,)).fetchone()
    if not row: return jsonify({"error":"Not found"}), 404
    d = dict(row)
    try: d["ai_breakdown"] = json.loads(d["ai_breakdown"]) if d.get("ai_breakdown") else []
    except: d["ai_breakdown"] = []
    d["final_marks"] = d["teacher_marks"] if d.get("teacher_marks") is not None else d.get("ai_marks",0)
    d["max_marks"]   = d.get("assignment_max") or d.get("max_marks") or 100
    return jsonify(d)

@app.route("/api/teacher/review/<submission_id>", methods=["POST"])
def teacher_review(submission_id):
    data   = request.get_json()
    action = data.get("action")
    db     = get_db()
    sub    = db.execute("SELECT * FROM submissions WHERE submission_id=?",(submission_id,)).fetchone()
    if not sub: return jsonify({"error":"Not found"}), 404
    sub = dict(sub)
    now = datetime.now().isoformat()
    if action == "approve":
        final = sub.get("ai_marks",0)
        db.execute("UPDATE submissions SET teacher_approved=1,final_marks=?,reviewed_at=? WHERE submission_id=?",(final,now,submission_id))
    elif action == "override":
        marks = data.get("marks")
        if marks is None: return jsonify({"error":"marks required"}), 400
        marks    = max(0,min(int(marks),sub.get("max_marks",100)))
        feedback = data.get("feedback","").strip()
        db.execute("UPDATE submissions SET teacher_marks=?,teacher_feedback=?,teacher_approved=2,final_marks=?,reviewed_at=? WHERE submission_id=?",(marks,feedback,marks,now,submission_id))
    else: return jsonify({"error":"Invalid action"}), 400
    db.commit()
    return jsonify({"success":True})

@app.route("/api/teacher/download-excel/<assignment_id>")
def download_excel(assignment_id):
    db   = get_db()
    a    = db.execute("SELECT * FROM assignments WHERE assignment_id=?",(assignment_id,)).fetchone()
    if not a: return jsonify({"error":"Not found"}), 404
    subs = db.execute("SELECT * FROM submissions WHERE assignment_id=?",(assignment_id,)).fetchall()
    rows = []
    for s in subs:
        d = dict(s)
        d["final_marks"] = d["teacher_marks"] if d.get("teacher_marks") is not None else d.get("ai_marks",0)
        d["max_marks"]   = dict(a).get("max_marks",d.get("max_marks",100))
        rows.append(d)
    fp = generate_excel(dict(a), rows)
    return send_file(fp, as_attachment=True, download_name=f"Results_{assignment_id}.xlsx")

@app.route("/api/teacher/view-pdf/<submission_id>")
def view_pdf(submission_id):
    db  = get_db()
    sub = db.execute("SELECT filename FROM submissions WHERE submission_id=?",(submission_id,)).fetchone()
    if not sub: return jsonify({"error":"Not found"}), 404
    return send_from_directory(UPLOAD_FOLDER, sub["filename"])

@app.route("/api/teacher/generate-rubric", methods=["POST"])
def generate_rubric():
    data      = request.get_json()
    questions = data.get("questions","").strip()
    subject   = data.get("subject","Fundamentals of Data Analysis").strip()
    max_marks = int(data.get("max_marks",25))
    sub_types = data.get("submission_types",["theory","code"])
    if not questions: return jsonify({"error":"Please paste assignment questions"}), 400
    from evaluator import _get_client, TEXT_MODEL
    try:
        client    = _get_client()
        type_note = "Students may submit handwritten theory AND code answers." if ("code" in sub_types and "theory" in sub_types) else ("Code-based answers." if "code" in sub_types else "Handwritten theory answers.")
        prompt = f"""You are an experienced university professor for {subject}.
Create a detailed, fair marking rubric for the following assignment questions.
SUBJECT: {subject}  TOTAL MARKS: {max_marks}  SUBMISSION TYPE: {type_note}
ASSIGNMENT QUESTIONS:\n{questions}
Generate a rubric that:
1. Distributes {max_marks} marks proportionally by difficulty
2. Breaks each question into specific sub-criteria
3. For code: marks for syntax, logic, output, explanation
4. For theory: marks for definition, completeness, examples, comparison
5. Enables partial marks. 6. Follows Bloom's Taxonomy
Respond in JSON only:
{{"questions":[{{"number":"Q1","title":"<topic>","total_marks":<int>,"type":"theory|code|mixed","bloom_level":"Remember|Understand|Apply|Analyse","criteria":[{{"name":"<criterion>","marks":<int>,"description":"<what to show>","partial_marks":"<what earns 50%>"}}]}}],"rubric_text":"<full rubric text>","evaluation_notes":"<AI evaluator instructions>"}}"""
        resp = client.chat.completions.create(model=TEXT_MODEL,temperature=0.2,max_tokens=3000,
            response_format={"type":"json_object"},
            messages=[{"role":"system","content":"Expert university professor. JSON only."},{"role":"user","content":prompt}])
        raw    = resp.choices[0].message.content.strip().replace("```json","").replace("```","").strip()
        result = json.loads(raw)
        rubric_text = result.get("rubric_text","")
        eval_notes  = result.get("evaluation_notes","")
        if eval_notes: rubric_text += f"\n\nEVALUATION NOTES FOR AI:\n{eval_notes}"
        return jsonify({"success":True,"questions":result.get("questions",[]),"rubric_text":rubric_text,"evaluation_notes":eval_notes})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error":f"Failed: {str(e)[:200]}"}), 500

@app.route("/api/teacher/rubric-templates", methods=["GET"])
def get_rubric_templates():
    db   = get_db()
    rows = db.execute("SELECT * FROM rubric_templates ORDER BY created_at DESC").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/teacher/rubric-templates", methods=["POST"])
def save_rubric_template():
    data = request.get_json()
    if not data.get("name") or not data.get("rubric_text"):
        return jsonify({"error":"Name and rubric_text required"}), 400
    teacher_id = None
    token = request.headers.get("Authorization","").replace("Bearer ","").strip()
    if token:
        try: teacher_id = decode_token(token)["user_id"]
        except: pass
    db = get_db()
    db.execute("INSERT INTO rubric_templates (name,subject,rubric_text,teacher_id,is_public,created_at) VALUES (?,?,?,?,?,?)",
        (data["name"],data.get("subject",""),data["rubric_text"],teacher_id,1 if data.get("is_public") else 0,datetime.now().isoformat()))
    db.commit()
    return jsonify({"success":True})

@app.route("/api/teacher/rubric-templates/<int:tid>", methods=["DELETE"])
def delete_rubric_template(tid):
    db = get_db()
    db.execute("DELETE FROM rubric_templates WHERE id=?",(tid,))
    db.commit()
    return jsonify({"success":True})

# ── STUDENT ───────────────────────────────────────────────────────────────────
@app.route("/api/assignment/<assignment_id>")
def get_assignment_info(assignment_id):
    db = get_db()
    a  = db.execute("SELECT assignment_id,title,subject,max_marks,deadline,teacher_name FROM assignments WHERE assignment_id=?",(assignment_id,)).fetchone()
    if not a: return jsonify({"error":"Assignment not found"}), 404
    d  = dict(a)
    dl = datetime.fromisoformat(d["deadline"])
    d["is_expired"] = datetime.now() > dl
    d["deadline_formatted"] = dl.strftime("%d %B %Y, %I:%M %p")
    return jsonify(d)

@app.route("/api/submit/<assignment_id>", methods=["POST"])
def submit_assignment(assignment_id):
    db = get_db()
    a  = db.execute("SELECT * FROM assignments WHERE assignment_id=?",(assignment_id,)).fetchone()
    if not a: return jsonify({"error":"Assignment not found"}), 404
    a  = dict(a)
    if datetime.now() > datetime.fromisoformat(a["deadline"]):
        return jsonify({"error":"Submission deadline has passed"}), 403
    name  = request.form.get("student_name","").strip()
    roll  = request.form.get("roll_number","").strip()
    email = request.form.get("email","").strip()
    if not name or not roll: return jsonify({"error":"Name and roll number required"}), 400
    if db.execute("SELECT id FROM submissions WHERE assignment_id=? AND roll_number=?",(assignment_id,roll)).fetchone():
        return jsonify({"error":"You have already submitted this assignment"}), 409
    if "file" not in request.files: return jsonify({"error":"No file uploaded"}), 400
    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"): return jsonify({"error":"Only PDF files accepted"}), 400
    fname = f"{assignment_id}_{roll}_{int(datetime.now().timestamp())}.pdf"
    fpath = os.path.join(UPLOAD_FOLDER, fname)
    file.save(fpath)
    text, has_images, page_count = _extract_pdf(fpath)
    clean_text = text.strip()
    words      = len(clean_text.split())
    if words >= 100:    stype = "typed"
    elif words >= 20 and has_images: stype = "mixed"
    else:               stype = "handwritten"
    print(f"[Submit] type={stype}, words={words}, images={has_images}, pages={page_count}")
    ev = evaluate_submission(text,a["rubric"],a["max_marks"],stype,file_path=fpath)
    sid = str(uuid.uuid4())[:8].upper()
    student_id = None
    sr = db.execute("SELECT id FROM users WHERE username=? AND role='student'",(roll,)).fetchone()
    if sr: student_id = sr["id"]
    db.execute("""INSERT INTO submissions
        (submission_id,assignment_id,student_name,roll_number,email,student_id,filename,
         submission_type,extracted_text,ai_marks,ai_feedback,ai_breakdown,
         final_marks,max_marks,needs_review,submitted_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sid,assignment_id,name,roll,email,student_id,fname,stype,
         text[:3000],ev["marks"],ev["feedback"],json.dumps(ev.get("breakdown",[])),
         ev["marks"],a["max_marks"],1 if ev["needs_review"] else 0,datetime.now().isoformat()))
    db.commit()
    return jsonify({"success":True,"submission_id":sid,"result_preview":{"marks":ev["marks"],"max_marks":a["max_marks"],"needs_review":ev["needs_review"]}})

@app.route("/api/student/result/<assignment_id>/<roll_number>")
def get_student_result(assignment_id, roll_number):
    db  = get_db()
    row = db.execute("""SELECT s.*, a.title, a.subject, a.teacher_name
        FROM submissions s JOIN assignments a ON s.assignment_id=a.assignment_id
        WHERE s.assignment_id=? AND s.roll_number=?""",(assignment_id,roll_number)).fetchone()
    if not row: return jsonify({"error":"No submission found for this roll number"}), 404
    d = dict(row)
    try: d["ai_breakdown"] = json.loads(d["ai_breakdown"]) if d.get("ai_breakdown") else []
    except: d["ai_breakdown"] = []
    d["final_marks"]      = d["teacher_marks"] if d.get("teacher_marks") is not None else d.get("ai_marks",0)
    d["max_marks"]        = d.get("max_marks") or 100
    d["display_feedback"] = d.get("teacher_feedback") or d.get("ai_feedback","")
    return jsonify(d)

@app.route("/api/student/my-submissions")
@require_auth
def my_submissions():
    db   = get_db()
    roll = request.username
    rows = db.execute("""SELECT s.submission_id,s.assignment_id,s.submitted_at,
        s.final_marks,s.max_marks,s.teacher_approved,s.needs_review,s.submission_type,
        a.title,a.subject,a.teacher_name
        FROM submissions s JOIN assignments a ON s.assignment_id=a.assignment_id
        WHERE s.roll_number=? ORDER BY s.submitted_at DESC""",(roll,)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["final_marks"] = d.get("final_marks") or 0
        result.append(d)
    return jsonify(result)

# ── HELPERS ───────────────────────────────────────────────────────────────────
def _extract_pdf(filepath):
    try:
        doc = fitz.open(filepath)
        text, has_images = "", False
        for page in doc:
            text += page.get_text() + "\n"
            if page.get_images(): has_images = True
        n = len(doc); doc.close()
        return text, has_images, n
    except Exception as e:
        print(f"[PDF] {e}"); return "", False, 0

def _backup_database():
    try:
        backup_dir = os.path.join(os.path.dirname(__file__),"backups")
        os.makedirs(backup_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        src = os.path.join(os.path.dirname(__file__),"evaluator.db")
        dst = os.path.join(backup_dir,f"evaluator_{date_str}.db")
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src,dst)
            print(f"✅ DB backed up → backups/evaluator_{date_str}.db")
        backups = sorted([f for f in os.listdir(backup_dir) if f.endswith(".db")])
        for old in backups[:-30]: os.remove(os.path.join(backup_dir,old))
    except Exception as e: print(f"[Backup] {e}")

# ── START ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    _backup_database()
    print("="*50)
    print("🚀  AssignEval → http://localhost:5000")
    print("    Login page → http://localhost:5000/pages/login.html")
    print("="*50)
    app.run(debug=True, port=5000, host="0.0.0.0")
