# Linux 二进制构建矩阵

这个仓库现在建议分成 3 条 Linux 打包链路：

- `cpu-universal`
  - 目标：尽量兼容较新的 Ubuntu / OEL8 / RHEL8 系 Linux
  - 特点：只打 CPU 运行时，不内置 GPU 依赖
  - 基线：`manylinux2014_x86_64`
- `oel8-cpu` / `oel8-gpu`
  - 目标：OEL 8.2 / RHEL 8 系列稳定部署
  - 基线：`oraclelinux:8`
- `ubuntu2004-gpu`
  - 目标：Ubuntu 20.04 GPU 服务器
  - 基线：`ubuntu:20.04`

## 为什么不能只做一个 GPU 包

GPU 版本通常会绑定这些原生运行时：

- `glibc`
- `libstdc++`
- CUDA / cuDNN
- PyTorch / ONNXRuntime 的 `.so`

所以 GPU 二进制很难同时稳定兼容 Ubuntu 和 OEL8。更现实的策略是：

- CPU 版追求跨发行版
- GPU 版按系统分别构建

## 1. 通用 CPU 包

Windows PowerShell:

```powershell
.\build_universal.ps1 -Version 1.0.0
```

Linux / macOS / Git Bash:

```bash
./build-universal.sh 1.0.0
```

产物：

```text
dist-output/icu-alert-system-linux-universal-1.0.0.tar.gz
```

部署：

```bash
cd /opt
tar xzf icu-alert-system-linux-universal-1.0.0.tar.gz
cd icu-alert-system-linux-universal
vi .env
./start.sh
```

说明：

- 默认 `ICU_ACCELERATION=cpu`
- 更适合做“一套包多台 Linux 主机复用”
- 不保证兼容所有极老系统，但比 Ubuntu 专用包更有机会跨发行版运行

## 2. OEL8 专用包

Windows PowerShell:

```powershell
.\build_oel8.ps1 -Version 1.0.0 -Variant both
```

Linux / macOS / Git Bash:

```bash
./build.sh 1.0.0 both
```

产物：

- `icu-alert-system-cpu-<version>.el8.x86_64.tar.gz`
- `icu-alert-system-gpu-<version>.el8.x86_64.tar.gz`

详细说明见：

[`OEL8_BUILD.md`](/d:/icu-alert-system/OEL8_BUILD.md)

## 3. Ubuntu 20.04 GPU 包

Linux / macOS / Git Bash:

```bash
./build-gpu.sh
```

产物：

```text
dist/icu-alert-system-ubuntu2004-gpu/
dist/icu-alert-system-ubuntu2004-gpu/manifest.sha256
dist/icu-alert-system-ubuntu2004-gpu.tar.gz
```

说明：

- 这是 Ubuntu 20.04 GPU 专用产物
- 不建议拿它直接跑到 OEL8
- 完整包会自动生成 `manifest.sha256`，后续可基于它制作纯内网增量包

### 3.1 Ubuntu GPU 快速源码增量更新包

> 这是纯内网常规更新推荐方式：不跑 Docker，不跑 PyInstaller，不重新生成几个 G 的完整包。

首次升级到支持源码增量的 GPU 基座包时，仍需完整部署一次：

```bash
./build-gpu.sh
```

完整包内会包含稳定运行时、`_internal/` 依赖库，以及外置业务代码目录：

```text
app/
static/
config.yaml
manifest.sha256
```

之后普通业务更新只需要：

```bash
./build-gpu-source-delta.sh --base-manifest old-manifest.sha256 --base-commit <上次发布commit>
```

如果不清楚上次 commit，也可以只传旧服务器拿出来的 manifest：

```bash
./build-gpu-source-delta.sh --base-manifest old-manifest.sha256
```

产物：

```text
dist/delta/icu-alert-system-source-delta-<version>.tar.gz
```

脚本只打包这些可源码增量更新的内容：

- `backend/app/**` -> 部署目录 `app/**`
- `backend/config.yaml` -> `config.yaml`
- `backend/knowledge_base/**` -> `knowledge_base/**`
- `backend/static/**` 或 `frontend/dist/**` -> `static/**`

如果指定了 `--base-commit`，脚本发现以下文件变更会拒绝增量并提示完整打包：

- `Dockerfile*`
- `build-gpu.sh`
- `entry.py`
- `backend/requirements*.txt`
- `frontend/package*.json`
- `package*.json`

内网服务器应用源码增量包：

```bash
rm -rf /tmp/icu-delta
mkdir -p /tmp/icu-delta
tar xzf /tmp/icu-alert-system-source-delta-<version>.tar.gz -C /tmp/icu-delta
/tmp/icu-delta/apply-gpu-delta.sh /opt/icu-alert-system-ubuntu2004-gpu
```

### 3.2 Ubuntu GPU 完整包差异增量

下面这个方式需要先有新的完整产物，适合已经完整打过包后切传输差异，不适合磁盘空间紧张时的常规更新。

首次部署仍使用完整包：

```bash
scp dist/icu-alert-system-ubuntu2004-gpu.tar.gz user@gpu-server:/opt/
cd /opt
tar xzf icu-alert-system-ubuntu2004-gpu.tar.gz
cd /opt/icu-alert-system-ubuntu2004-gpu
cp .env.template .env
./run.sh start-bg
```

后续更新先正常构建完整产物，再生成只包含变化文件的小包：

```bash
./build-gpu.sh
./build-gpu-delta.sh --base previous-manifest.sha256
```

`--base` 可以传上一次发布保存的 `manifest.sha256`，也可以传上一次完整解压目录：

```bash
./build-gpu-delta.sh --base /path/to/previous/icu-alert-system-ubuntu2004-gpu
```

产物：

```text
dist/delta/icu-alert-system-gpu-delta-<version>.tar.gz
```

内网服务器应用增量包：

```bash
mkdir -p /tmp/icu-delta
tar xzf /tmp/icu-alert-system-gpu-delta-<version>.tar.gz -C /tmp/icu-delta
/tmp/icu-delta/apply-gpu-delta.sh /opt/icu-alert-system-ubuntu2004-gpu
```

增量规则：

- `.env`、日志、pid、`.delta-backups/` 不进入 manifest，避免覆盖服务器本机配置
- `_internal/` 变化超过 300MB 或 200 个文件时，脚本会停止并提示发布完整包
- 应用增量包前会停止服务，覆盖后校验 manifest，通过后执行 `./run.sh start-bg`
- 默认保留最近 3 次 `.delta-backups/`，可用 `KEEP_BACKUPS=5` 调整

## 建议选型

如果你的目标是省心部署：

- 多种 Linux 混合环境：优先 `cpu-universal`
- OEL 8.2 生产环境：优先 `oel8-cpu` / `oel8-gpu`
- Ubuntu GPU 服务器：优先 `ubuntu2004-gpu`
