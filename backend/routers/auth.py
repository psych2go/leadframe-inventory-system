import os
import urllib.parse
import jwt
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from auth_service import (
    is_wecom_configured,
    create_jwt,
    decode_jwt,
    get_user_info,
    get_user_detail,
    generate_jsapi_signature,
    JWT_SECRET,
    JWT_ALGORITHM,
    WECORP_ID,
    WECORP_AGENT_ID,
)

router = APIRouter()

AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
APP_PASSWORD = os.getenv("APP_PASSWORD", "")


def get_auth_url(redirect_uri: str) -> str:
    """生成企微网页授权链接"""
    encoded_uri = urllib.parse.quote(redirect_uri, safe="")
    return (
        f"https://open.weixin.qq.com/connect/oauth2/authorize"
        f"?appid={WECORP_ID}&redirect_uri={encoded_uri}"
        f"&response_type=code&scope=snsapi_base&state=wecom"
        f"&agentid={WECORP_AGENT_ID}"
        f"#wechat_redirect"
    )


# ── FastAPI 依赖：可选/强制鉴权 ──

def get_current_user_optional(request: Request) -> dict | None:
    """从请求中提取 JWT 用户信息（可选，无 token 返回 None）"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        payload = decode_jwt(auth[7:])
        if payload:
            return payload
    return None


def get_current_user(request: Request) -> dict:
    """强制鉴权依赖，未登录返回 401"""
    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(401, "未登录或登录已过期")
    return user


# ── 路由 ──

class LoginRequest(BaseModel):
    code: str


class PasswordLoginRequest(BaseModel):
    password: str


@router.post("/auth/login")
def password_login(req: PasswordLoginRequest):
    """密码登录：验证共享密码，签发 JWT（30 天有效）"""
    if not APP_PASSWORD:
        raise HTTPException(400, "未配置登录密码，请设置 APP_PASSWORD 环境变量")
    if req.password != APP_PASSWORD:
        raise HTTPException(401, "密码错误")
    token = create_jwt("user", "用户")
    # 密码登录签发 30 天有效的 JWT
    payload = {
        "user_id": "user",
        "name": "用户",
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"token": token, "user_id": "user", "name": "用户"}


@router.get("/auth/wecom/url")
def auth_url(redirect: str = Query("/", description="授权后回调的前端路径")):
    """生成企微 OAuth 授权链接，前端跳转此 URL 开始授权"""
    if not is_wecom_configured():
        raise HTTPException(400, "企微未配置，请设置 WECORP_ID 和 WECORP_SECRET")
    # redirect_uri 指向后端 callback，同时把前端目标路径带上
    base = os.getenv("APP_BASE_URL", "")
    if not base:
        raise HTTPException(500, "未配置 APP_BASE_URL 环境变量")
    cb = f"{base.rstrip('/')}/api/auth/wecom/callback?next={urllib.parse.quote(redirect)}"
    url = get_auth_url(cb)
    return {"url": url}


@router.get("/auth/wecom/callback")
def wecom_callback(code: str = Query(...), next: str = Query("/")):
    """企微 OAuth 回调：用 code 换取用户身份 → 签发 JWT → 重定向回前端"""
    if not is_wecom_configured():
        raise HTTPException(400, "企微未配置")

    info = get_user_info(code)
    if not info or "userid" not in info:
        raise HTTPException(400, f"企微授权失败: {info}")

    user_id = info["userid"]
    name = user_id

    # 尝试获取用户姓名
    user_ticket = info.get("user_ticket")
    if user_ticket:
        detail = get_user_detail(user_ticket)
        if detail:
            name = detail.get("name", user_id)

    token = create_jwt(user_id, name)

    base = os.getenv("APP_BASE_URL", "")
    frontend_url = f"{base.rstrip('/')}{next}?token={token}&name={urllib.parse.quote(name)}"
    return RedirectResponse(url=frontend_url)


@router.post("/auth/wecom/login")
def wecom_login(req: LoginRequest):
    """前端用 code 换 JWT（不走重定向的方式，适用于前端直接拿到 code 的场景）"""
    if not is_wecom_configured():
        raise HTTPException(400, "企微未配置")

    info = get_user_info(req.code)
    if not info or "userid" not in info:
        raise HTTPException(400, f"企微授权失败: {info}")

    user_id = info["userid"]
    name = user_id

    user_ticket = info.get("user_ticket")
    if user_ticket:
        detail = get_user_detail(user_ticket)
        if detail:
            name = detail.get("name", user_id)

    token = create_jwt(user_id, name)
    return {"token": token, "user_id": user_id, "name": name}


@router.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return {"user_id": user["user_id"], "name": user.get("name", "")}


@router.get("/auth/wecom/jsapi-config")
def jsapi_config(url: str = Query(..., description="当前页面 URL")):
    """返回企微 JS-SDK 签名配置"""
    if not is_wecom_configured():
        raise HTTPException(400, "企微未配置")
    config = generate_jsapi_signature(url)
    if not config:
        raise HTTPException(500, "生成 JS-SDK 签名失败")
    return config
