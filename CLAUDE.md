# CLAUDE.md — 引线框架库存管理系统

## 项目概述

引线框架（Leadframe）库存管理系统。移动端 H5 应用，嵌入企业微信使用。核心流程：拍照 → PaddleOCR-VL-1.5 云端 API 识别标签 → 结构化数据入库。以物料编码+批号为唯一标识，相同则数量累加。

## 技术栈

- 后端：Python FastAPI，SQLite（WAL 模式），httpx 调用 PaddleOCR 云端 API
- 前端：Vue 3 + Vant 4 + Vite，base path `/inventory/`
- 部署：PM2 + Nginx（生产，与其他项目共用服务器），Docker Compose（备选）
- 认证：JWT + 企业微信 OAuth

## 路径配置

前端 base path 为 `/inventory/`（`vite.config.js` 中 `base: '/inventory/'`），Vue Router 使用 `createWebHistory('/inventory/')`。

- 前端静态文件通过 `/inventory/` 访问
- API 调用使用 `import.meta.env.BASE_URL + 'api'`，解析为 `/inventory/api/...`
- Nginx 通过 `proxy_pass` 将 `/inventory/api/` 映射到后端 `/api/`（去掉前缀）
- 后端路由前缀为 `/api/...`，无需感知外层 `/inventory` 路径
- 本地开发时 Vite 代理 `/api` → `localhost:8000`，路径正常工作

## 关键文件

| 文件 | 职责 |
|------|------|
| `backend/main.py` | FastAPI 入口，lifespan 建表，CORS，路由挂载（prefix=/api） |
| `backend/database.py` | SQLite 连接管理，inventory/stock_log/audit_log 三张表的建表/CRUD/审计 |
| `backend/ocr_service.py` | PaddleOCR-VL-1.5 云端 API 调用，base64 编码图片，解析返回的 Markdown 文本为结构化字段 |
| `backend/routers/ocr.py` | POST /api/ocr，接收图片上传（限制 20MB），保存文件后调用 OCR |
| `backend/routers/inventory.py` | 库存 CRUD、入库、出库、记录查询、审计日志查询、上传图片静态服务、Excel 导出 |
| `backend/auth_service.py` | JWT 签发/验证，企微 API 调用（access_token + jsapi_ticket + 用户身份），缓存 |
| `backend/routers/auth.py` | 企微 OAuth + 密码登录：授权链接、code→JWT 回调、密码验证登录、JS-SDK 签名配置 |
| `frontend/src/api/index.js` | Axios 实例（baseURL = BASE_URL + 'api'，即 `/inventory/api`），所有后端接口封装 |
| `frontend/src/utils/wxsdk.js` | 企微 JS-SDK 封装：初始化 wx.config、chooseImage（支持拍照+相册）、getLocalImgData，非企微降级，上传前压缩图片 |
| `frontend/src/views/Camera.vue` | 拍照/选图（企微 JS-SDK 或 HTML input）→ OCR → 展示可编辑识别结果 → 确认入库 |
| `frontend/src/views/CameraOut.vue` | 拍照出库：拍照识别 → 匹配库存记录 → 选择 → 出库 |
| `frontend/src/views/StockOut.vue` | 搜索库存 → 选择 → 输入出库数量 → 确认 |
| `frontend/src/views/InventoryList.vue` | 库存列表，搜索、下拉刷新、无限加载、滑动删除、导出 Excel |
| `frontend/src/views/InventoryDetail.vue` | 库存详情页 |
| `frontend/src/views/AuditLogs.vue` | 操作记录日志列表，按操作类型筛选 |
| `frontend/src/views/Home.vue` | 首页仪表盘，统计+快捷入口（4 宫格）+库存预警，导航栏右上角「操作记录」入口 |
| `frontend/src/views/StockIn.vue` | 手动入库表单 |
| `frontend/src/views/Login.vue` | 密码登录页（设置 LOGIN_PASSWORD 后生效） |
| `frontend/src/router/index.js` | Vue Router，history 模式，base `/inventory/`，8 个路由 |
| `frontend/vite.config.js` | Vite 配置，base: `/inventory/`，开发代理 `/api` → `localhost:8000` |
| `ecosystem.config.js` | PM2 进程管理配置（生产部署用） |
| `nginx.conf` | Docker 部署用 Nginx 配置，HTTP/HTTPS，安全响应头，gzip |
| `nginx-common.conf` | Docker 部署用共享 Nginx 配置：API 代理、SPA try_files、静态资源缓存、安全头 |
| `docker-compose.yml` | Docker 部署：backend + frontend(nginx:alpine)，env_file + ${VAR} 引用，健康检查 |
| `dev-start.sh` | 本地开发一键启动（uvicorn + vite，WSL2 环境） |
| `dev-stop.sh` | 停止本地开发服务 |

