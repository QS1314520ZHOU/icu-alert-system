# EXE 打包

这个项目的 EXE 打包方式是：

1. 构建 `frontend/dist`
2. 复制到 `backend/static`
3. 用 `backend/icu_alert.spec` 通过 PyInstaller 打包

这样最终只有一个后端 EXE，前端静态资源被一起打进去，运行后直接访问：

`http://127.0.0.1:8000`

## 前置条件

- Windows
- Python 已安装，并且能运行 `python`
- Node.js / npm 已安装
- 已安装后端依赖：`backend/requirements.txt`
- 已安装前端依赖：`frontend/package.json`
- 已安装 PyInstaller

## 一键打包

在项目根目录执行：

```powershell
.\build_exe.ps1
```

或：

```bat
build_exe.bat
```

## 输出位置

打包结果默认在：

`backend/dist/ICU-Alert-System`

主程序：

`backend/dist/ICU-Alert-System/ICU-Alert-System.exe`

## 说明

- 打包结果是 `onedir`，不是单文件 `onefile`。
- `onedir` 更适合这个项目，因为依赖较多，包含 FastAPI、Uvicorn、NLP 模型相关资源和前端静态文件。
- `backend/icu_alert.spec` 已包含：
  - `static`
  - `config.yaml`
  - `.env`
  - `knowledge_base`

## 运行

双击：

`ICU-Alert-System.exe`

默认监听：

`0.0.0.0:8000`

本机访问：

`http://127.0.0.1:8000`

## 常见问题

### 1. 前端打不开

先确认 `backend/static/index.html` 是否存在。没有的话说明前端构建或复制步骤失败。

### 2. 启动后数据库连不上

这是运行环境配置问题，不是打包问题。需要检查：

- `backend/.env`
- `backend/config.yaml`
- MongoDB / Redis / 其他外部服务地址

### 3. 想把所有依赖都打进去

PyInstaller 已经会把 Python 运行时和项目依赖打进 `dist/ICU-Alert-System`。  
但数据库、Redis、Node.js 这类外部服务不会被“嵌入”到 EXE 里，它们仍然是外部运行时依赖。
