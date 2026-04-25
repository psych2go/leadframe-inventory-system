# 引线框架库存管理系统

面向半导体引线框架（Leadframe）仓库的移动端库存管理工具。拍照即可通过 OCR 自动识别标签上的规格、批号、厂家等信息，完成入库/出库操作。设计为企业微信自建 H5 应用，适合 1-5 人小团队使用。

## 功能

- **拍照入库** — 手机拍照上传，PaddleOCR-VL-1.5 自动识别标签文字，提取规格、生产厂家、批号、数量、生产日期、过期日期，确认后入库
- **拍照出库** — 拍照识别批号后自动匹配库存记录，选择后出库
- **手动入库** — 直接填写表单入库
- **出库操作** — 搜索库存，输入出库数量，库存自动扣减
- **库存查询** — 搜索、分页浏览所有库存记录
- **库存导出** — 一键导出 Excel 文件
- **出入库记录** — 完整的出入库日志
- **操作审计** — 所有数据变更自动记录（谁在什么时间做了什么操作）
- **库存预警** — 数量低于 2K 自动预警提示
- **物料编码建议** — 根据厂家规格自动建议历史物料编码

### 入库规则

以 **物料编码 + 批号** 为唯一标识。入库时如果已有相同物料编码+批号的记录，数量自动累加；否则新建记录。所有数量以 K（千）为单位，最多 3 位小数。

### 企微集成

- **OAuth 登录** — 从企微工作台打开自动完成身份认证
- **JS-SDK 拍照** — 企微内调用原生相机拍照，兼容性更好
- **非企微降级** — 普通浏览器中自动降级为 HTML 拍照方式

## 技术栈

| 层 | 技术 |
|---|------|
| 前端 | Vue 3 + Vant 4（移动端 UI 库），base path `/inventory/` |
| 后端 | Python FastAPI，路由前缀 `/api` |
| OCR | PaddleOCR-VL-1.5 云端 API |
| 数据库 | SQLite（WAL 模式） |
| 部署 | PM2 + Nginx（生产），Docker Compose（备选） |
| 认证 | JWT + 企业微信 OAuth |

## 架构

```
企业微信 / 手机浏览器
         │
    Nginx (:80/:443, HTTPS)
    ├── /                   → 现有项目前端
    ├── /api                → 现有项目后端 (:3000)
    ├── /inventory/         → 库存系统前端 (Vue SPA)
    └── /inventory/api/     → 库存系统后端 (:8000)
                                [Nginx 去掉 /inventory 前缀转发]
                                │
                           SQLite 数据库
                         (inventory + stock_log + audit_log)
```

## 项目结构

```
leadframe-inventory-system/
├── backend/
│   ├── main.py              FastAPI 入口，lifespan 建表，路由前缀 /api
│   ├── database.py           SQLite 模型、CRUD、审计
│   ├── ocr_service.py        PaddleOCR 云端 API 封装
│   ├── auth_service.py       JWT + 企微 access_token + jsapi_ticket
│   ├── routers/
│   │   ├── ocr.py            OCR 接口（20MB 限制）
│   │   ├── inventory.py      库存管理 + 审计 + 导出
│   │   └── auth.py           企微 OAuth + JS-SDK 签名
│   ├── uploads/              上传图片目录
│   ├── .env                  OCR 凭据（gitignore）
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── Home.vue          首页仪表盘
│   │   │   ├── Camera.vue        拍照入库（JS-SDK）
│   │   │   ├── CameraOut.vue     拍照出库（JS-SDK）
│   │   │   ├── StockIn.vue       手动入库
│   │   │   ├── StockOut.vue      搜索出库
│   │   │   ├── InventoryList.vue 库存列表+导出
│   │   │   ├── InventoryDetail.vue 库存详情
│   │   │   └── AuditLogs.vue     操作审计
│   │   ├── utils/
│   │   │   └── wxsdk.js          企微 JS-SDK 封装
│   │   ├── api/index.js          API 请求（baseURL = /inventory/api）
│   │   └── router/index.js       路由（base /inventory/，8 个页面）
│   ├── index.html               含 jweixin-1.2.0.js
│   ├── vite.config.js           base: '/inventory/'
│   └── package.json
├── certs/                        SSL 证书（gitignore）
├── logs/                         应用日志
├── ecosystem.config.js           PM2 进程管理配置
├── docker-compose.yml            Docker 部署（备选）
├── nginx.conf                    Docker 部署用 Nginx 配置
├── nginx-common.conf             Docker 部署用共享 Nginx 配置
├── dev-start.sh                  本地开发一键启动
├── dev-stop.sh                   停止本地开发服务
├── .gitignore
└── CLAUDE.md                     详细开发文档
```

## 部署

### 方式一：PM2 + Nginx（共享服务器）

适用于已部署其他项目的服务器，通过 Nginx 路径区分不同应用。

#### 前置条件

