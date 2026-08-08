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
