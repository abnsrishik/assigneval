# Assignment Evaluator
### AI-Powered Assignment Evaluation — SRM Ramapuram, 1st Year AI Mini Project

---

## HOW TO RUN (Read this carefully — 3 steps only)

### Step 1 — Install Python packages (do this ONCE)
Open PowerShell or Command Prompt inside the `backend` folder and run:
```
pip install flask flask-cors groq PyMuPDF openpyxl
```

### Step 2 — Paste your Groq API key
Open `backend/evaluator.py` in any text editor.
Find line 14 and paste your key:
```python
GROQ_API_KEY = "gsk_your_key_here"
```
Get free key from: https://console.groq.com (just Google login, no card)

### Step 3 — Run the server
Inside the `backend` folder, run:
```
python app.py
```

### Step 4 — Open in browser
Go to: http://localhost:5000

---

## IMPORTANT — Always open via http://localhost:5000
NEVER open HTML files by double-clicking them.
Always go to http://localhost:5000 in your browser AFTER running python app.py

---

## Pages
- Home:              http://localhost:5000
- Teacher Dashboard: http://localhost:5000/pages/teacher.html
- Submit Assignment: http://localhost:5000/pages/submit.html?assignment_id=XXXXXXXX
- View Results:      http://localhost:5000/pages/results.html?assignment_id=XXXXXXXX
- Check My Result:   http://localhost:5000/pages/result.html

---

## Project Structure
```
assignment-evaluator/
├── backend/
│   ├── app.py              ← Run this to start the server
│   ├── database.py         ← SQLite database setup
│   ├── evaluator.py        ← AI evaluation using Groq (PASTE KEY HERE)
│   ├── excel_generator.py  ← Excel results sheet
│   ├── requirements.txt    ← Python packages
│   └── uploads/            ← Student PDFs saved here (auto-created)
├── frontend/
│   ├── index.html          ← Home page
│   └── pages/
│       ├── teacher.html    ← Teacher dashboard
│       ├── submit.html     ← Student submission page
│       ├── results.html    ← Teacher results viewer
│       └── result.html     ← Student result checker
└── README.md
```

---

Built by Rishik's Team — SRM Ramapuram — 2026
#
