# 部署指南

## 环境要求

- Docker 20.10+
- Docker Compose 2.0+
- Node.js 18+ (开发环境)
- Python 3.11+ (开发环境)

## 快速部署

### 1. 克隆项目

```bash
git clone <repository-url>
cd icu-alert-system
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，配置数据库连接等
```

### 3. 启动服务

```bash
# 生产环境
docker-compose up -d

# 开发环境
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### 4. 访问服务

- 前端: http://localhost:5173 (开发) 或 http://localhost:8000 (生产)
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs

## 开发环境部署

### 1. 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

## 生产环境部署

### 1. 构建镜像

```bash
# 构建后端镜像（包含前端）
docker build -f backend/Dockerfile -t icu-alert:latest .

# 或分别构建
docker build -f backend/Dockerfile --target backend -t icu-alert-backend:latest .
docker build -f frontend/Dockerfile -t icu-alert-frontend:latest .
```

### 2. 启动服务

```bash
docker-compose -f docker-compose.yml up -d
```

### 3. 查看日志

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f backend
```

## 环境变量说明

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MONGODB_URL` | MongoDB 连接地址 | `mongodb://localhost:27017` |
| `REDIS_URL` | Redis 连接地址 | `redis://localhost:6379` |
| `DISEASE_CENTER_MOCK_ENABLED` | 是否启用 Mock 数据 | `false` |
| `VITE_ENABLE_DISEASE_CENTER_MOCK` | 前端是否启用 Mock | `false` |
| `AI_MODEL_ID` | AI 模型 ID | `Qwen2-7B-Medical` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

## 健康检查

### 后端健康检查

```bash
curl http://localhost:8000/health
```

### 评分系统健康检查

```bash
curl http://localhost:8000/api/disease-center/scoring/health
```

## 常见问题

### 1. 端口冲突

如果端口被占用，修改 `docker-compose.yml` 中的端口映射：

```yaml
ports:
  - "8080:8000"  # 将 8000 改为 8080
```

### 2. 数据库连接失败

检查 MongoDB 和 Redis 服务是否正常运行：

```bash
docker-compose ps
docker-compose logs mongodb
docker-compose logs redis
```

### 3. 前端无法访问后端

确保 `VITE_API_URL` 环境变量配置正确：

```yaml
environment:
  - VITE_API_URL=http://backend:8000
```

## 监控和日志

### 查看服务状态

```bash
docker-compose ps
```

### 查看资源使用

```bash
docker stats
```

### 查看日志

```bash
# 实时日志
docker-compose logs -f

# 最近 100 行日志
docker-compose logs --tail 100
```

## 备份和恢复

### 备份 MongoDB

```bash
docker exec mongodb mongodump --out /backup
docker cp mongodb:/backup ./backup
```

### 恢复 MongoDB

```bash
docker cp ./backup mongodb:/backup
docker exec mongodb mongorestore /backup
```

## 更新部署

### 1. 拉取最新代码

```bash
git pull
```

### 2. 重新构建并部署

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 3. 数据库迁移（如需要）

```bash
docker-compose exec backend python -m app.migrations
```
