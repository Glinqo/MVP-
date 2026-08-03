"""用户认证 - 预置1000个账号 (000-999, 密码123456)"""
import hashlib, json, logging, os, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import sqlite3
import jwt

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "users.db"
JWT_SECRET = os.environ.get("JWT_SECRET", "mvp-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 7

def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.execute("PRAGMA journal_mode=WAL")
    c.row_factory = sqlite3.Row
    return c

def _ensure_tables():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                nickname TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'student',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.commit()
_ensure_tables()

def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 100000)
    return salt.hex() + ":" + dk.hex()

def verify_password(pw: str, pwd_hash: str) -> bool:
    salt_hex, dk_hex = pwd_hash.split(":")
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), 100000)
    return dk.hex() == dk_hex

def create_token(user: Dict[str, Any]) -> str:
    return jwt.encode({
        "user_id": user["id"], "username": user["username"],
        "role": user["role"], "nickname": user["nickname"],
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
        "iat": datetime.now(timezone.utc),
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(token: str) -> Optional[Dict]:
    try: return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError: return None

def login(username: str, password: str) -> Dict[str, Any]:
    with _conn() as conn:
        row = conn.execute("SELECT id, username, password_hash, nickname, role, identity, job_role FROM users WHERE username = ?", (username,)).fetchone()
    if not row: return {"ok": False, "error": "用户不存在"}
    if not verify_password(password, row["password_hash"]): return {"ok": False, "error": "密码错误"}
    user = {"id": row["id"], "username": row["username"], "nickname": row["nickname"], "role": row["role"],
            "identity": row["identity"] or "", "job_role": row["job_role"] or ""}


def save_identity(username: str, identity: str, job_role: str) -> Dict[str, Any]:
    with _conn() as conn:
        conn.execute("UPDATE users SET identity = ?, job_role = ?, updated_at = ? WHERE username = ?",
                     (identity, job_role, time.time(), username))
        conn.commit()
        row = conn.execute("SELECT id, username, nickname, role, identity, job_role FROM users WHERE username = ?", (username,)).fetchone()
    user = {"id": row["id"], "username": row["username"], "nickname": row["nickname"], "role": row["role"],
            "identity": row["identity"] or "", "job_role": row["job_role"] or ""}
    return {"ok": True, "user": user}
def get_user(user_id: int) -> Optional[Dict]:
    with _conn() as conn:
        row = conn.execute("SELECT id, username, nickname, role FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None

def list_users() -> list:
    with _conn() as conn:
        return [dict(r) for r in conn.execute("SELECT id, username, nickname, role FROM users ORDER BY id").fetchall()]