## 数据库

SQLite，文件 `backend/inventory.db`。

**inventory 表**：id, material_code, spec, manufacturer, batch_no, production_date, expiry_date, quantity, note, image_path, created_at, updated_at。唯一约束 `UNIQUE(material_code, batch_no)`。

**stock_log 表**：id, inventory_id(外键), type('in'/'out'), quantity, note, operator, created_at。

**audit_log 表**：id, user_id, user_name, action('stock_in'/'stock_out'/'update'/'delete'), table_name, record_id, snapshot(JSON), changes(JSON), detail, ip_address, created_at。

### 数量单位

所有数量以 **K（千）** 为单位存储，最多 3 位小数。如 `"46.368"` 表示 46,368 只。预警阈值为 2K。

## OCR 流程

1. 前端拍照/选图（企微内用 JS-SDK `wx.chooseImage`，非企微用 HTML input）→ 自动压缩图片（最大宽度 1600px，JPEG 质量 80%）→ POST /api/ocr（multipart/form-data，限制 20MB）
2. 后端保存图片到 uploads/ → base64 编码 → 调用 PaddleOCR-VL-1.5 云端 API
3. API 返回 `result.layoutParsingResults[].markdown.text`（Markdown 文本）
4. `parse_ocr_markdown()` 用正则从 Markdown 中提取字段（厂家、规格、批号、数量、日期等）
5. 厂家名归一化（`_resolve_manufacturer`），AAMI 厂家专用规格提取（`_resolve_aami_spec`）
6. 数量统一转 K 单位（`_normalize_qty`：支持 PCS/只/万/K/M）
7. 日期格式统一为 YYYY-MM-DD（`_normalize_date`：支持中英文各种格式）
8. 返回 raw_text + parsed 给前端，用户可在 Camera.vue 中手动修正后确认入库

OCR 凭据通过 `backend/.env` 文件注入（已 gitignore）：`PADDOLEOCR_API_URL`、`PADDOLEOCR_TOKEN`。

## 企微集成

### OAuth 认证

环境变量配置（通过项目根目录 `.env`、PM2 env_file、或宿主机环境变量注入）：

| 变量 | 说明 | 示例 |
|------|------|------|
| `WECORP_ID` | 企业微信 CorpID | `ww1234567890` |
| `WECORP_SECRET` | 自建应用 Secret | `xxx` |
| `WECORP_AGENT_ID` | 自建应用 AgentID | `1000002` |
| `APP_BASE_URL` | 应用外网地址（含路径前缀） | `https://inv.example.com/inventory` |
| `JWT_SECRET` | JWT 签名密钥（必须设置） | 随机字符串 |
| `AUTH_REQUIRED` | 是否强制登录 | `true` / `false` |
| `LOGIN_PASSWORD` | 共享登录密码（设置后启用密码登录模式） | 自定义密码 |

系统支持两种认证模式，按配置自动选择：
- **密码登录**：设置 `LOGIN_PASSWORD` 后启用。访问页面时跳转登录页，输入共享密码后签发 JWT（30 天有效）。适合小团队使用。
- **企微 OAuth**：配置 `WECORP_ID` + `WECORP_SECRET` + `AUTH_REQUIRED=true` 后启用。企微内自动授权，非企微浏览器提示在企微中打开。

两种模式可独立使用，也可同时配置（密码登录优先）。

不配置企微变量时系统正常运行（无登录拦截）。`AUTH_REQUIRED=true` 时强制登录。

### JS-SDK 拍照

企微内嵌 H5 通过 JS-SDK 调用原生拍照能力，解决部分 Android 机型 HTML input 拍照不稳定的问题。

