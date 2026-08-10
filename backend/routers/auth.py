import os
import urllib.parse
import jwt
import secrets
import threading
import time
import ipaddress
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
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

LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "")
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_FAILURES = 5
_login_failures = defaultdict(deque)
_login_lock = threading.Lock()
OAUTH_STATE_COOKIE = "wecom_oauth_nonce"


def get_auth_url(redirect_uri: str, state: str) -> str:
    """生成企微网页授权链接"""
    encoded_uri = urllib.parse.quote(redirect_uri, safe="")
    return (
        f"https://open.weixin.qq.com/connect/oauth2/authorize"
        f"?appid={WECORP_ID}&redirect_uri={encoded_uri}"
        f"&response_type=code&scope=snsapi_base&state={urllib.parse.quote(state, safe='')}"
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
    state: str


class PasswordLoginRequest(BaseModel):
    password: str


def get_client_ip(request: Request) -> str:
    candidates = [
        request.headers.get("x-real-ip", ""),
        request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip(),
        request.client.host if request.client else "",
    ]
    for candidate in candidates:
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return "unknown"


def _check_login_rate_limit(ip: str) -> None:
    now = time.monotonic()
    with _login_lock:
        failures = _login_failures[ip]
        while failures and failures[0] <= now - LOGIN_WINDOW_SECONDS:
            failures.popleft()
        if len(failures) >= LOGIN_MAX_FAILURES:
            raise HTTPException(429, "登录失败次数过多，请稍后重试")


def _record_login_failure(ip: str) -> None:
    with _login_lock:
        _login_failures[ip].append(time.monotonic())


def _clear_login_failures(ip: str) -> None:
    with _login_lock:
        _login_failures.pop(ip, None)


def _safe_next_path(value: str) -> str:
    parsed = urlsplit(value or "/")
    if parsed.scheme or parsed.netloc or "\\" in value or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return "/"
    path = parsed.path or "/"
    return path + (f"?{parsed.query}" if parsed.query else "")


def _oauth_cookie_path() -> str:
    path = urlsplit(os.getenv("APP_BASE_URL", "")).path.rstrip("/")
    return path or "/"


def _create_oauth_state(next_path: str, nonce: str) -> str:
    payload = {
        "purpose": "wecom-oauth-state",
        "nonce": nonce,
        "next": _safe_next_path(next_path),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _validate_oauth_state(state: str, request: Request) -> dict:
    nonce = request.cookies.get(OAUTH_STATE_COOKIE, "")
    if not nonce:
        raise HTTPException(400, "OAuth state cookie 已失效")
    try:
        payload = jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(400, "OAuth state 无效")
    if payload.get("purpose") != "wecom-oauth-state":
        raise HTTPException(400, "OAuth state 类型无效")
    if not secrets.compare_digest(str(payload.get("nonce", "")), nonce):
        raise HTTPException(400, "OAuth state 不匹配")
    payload["next"] = _safe_next_path(str(payload.get("next", "/")))
    return payload


@router.post("/auth/login")
def password_login(req: PasswordLoginRequest, request: Request):
    """密码登录：验证共享密码，签发统一 24 小时 JWT。"""
    if not LOGIN_PASSWORD:
        raise HTTPException(400, "未配置登录密码，请设置 LOGIN_PASSWORD 环境变量")
    ip = get_client_ip(request)
    _check_login_rate_limit(ip)
    if not secrets.compare_digest(req.password, LOGIN_PASSWORD):
        _record_login_failure(ip)
        raise HTTPException(401, "密码错误")
    _clear_login_failures(ip)
    token = create_jwt("user", "用户")
    return {"token": token, "user_id": "user", "name": "用户"}


@router.get("/auth/wecom/url")
def auth_url(response: Response, redirect: str = Query("/", description="授权后回调的前端路径")):
    """生成企微 OAuth 授权链接，前端跳转此 URL 开始授权"""
    if not is_wecom_configured():
        raise HTTPException(400, "企微未配置，请设置 WECORP_ID 和 WECORP_SECRET")
    base = os.getenv("APP_BASE_URL", "")
    if not base:
        raise HTTPException(500, "未配置 APP_BASE_URL 环境变量")
    nonce = secrets.token_urlsafe(24)
    state = _create_oauth_state(redirect, nonce)
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        nonce,
        max_age=600,
        httponly=True,
        secure=urlsplit(base).scheme == "https",
        samesite="lax",
        path=_oauth_cookie_path(),
    )
    cb = f"{base.rstrip('/')}/api/auth/wecom/callback"
    url = get_auth_url(cb, state)
    return {"url": url}


@router.get("/auth/wecom/callback")
def wecom_callback(request: Request, code: str = Query(...), state: str = Query(...)):
    """企微 OAuth 回调：校验 state 后把一次性 code 转交前端交换 JWT。"""
    if not is_wecom_configured():
        raise HTTPException(400, "企微未配置")
    payload = _validate_oauth_state(state, request)
    base = os.getenv("APP_BASE_URL", "")
    separator = "&" if "?" in payload["next"] else "?"
    frontend_url = (
        f"{base.rstrip('/')}{payload['next']}{separator}"
        f"code={urllib.parse.quote(code, safe='')}&state={urllib.parse.quote(state, safe='')}"
    )
    return RedirectResponse(url=frontend_url)


@router.post("/auth/wecom/login")
def wecom_login(req: LoginRequest, request: Request, response: Response):
    """前端用 code 换 JWT（不走重定向的方式，适用于前端直接拿到 code 的场景）"""
    if not is_wecom_configured():
        raise HTTPException(400, "企微未配置")

    _validate_oauth_state(req.state, request)
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
    response.delete_cookie(OAUTH_STATE_COOKIE, path=_oauth_cookie_path())
    return {"token": token, "user_id": user_id, "name": name}


@router.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return {"user_id": user["user_id"], "name": user.get("name", "")}


@router.get("/auth/wecom/jsapi-config")
def jsapi_config(
    url: str = Query(..., description="当前页面 URL"),
    user: dict = Depends(get_current_user),
):
    """返回企微 JS-SDK 签名配置"""
    if not is_wecom_configured():
        raise HTTPException(400, "企微未配置")
    config = generate_jsapi_signature(url)
    if not config:
        raise HTTPException(500, "生成 JS-SDK 签名失败")
    return config
