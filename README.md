# ICU 智能预警系统（ICU Alert System）

![ICU Alert System Logo](docs/images/logo.png)

面向重症监护病区（ICU）的全栈平台，覆盖：

- 患者风险实时预警
- 护理与治疗流程联动（Bundle / 装置 / 管路）
- 患者详情多维工作台（趋势、检验、用药、预警、AI）
- 科研分析与导出
- 大屏与病区运营视角

---

## 目录

- [1. 项目概览](#1-项目概览)
- [2. 核心能力](#2-核心能力)
- [3. 技术栈](#3-技术栈)
- [4. 仓库结构](#4-仓库结构)
- [5. 快速启动（本地开发）](#5-快速启动本地开发)
- [6. Docker 部署](#6-docker-部署)
- [7. 环境变量说明](#7-环境变量说明)
- [8. 关键工作流](#8-关键工作流)
- [9. 开发与构建命令](#9-开发与构建命令)
- [10. 打包发布](#10-打包发布)
- [11. 常见问题排查](#11-常见问题排查)
- [12. 相关文档](#12-相关文档)

---

## 1. 项目概览

本项目是一个 **前后端一体化 ICU 智能预警系统**：

- **后端** 使用 FastAPI，负责患者数据聚合、规则扫描、AI 服务编排、WebSocket 推送。
- **前端** 使用 Vue 3 + Vite，提供患者总览、患者详情、预警审核、AI 工作台、大屏与科研工作台。
- **扫描 Worker** 独立进程持续执行临床规则，写入预警结果并触发联动。

系统适合以下场景：

- ICU 临床值班与床旁监护
- 护理质控（Bundle / 装置留置 / HAI 风险）
- 科室级风险态势追踪
- 医疗 AI 辅助推理与科研分析

---

## 2. 核心能力

### 2.1 临床预警与规则引擎

- 多扫描器并行处理患者状态
- 支持分级风险（normal / warning / high / critical）
- 支持预警审核、查看回执、闭环追踪

> 扫描器细节请见：[SCANNERS.md](SCANNERS.md)

### 2.2 患者详情工作台

- 生命体征快照 + 趋势
- 检验 / 用药 / 护理评估
- 装置/管路联动视图
- 器官风险热力图 + 预警聚焦

### 2.3 AI 与知识增强

- 检验摘要、风险预测、临床推理
- 交班摘要（handoff）
- 知识文档检索与片段浏览（RAG）
- 多模块 AI 工作台整合展示

### 2.4 运营与科研

- 大屏监测（病区级）
- 预警统计分析
- 科研分析与导出流程

---

## 3. 技术栈

### 后端

- Python 3.10+
- FastAPI / Uvicorn
- Redis（队列/缓存）
- MongoDB（业务数据）

### 前端

- Vue 3 + TypeScript
- Vite
- Ant Design Vue
- ECharts
- Pinia + Vue Router

### 部署与发布

- Docker Compose
- PyInstaller（Windows EXE）
- Linux binary 构建脚本

---

## 4. 仓库结构

```text
icu-alert-system/
├─ backend/                    # FastAPI + 扫描引擎 + AI 服务
│  ├─ app/
│  │  ├─ alert_engine/         # 扫描器与预警引擎
│  │  ├─ routers/              # API 路由
│  │  ├─ services/             # 业务/AI/分析服务
│  │  └─ main.py               # FastAPI 入口
│  ├─ run_server.py            # 后端启动入口
│  ├─ run_scan_worker.py       # 扫描 Worker 启动入口
│  ├─ .env.example             # 后端环境变量模板
│  └─ requirements*.txt
├─ frontend/                   # Vue 3 前端
│  ├─ src/
│  ├─ scripts/sync-to-backend-static.mjs
│  └─ package.json
├─ docs/                       # 文档与图片资源
├─ SCANNERS.md                 # 扫描器口径说明
├─ docker-compose.yml
└─ README.md
```

---

## 5. 快速启动（本地开发）

> 以下命令均以仓库根目录为起点。

### 5.1 后端依赖安装

```bash
cd backend
python -m pip install -r requirements.txt
```

`backend/requirements.txt` 当前指向 `requirements.cpu.txt`，适合常规开发机。

### 5.2 配置环境变量

```bash
cd backend
cp .env.example .env
```

按实际环境修改 `.env`（数据库、Redis、LLM）。

### 5.3 启动后端 API

```bash
cd backend
python run_server.py
```

默认端口：`8000`  
健康检查：`http://127.0.0.1:8000/health`

### 5.4 启动扫描 Worker（建议单独终端）

```bash
cd backend
python run_scan_worker.py
```

### 5.5 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认地址：`http://127.0.0.1:5173`

---

## 6. Docker 部署

项目提供 `docker-compose.yml`，内含：

- `api`（FastAPI 服务）
- `redis`（Redis 服务）

启动：

```bash
docker-compose up -d
```

查看日志：

```bash
docker-compose logs -f api
docker-compose logs -f redis
```

停止：

```bash
docker-compose down
```

---

## 7. 环境变量说明

主要变量来自 `backend/.env.example`。

| 变量 | 示例 | 说明 |
| --- | --- | --- |
| `APP_HOST` | `0.0.0.0` | API 监听地址 |
| `APP_PORT` | `8000` | API 端口 |
| `SMARTCARE_DB_HOST` | `127.0.0.1` | SmartCare Mongo 地址 |
| `SMARTCARE_DB_PORT` | `27017` | SmartCare Mongo 端口 |
| `DATACENTER_DB_HOST` | `127.0.0.1` | DataCenter Mongo 地址 |
| `DATACENTER_DB_PORT` | `27017` | DataCenter Mongo 端口 |
| `REDIS_HOST` | `127.0.0.1` | Redis 地址 |
| `REDIS_PORT` | `6379` | Redis 端口 |
| `LLM_BASE_URL` | `http://127.0.0.1:11434/v1` | LLM API 基地址 |
| `LLM_API_KEY` | `your_api_key` | LLM 访问密钥 |
| `LLM_MODEL` | `qwen2.5:32b` | 主模型名 |
| `SECRET_KEY` | `change-me` | 系统密钥 |
| `CORS_ALLOWED_ORIGINS` | `http://127.0.0.1:5173` | CORS 白名单 |

---

## 8. 关键工作流

### 8.1 预警主链路

1. Worker 拉取患者相关数据（监护、检验、装置等）  
2. 扫描器计算风险并生成告警  
3. 告警入库并可通过 WebSocket / API 提供给前端  
4. 前端在总览、大屏、患者详情中展示并支持审核闭环

### 8.2 前端构建与静态同步

`frontend/package.json` 中：

- `npm run build` 会执行 `postbuild`
- `postbuild` 脚本会把前端产物同步到 `backend/static`

因此只要在 `frontend/` 构建成功，后端静态资源会自动更新。

---

## 9. 开发与构建命令

### 前端

```bash
cd frontend
npm run dev       # 开发
npm run build     # 生产构建 + 同步到 backend/static
npm run preview   # 本地预览构建产物
```

### 后端

```bash
cd backend
python run_server.py
python run_scan_worker.py
```

---

## 10. 打包发布

按目标环境使用仓库根目录脚本：

- Windows EXE：`build_exe.ps1` / `build_exe.bat`
- Linux：`build.sh` / `build-universal.sh`
- GPU/特定环境：`build-gpu.sh`、`Dockerfile.gpu-build` 等

详细请参考：

- [EXE_BUILD.md](EXE_BUILD.md)
- [LINUX_BINARY_BUILD.md](LINUX_BINARY_BUILD.md)
- [OEL8_BUILD.md](OEL8_BUILD.md)

---

## 11. 常见问题排查

### 11.1 前端能开但没有数据

- 检查后端 `8000` 端口是否启动
- 检查 `backend/.env` 的数据库与 Redis 是否可连接
- 访问 `/health` 验证 API 状态

### 11.2 预警不刷新 / 不生成

- 检查 `run_scan_worker.py` 是否在运行
- 检查 Redis 连通性与鉴权配置
- 查看后端日志是否有扫描器异常

### 11.3 页面加载慢

- 先看浏览器 Network 是否出现后端超时
- 检查 Redis/Mongo 延迟
- 排查是否同时触发大量患者级详情请求

### 11.4 构建成功但页面资源未更新

- 确认执行的是 `frontend` 下的 `npm run build`
- 确认 `postbuild` 日志出现 `synced frontend dist to .../backend/static`

---

## 12. 相关文档

- 扫描器与风险口径：[SCANNERS.md](SCANNERS.md)
- 可执行打包：[EXE_BUILD.md](EXE_BUILD.md)
- Linux 二进制构建：[LINUX_BINARY_BUILD.md](LINUX_BINARY_BUILD.md)
- OEL8 构建：[OEL8_BUILD.md](OEL8_BUILD.md)

---

如需我再补一版 **“面向新同事入门（含系统架构图 + API 清单）”**，我可以继续在 `docs/` 下补齐并在 README 增加跳转。

