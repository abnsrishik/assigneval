"""
auth.py — Authentication helpers for AssignEval
Handles: password hashing, JWT tokens, route protection
"""
import bcrypt, jwt, os
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify

# ── Secret key — change this in production! ──────────────────────────────────
SECRET_KEY = os.environ.get("JWT_SECRET", "assigneval-secret-change-in-production-2026")
TOKEN_EXPIRY_DAYS = 7


# ── Password helpers ──────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=10)).decode()

def check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ── JWT helpers ───────────────────────────────────────────────────────────────
def create_token(user_id: int, username: str, role: str, institution: str = "") -> str:
    payload = {
        "user_id":    user_id,
        "username":   username,
        "role":       role,
        "institution": institution,
        "exp":        datetime.utcnow() + timedelta(days=TOKEN_EXPIRY_DAYS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])


# ── Route decorators ──────────────────────────────────────────────────────────
def require_auth(f):
    """Protect any route — requires valid JWT token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify({"error": "Login required", "code": "NO_TOKEN"}), 401
        try:
            payload = decode_token(token)
            request.user_id       = payload["user_id"]
            request.user_role     = payload["role"]
            request.username      = payload["username"]
            request.institution   = payload.get("institution", "")
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Session expired. Please log in again.", "code": "EXPIRED"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid session. Please log in again.", "code": "INVALID"}), 401
        return f(*args, **kwargs)
    return decorated

def require_teacher(f):
    """Only teachers and admins can access."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify({"error": "Login required", "code": "NO_TOKEN"}), 401
        try:
            payload = decode_token(token)
            if payload["role"] not in ("teacher", "admin"):
                return jsonify({"error": "Teacher access required", "code": "FORBIDDEN"}), 403
            request.user_id     = payload["user_id"]
            request.user_role   = payload["role"]
            request.username    = payload["username"]
            request.institution = payload.get("institution", "")
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Session expired. Please log in again.", "code": "EXPIRED"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid session.", "code": "INVALID"}), 401
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    """Only admins can access."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify({"error": "Login required"}), 401
        try:
            payload = decode_token(token)
            if payload["role"] != "admin":
                return jsonify({"error": "Admin access required"}), 403
            request.user_id   = payload["user_id"]
            request.user_role = payload["role"]
            request.username  = payload["username"]
        except Exception:
            return jsonify({"error": "Invalid session"}), 401
        return f(*args, **kwargs)
    return decorated

def _extract_token() -> str:
    """Pull token from Authorization header OR cookie."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return request.cookies.get("ae_token", "")
