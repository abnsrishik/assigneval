#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Assignment Evaluator - One-Click Setup Script
# SRM Ramapuram | Rishik's Team | AI Mini Project
# ═══════════════════════════════════════════════════════════════
# Usage: bash setup.sh

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║    ASSIGNMENT EVALUATOR - Setup & Run           ║"
echo "║    SRM Ramapuram · AI Mini Project              ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Check Python ─────────────────────────────────────
echo "→ Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install from https://python.org"
    exit 1
fi
echo "✅ Python $(python3 --version | awk '{print $2}') found"

# ── Step 2: Install dependencies ─────────────────────────────
echo ""
echo "→ Installing Python packages..."
cd backend
pip install -r requirements.txt --quiet
echo "✅ Packages installed"

# ── Step 3: Check API key ─────────────────────────────────────
echo ""
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "⚠️  ANTHROPIC_API_KEY is not set."
    echo "   The app will run in DEMO MODE (no real AI evaluation)."
    echo "   To enable AI: export ANTHROPIC_API_KEY='your-key-here'"
    echo "   Get your key from: https://console.anthropic.com"
else
    echo "✅ ANTHROPIC_API_KEY found"
fi

# ── Step 4: Initialize database ──────────────────────────────
echo ""
echo "→ Initializing database..."
python3 -c "from database import init_db; init_db()"
echo "✅ Database ready"

# ── Step 5: Start server ──────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  🚀 Starting server...                          ║"
echo "║                                                  ║"
echo "║  Open in browser:                               ║"
echo "║  → http://localhost:5000                        ║"
echo "║  → Teacher: /pages/teacher.html                ║"
echo "║  → Submit:  /pages/submit.html?assignment_id=  ║"
echo "║  → Results: /pages/results.html?assignment_id= ║"
echo "║                                                  ║"
echo "║  Press Ctrl+C to stop                          ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

python3 app.py
