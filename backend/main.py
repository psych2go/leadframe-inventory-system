import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import ocr, inventory, auth

# 日志同时输出到控制台和文件
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(log_dir, "app.log"), encoding="utf-8"),
    ],
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app):
    init_db()
    logging.info("Database initialized")
    yield


app = FastAPI(title="引线框架库存管理系统", version="1.0.0", lifespan=lifespan)

# CORS: 生产环境通过 Nginx 同源代理，不走 CORS；开发环境允许 localhost
cors_origins = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ocr.router, prefix="/api", tags=["OCR"])
app.include_router(inventory.router, prefix="/api", tags=["库存管理"])
app.include_router(auth.router, prefix="/api", tags=["认证"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


import auth_service


@app.get("/api/config")
def config():
    """返回前端需要的配置，让前端知道是否启用企微认证"""
    return {
        "wecom_configured": auth_service.is_wecom_configured(),
        "auth_required": os.getenv("AUTH_REQUIRED", "false").lower() == "true",
        "password_login": bool(os.getenv("LOGIN_PASSWORD", "")),
    }
