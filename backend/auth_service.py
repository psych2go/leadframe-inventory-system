import os
import time
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

import httpx
import jwt

logger = logging.getLogger(__name__)

# JWT 配置
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

# 企微配置
WECORP_ID = os.getenv("WECORP_ID", "")
WECORP_SECRET = os.getenv("WECORP_SECRET", "")
WECORP_AGENT_ID = os.getenv("WECORP_AGENT_ID", "")

# access_token 缓存
_token_cache = {"token": None, "expires_at": 0}

# jsapi_ticket 缓存
_jsapi_ticket_cache = {"ticket": None, "expires_at": 0}


def is_wecom_configured() -> bool:
    return bool(WECORP_ID and WECORP_SECRET)


def create_jwt(user_id: str, name: str = "") -> str:
    if not JWT_SECRET:
        raise ValueError("JWT_SECRET 未配置，无法签发 Token")
    payload = {
        "user_id": user_id,
        "name": name,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_access_token() -> str | None:
    """获取企微 access_token，带缓存（提前 300 秒刷新）"""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 300:
        return _token_cache["token"]

    url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
    params = {"corpid": WECORP_ID, "corpsecret": WECORP_SECRET}
    try:
        resp = httpx.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("errcode") != 0:
            logger.error("获取 access_token 失败: %s", data)
            return None
        _token_cache["token"] = data["access_token"]
        _token_cache["expires_at"] = now + data.get("expires_in", 7200)
        return data["access_token"]
    except Exception as e:
        logger.error("获取 access_token 异常: %s", e)
        return None


def get_user_info(code: str) -> dict | None:
    """用 code 换取用户身份（userid）"""
    token = get_access_token()
    if not token:
        return None

    url = "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo"
    params = {"access_token": token, "code": code}
    try:
        resp = httpx.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("errcode") != 0:
            logger.error("获取用户信息失败: %s", data)
            return None
        return data
    except Exception as e:
        logger.error("获取用户信息异常: %s", e)
        return None


def get_user_detail(user_ticket: str) -> dict | None:
    """通过 user_ticket 获取用户详细信息（姓名等）"""
    token = get_access_token()
    if not token:
        return None

    url = "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserdetail"
    params = {"access_token": token}
    body = {"user_ticket": user_ticket}
    try:
        resp = httpx.post(url, params=params, json=body, timeout=10)
        data = resp.json()
        if data.get("errcode") != 0:
            logger.error("获取用户详情失败: %s", data)
            return None
        return data
    except Exception as e:
        logger.error("获取用户详情异常: %s", e)
        return None


def get_jsapi_ticket() -> str | None:
    """获取企微 jsapi_ticket，带缓存"""
    now = time.time()
    if _jsapi_ticket_cache["ticket"] and _jsapi_ticket_cache["expires_at"] > now + 300:
        return _jsapi_ticket_cache["ticket"]

    token = get_access_token()
    if not token:
        return None

    url = "https://qyapi.weixin.qq.com/cgi-bin/get_jsapi_ticket"
    params = {"access_token": token}
    try:
        resp = httpx.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("errcode") != 0:
            logger.error("获取 jsapi_ticket 失败: %s", data)
            return None
        _jsapi_ticket_cache["ticket"] = data["ticket"]
        _jsapi_ticket_cache["expires_at"] = now + data.get("expires_in", 7200)
        return data["ticket"]
    except Exception as e:
        logger.error("获取 jsapi_ticket 异常: %s", e)
        return None


def generate_jsapi_signature(url: str) -> dict | None:
    """生成企微 JS-SDK 签名配置"""
    ticket = get_jsapi_ticket()
    if not ticket:
        return None

    nonce_str = secrets.token_hex(8)
    timestamp = str(int(time.time()))

    # 签名算法：SHA1(sort(jsapi_ticket, noncestr, timestamp, url))
    raw = f"jsapi_ticket={ticket}&noncestr={nonce_str}&timestamp={timestamp}&url={url}"
    signature = hashlib.sha1(raw.encode()).hexdigest()

    return {
        "appId": WECORP_ID,
        "timestamp": timestamp,
        "nonceStr": nonce_str,
        "signature": signature,
    }