流程：
1. 页面加载时 `wxsdk.js` 自动获取 JS-SDK 签名（`GET /api/auth/wecom/jsapi-config?url=当前页面`）
2. 调用 `wx.config` 初始化（使用 jsapi_ticket，与 access_token 独立）
3. 用户点击拍照/选图 → `wx.chooseImage`（支持拍照和相册）→ `wx.getLocalImgData` → 转 File 对象
4. 图片经过前端压缩（Canvas 缩放至最大 1600px 宽度，JPEG 80% 质量）
5. 压缩后的 File 走 OCR 流程

非企微环境自动降级为 HTML `<input type="file" accept="image/*">`（支持拍照和相册选择），同样经过压缩。

### 操作记录（审计日志）

所有数据修改操作自动记录审计日志：

| 操作 | action | 记录内容 |
|------|--------|----------|
| 入库 POST /api/stock-in | stock_in | 数量、规格、批号 |
| 出库 POST /api/stock-out | stock_out | 出库数量 + 操作前完整快照 |
| 编辑 PUT /api/inventory/:id | update | 实际变更字段的 diff（old → new） |
| 删除 DELETE /api/inventory/:id | delete | 被删记录的完整快照 |

每条审计记录包含：操作人（user_id + user_name）、操作时间、IP 地址、变更详情。通过 `GET /api/audit-logs` 查询，前端首页导航栏右上角「操作记录」入口跳转 `/audit-logs` 页面展示。

## 自动部署

项目配置了 GitHub Actions（`.github/workflows/deploy.yml`），推送到 `main` 分支时自动部署到服务器。

需要在 GitHub 仓库 Settings → Secrets 中配置：
- `SERVER_HOST`：服务器 IP
- `SERVER_USER`：SSH 用户名
- `SERVER_SSH_KEY`：SSH 私钥

部署流程：git pull → pip install 后端依赖 → npm install + build 前端 → pm2 restart

## 构建和部署

生产部署使用 PM2 + Nginx，可与其他项目共用同一台服务器（通过 Nginx 路径区分）。也支持 Docker Compose 独立部署。

### 方式一：PM2 + Nginx（生产推荐，共享服务器）

**1. 安装依赖**

```bash
apt install -y python3.11 python3.11-venv
```

**2. 克隆项目并配置后端**

```bash
git clone <仓库地址> /opt/leadframe-inventory
cd /opt/leadframe-inventory

# Python 虚拟环境
python3.11 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt
```

**3. 配置环境变量**

项目根目录 `.env`（认证 + JWT）：

```env
JWT_SECRET=随机安全字符串
LOGIN_PASSWORD=你的登录密码
# 企微 OAuth（可选）
# WECORP_ID=ww1234567890
# WECORP_SECRET=your-secret
# WECORP_AGENT_ID=1000002
# APP_BASE_URL=https://你的域名/inventory
# AUTH_REQUIRED=true
```

`backend/.env`（OCR 凭据，已 gitignore）：

```env
PADDOLEOCR_API_URL=https://your-api-url/layout-parsing
PADDOLEOCR_TOKEN=your-token
```

**4. 构建前端**

```bash
cd /opt/leadframe-inventory/frontend
npm install
npm run build
```

**5. PM2 启动后端**

确保 `ecosystem.config.js` 中 `interpreter` 指向 venv 的 Python（PM2 默认用 Node.js 执行，会报语法错误）：

```js
module.exports = {
  apps: [{
    name: 'leadframe-inv',
    cwd: '/opt/leadframe-inventory/backend',
    interpreter: '/opt/leadframe-inventory/backend/venv/bin/python',
    script: '/opt/leadframe-inventory/backend/venv/bin/uvicorn',
    args: 'main:app --host 127.0.0.1 --port 8000',
    env_file: '/opt/leadframe-inventory/.env',
    max_memory_restart: '500M',
  }]
}
```

```bash
pm2 start ecosystem.config.js
pm2 save
```

**6. Nginx 配置**

在现有站点的 server 块内追加：

```nginx
# 引线框架库存管理系统
location /inventory/api/ {
    proxy_pass http://127.0.0.1:8000/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 20m;
}

location /inventory {
    alias /opt/leadframe-inventory/frontend/dist;
    try_files $uri $uri/ /inventory/index.html;
}
```

