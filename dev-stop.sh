#!/bin/bash
# 停止本地开发服务

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_DIR="$SCRIPT_DIR/logs"

if [ -f "$PID_DIR/backend.pid" ]; then
    BACKEND_PID=$(cat "$PID_DIR/backend.pid")
    kill $BACKEND_PID 2>/dev/null && echo "✅ 后端已停止 (PID: $BACKEND_PID)" || echo "⚠️  后端进程未运行"
    rm -f "$PID_DIR/backend.pid"
fi

if [ -f "$PID_DIR/frontend.pid" ]; then
    FRONTEND_PID=$(cat "$PID_DIR/frontend.pid")
    kill $FRONTEND_PID 2>/dev/null && echo "✅ 前端已停止 (PID: $FRONTEND_PID)" || echo "⚠️  前端进程未运行"
    rm -f "$PID_DIR/frontend.pid"
fi

# 清理可能残留的 uvicorn 进程
pkill -f "uvicorn main:app" 2>/dev/null && echo "✅ 清理残留 uvicorn 进程" || true

echo "所有服务已停止"
