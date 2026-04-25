#!/bin/bash
# 本地开发一键启动脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

echo "=== 引线框架库存管理系统 - 本地开发启动 ==="
echo ""

# 停止已有进程
echo "清理已有进程..."
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
sleep 1

# 检查后端虚拟环境
if [ ! -d "$BACKEND_DIR/venv" ]; then
    echo "❌ 后端虚拟环境不存在，正在创建..."
    python3 -m venv "$BACKEND_DIR/venv"
    "$BACKEND_DIR/venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
    echo "✅ 后端虚拟环境创建完成"
fi

# 检查前端依赖
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "❌ 前端依赖未安装，正在安装..."
    cd "$FRONTEND_DIR"
    npm install
    cd "$SCRIPT_DIR"
    echo "✅ 前端依赖安装完成"
fi

# 创建日志目录
mkdir -p "$SCRIPT_DIR/logs"

echo ""
echo "启动后端服务..."
cd "$BACKEND_DIR"
# 从 backend/.env 加载 OCR 凭据（文件已 gitignore）
set -a && [ -f "$BACKEND_DIR/.env" ] && source "$BACKEND_DIR/.env" && set +a
export AUTH_REQUIRED=false
nohup ./venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload > "$SCRIPT_DIR/logs/backend.log" 2>&1 &
BACKEND_PID=$!
echo "后端 PID: $BACKEND_PID"

sleep 3

# 验证后端启动
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "✅ 后端启动成功"
else
    echo "⚠️  后端可能未正常启动，请检查日志"
fi

echo ""
echo "启动前端服务..."
cd "$FRONTEND_DIR"
nohup npm run dev > "$SCRIPT_DIR/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "前端 PID: $FRONTEND_PID"

sleep 3

# 保存 PID
echo "$BACKEND_PID" > "$SCRIPT_DIR/logs/backend.pid"
echo "$FRONTEND_PID" > "$SCRIPT_DIR/logs/frontend.pid"

# 获取 WSL IP
WSL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$WSL_IP" ]; then
    WSL_IP=$(ip addr 2>/dev/null | grep "inet " | grep -v "127.0.0.1" | head -1 | awk '{print $2}' | cut -d/ -f1)
fi

echo ""
echo "=== ✅ 服务启动完成！ ==="
echo ""
echo "📱 前端地址:"
echo "   - http://localhost:5173"
if [ -n "$WSL_IP" ]; then
    echo "   - http://$WSL_IP:5173"
fi
echo ""
echo "🔧 后端地址:"
echo "   - http://localhost:8000"
echo "   - API 文档: http://localhost:8000/docs"
echo ""
echo "日志文件:"
echo "  - 后端: $SCRIPT_DIR/logs/backend.log"
echo "  - 前端: $SCRIPT_DIR/logs/frontend.log"
echo ""
echo "停止服务:"
echo "  - 运行: ./dev-stop.sh"
echo ""
echo "=== WSL2 网络提示 ==="
echo "如果在 Windows 中无法访问，尝试以下方法："
echo "1. 在 Windows PowerShell (管理员) 中运行："
echo "   netsh interface portproxy add v4tov4 listenport=5173 listenaddress=0.0.0.0 connectport=5173 connectaddress=$WSL_IP"
echo "   netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=$WSL_IP"
echo ""
echo "2. 或者使用 Windows 防火墙入站规则允许端口 5173 和 8000"
echo ""