- Ubuntu/Debian 服务器
- 已安装 Node.js 20、Nginx、PM2
- 域名 + SSL 证书（已有 certbot 配置即可，新路径自动受保护）
- PaddleOCR API 凭据（从 https://aistudio.baidu.com/paddleocr/task 获取）
- 企业微信自建应用（CorpID、Secret、AgentID）

#### 1. 安装 Python 3.11

```bash
apt update
apt install -y python3.11 python3.11-venv
```

#### 2. 克隆项目

```bash
git clone <仓库地址> /opt/leadframe-inventory
```

#### 3. 配置后端

```bash
cd /opt/leadframe-inventory

# 创建 Python 虚拟环境并安装依赖
python3.11 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt
```

#### 4. 配置环境变量

**项目根目录 `.env`**（企微 + JWT 配置）：

```bash
cat > /opt/leadframe-inventory/.env << 'EOF'
WECORP_ID=ww1234567890
WECORP_SECRET=your-secret
WECORP_AGENT_ID=1000002
APP_BASE_URL=https://你的域名/inventory
JWT_SECRET=随机安全字符串
AUTH_REQUIRED=true
EOF
```

注意 `APP_BASE_URL` 末尾带 `/inventory`，OAuth 回调依赖此路径。

**`backend/.env`**（OCR 凭据，已 gitignore）：

```bash
cat > /opt/leadframe-inventory/backend/.env << 'EOF'
PADDOLEOCR_API_URL=https://your-api-url/layout-parsing
PADDOLEOCR_TOKEN=your-token
EOF
```

#### 5. 构建前端

```bash
cd /opt/leadframe-inventory/frontend
npm install
npm run build
```

构建产物在 `frontend/dist/`，base path 为 `/inventory/`。

#### 6. PM2 启动后端

```bash
cd /opt/leadframe-inventory
pm2 start ecosystem.config.js
pm2 save
```

后端监听 `127.0.0.1:8000`。

#### 7. Nginx 配置

编辑现有站点配置（如 `/etc/nginx/sites-available/pts`），在 `server {}` 块内追加：

```nginx
    # ── 引线框架库存管理系统 ──

    # API 代理：/inventory/api/ → 后端 :8000/api/（自动去掉 /inventory 前缀）
    location /inventory/api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 20m;
    }

    # 前端静态文件
    location /inventory {
        alias /opt/leadframe-inventory/frontend/dist;
        try_files $uri $uri/ /inventory/index.html;
    }
```

重载 Nginx：

```bash
sudo nginx -t && sudo systemctl reload nginx
```

#### 8. 验证

```bash
# 后端健康检查（直接）
curl http://127.0.0.1:8000/api/health

# 通过 Nginx 访问
curl https://你的域名/inventory/api/health

# 浏览器访问
# https://你的域名/inventory/
```

#### 企业微信配置

1. 企业微信管理后台 → 应用管理 → 创建自建应用
2. 记录 CorpID、Secret、AgentID
3. 应用主页 URL 填写 `https://你的域名/inventory/`
4. 设置网页授权域名（你的域名）
5. 可信域名设置（你的域名）

---

### 方式二：Docker Compose（独立部署）

适用于独占服务器部署，不与其他项目共享。

#### 前置条件

- 云服务器，已安装 Docker 和 Docker Compose
- 域名 + SSL 证书（企微要求 HTTPS）

#### 1. 构建前端

```bash
cd frontend
npm install
npm run build
cd ..
```

#### 2. 配置环境变量

项目根目录 `.env`：

```env
WECORP_ID=ww1234567890
WECORP_SECRET=your-secret
WECORP_AGENT_ID=1000002
APP_BASE_URL=https://inv.example.com
JWT_SECRET=随机安全字符串
AUTH_REQUIRED=true
```

`backend/.env`（OCR 凭据）：

```env
PADDOLEOCR_API_URL=https://your-api-url/layout-parsing
PADDOLEOCR_TOKEN=your-token
```

#### 3. 配置 SSL 证书

```bash
mkdir -p certs
cp fullchain.pem privkey.pem certs/
# 或开发环境使用自签名: ./init-ssl.sh
```

#### 4. 启动服务

```bash
docker compose up -d --build
```

前端通过 Nginx 在 `https://你的域名` 访问。

---

### 本地开发

```bash
# 一键启动（WSL2 环境）
./dev-start.sh

# 或手动启动：
# 后端
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/uvicorn main:app --reload

# 前端（另一个终端）
cd frontend
npm install
npm run dev
```

前端开发服务器在 `http://localhost:5173/inventory/`，Vite 代理 `/api` → `localhost:8000`。

停止服务：`./dev-stop.sh`

## 安全说明

- 图片上传限制 20MB，仅接受图片类型
- 上传图片路径做了路径遍历防护
- 出库操作使用数据库锁（BEGIN IMMEDIATE）防止并发超额
- JWT Secret 必须配置，未设置时无法签发 Token
- 敏感凭据（`.env`、`backend/.env`、`certs/`）已加入 `.gitignore`
- 所有数据变更自动记录审计日志（操作人、时间、IP、变更内容）
