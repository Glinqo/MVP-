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
