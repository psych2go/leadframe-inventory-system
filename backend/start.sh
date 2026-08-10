#!/bin/bash
# 加载根目录认证配置和 backend/.env OCR 凭据
set -a
[ -f "$(dirname "$0")/../.env" ] && source "$(dirname "$0")/../.env"
[ -f "$(dirname "$0")/.env" ] && source "$(dirname "$0")/.env"
set +a
exec "$(dirname "$0")/venv/bin/python" -m uvicorn main:app --host 0.0.0.0 --port 8000
