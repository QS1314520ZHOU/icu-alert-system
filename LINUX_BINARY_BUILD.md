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
```

说明：

- 这是 Ubuntu 20.04 GPU 专用产物
- 不建议拿它直接跑到 OEL8

## 建议选型

如果你的目标是省心部署：

- 多种 Linux 混合环境：优先 `cpu-universal`
- OEL 8.2 生产环境：优先 `oel8-cpu` / `oel8-gpu`
- Ubuntu GPU 服务器：优先 `ubuntu2004-gpu`
