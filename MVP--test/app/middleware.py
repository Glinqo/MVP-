"""JWT 鉴权中间件"""
from app.services.auth import verify_token

def find_authed_user(handler):
    """从请求头提取 JWT 并返回用户信息，无有效 token 返回 None"""
    auth = handler.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    payload = verify_token(token)
    if not payload:
        return None
    return {"id": payload["user_id"], "username": payload["username"], "role": payload["role"]}

def verify_student_ownership(handler):
    """Verify JWT user owns the requested session_id; returns (user, error_tuple_or_None)."""
    user = find_authed_user(handler)
    if not user:
        return None, (401, "请先登录")
    # Parse body to get session_id
    try:
        import json
        length = int(handler.headers.get("Content-Length", 0))
        body = json.loads(handler.rfile.read(length)) if length > 0 else {}
    except:
        body = {}
    # Use query param or body param for session_id
    sid = body.get("session_id", "")
    # Teacher can access any student data
    if user.get("role") == "teacher":
        return user, (None, None)
    # Student: verify session_id contains their username
    if user.get("role") == "student" and sid:
        if user.get("username") not in sid:
            return None, (403, "无权访问其他学生的数据")
    return user, (None, None)

def require_student_owner(user: dict, requested_student_id: str = None, requested_session_id: str = None) -> bool:
    """Student must only access their own resources. Teacher can access via Teacher API."""
    if not user:
        return False
    role = user.get("role", "")
    username = user.get("username", "")
    # Teacher: not allowed through student private API; must use /api/teacher/*
    if role == "teacher":
        return False
    # Student self: ok
    if requested_student_id and requested_student_id == username:
        return True
    # Session-based: session_id format should contain student identifier
    if requested_session_id:
        try:
            from app.services.class_management import session_id_belongs_to_student
            if session_id_belongs_to_student(requested_session_id, username):
                return True
        except Exception:
            pass
        parts = requested_session_id.split("-")
        for p in parts:
            if p == username:
                return True
        if requested_session_id.startswith(username + "-") or ("-" + username + "-") in requested_session_id:
            return True
    # Default: student only accesses self
    if not requested_student_id and not requested_session_id:
        return True  # General access (no specific resource requested)
    return False