重载：`sudo nginx -t && sudo systemctl reload nginx`

### 方式二：Docker Compose（独立部署）

```bash
# SSL 证书（开发用自签名）
./init-ssl.sh

# 构建前端
cd frontend && npm install && npm run build && cd ..

# 启动
docker compose up -d --build
```

### 本地开发

```bash
./dev-start.sh   # 一键启动（uvicorn + vite）
./dev-stop.sh    # 停止服务
```

或手动启动：

```bash
# 后端
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
# 配置 backend/.env 后启动
./venv/bin/uvicorn main:app --reload

# 前端（另一个终端）
cd frontend
npm install
npm run dev
```

前端开发服务器在 `http://localhost:5173`，Vite 代理 `/api` → `localhost:8000`。

## API 端点

后端路由前缀为 `/api`。通过 Nginx 访问时路径为 `/inventory/api/...`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/health | 健康检查 |
| GET | /api/config | 前端配置探测（企微是否启用、是否强制登录） |
| POST | /api/ocr | 图片 OCR 识别（限制 20MB） |
| GET | /api/inventory | 库存列表（?search=&page=&size=） |
| GET | /api/inventory/alerts | 低库存预警（< 2K） |
| GET | /api/inventory/export | 导出 Excel（?search=） |
| GET | /api/inventory/:id | 单条库存 |
| PUT | /api/inventory/:id | 更新库存（含审计） |
| DELETE | /api/inventory/:id | 删除库存（含审计，删除前记录快照） |
| POST | /api/stock-in | 入库（相同物料编码+批号累加数量） |
| POST | /api/stock-out | 出库（扣减数量，BEGIN IMMEDIATE 防竞态） |
| GET | /api/stock-logs | 出入库记录（?inventory_id=&page=） |
| GET | /api/audit-logs | 操作审计日志（?action=&page=&size=） |
| GET | /api/uploads/:filename | 上传图片静态服务（防路径遍历） |
| GET | /api/material-code-suggest | 根据规格建议物料编码（?spec=） |
| GET | /api/auth/wecom/url | 生成企微 OAuth 授权链接 |
| GET | /api/auth/wecom/callback | 企微 OAuth 回调，code→JWT→重定向 |
| POST | /api/auth/wecom/login | 前端用 code 换 JWT |
| POST | /api/auth/login | 密码登录（验证 LOGIN_PASSWORD，签发 30 天 JWT） |
| GET | /api/auth/wecom/jsapi-config | JS-SDK 签名配置（?url=） |
| GET | /api/auth/me | 获取当前登录用户信息 |

## 前端路由

所有路由基于 base path `/inventory/`。

- `/inventory/` — Home.vue（首页仪表盘）
- `/inventory/login` — Login.vue（密码登录页）
- `/inventory/camera` — Camera.vue（拍照+OCR+确认入库）
- `/inventory/camera-out` — CameraOut.vue（拍照识别+匹配+出库）
- `/inventory/stock-in` — StockIn.vue（手动入库表单）
- `/inventory/stock-out/:id?` — StockOut.vue（搜索/选择→出库）
- `/inventory/inventory` — InventoryList.vue（库存列表+导出）
- `/inventory/inventory/:id` — InventoryDetail.vue（库存详情）
- `/inventory/audit-logs` — AuditLogs.vue（操作审计日志）

## 注意事项

- PaddleOCR API 是云端服务，需要网络连通，首次调用可能有数秒延迟
- H5 拍照需要 HTTPS 环境（生产环境通过 certbot 配置 SSL）
- 企微内使用 JS-SDK 拍照，非企微环境降级为 HTML input
- JWT_SECRET 必须设置，未设置时无法签发 Token
- CORS 默认 `*`（开发用），生产环境通过 Nginx 同源代理，可设 `CORS_ORIGINS` 收紧
- 出库操作使用 `BEGIN IMMEDIATE` 防止并发超额出库
- 后端日志同时输出到控制台和 `logs/app.log`
- `backend/.env` 和 `certs/` 已加入 `.gitignore`，不提交敏感信息
- `APP_BASE_URL` 在共享服务器部署时必须包含 `/inventory` 路径前缀（OAuth 回调依赖）
