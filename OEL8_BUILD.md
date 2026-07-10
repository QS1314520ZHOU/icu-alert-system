# OEL 8.2 二进制打包

目标产物：

- `icu-alert-system-cpu-<version>.el8.x86_64.tar.gz`
- `icu-alert-system-gpu-<version>.el8.x86_64.tar.gz`

两者都是在 `oraclelinux:8` 容器内构建，适合部署到 OEL 8.2 / RHEL 8 系列主机。

## 本机构建

Windows PowerShell:

```powershell
.\build_oel8.ps1 -Version 1.0.0 -Variant both
```

Linux / macOS / Git Bash:

```bash
./build.sh 1.0.0 both
```

可选 `Variant`:

- `cpu`
- `gpu`
- `both`

产物输出目录：

`dist-output/`

## 构建要求

- 本机已安装 Docker
- 构建机能访问：
  - `oraclelinux:8`
  - npm registry
  - PyPI
  - GPU 版本额外需要访问 `https://download.pytorch.org/whl/cu121`

## OEL 8.2 部署

```bash
cd /opt
tar xzf icu-alert-system-cpu-1.0.0.el8.x86_64.tar.gz
cd /opt/icu-alert-system-cpu
vi .env
./install.sh
systemctl start icu-alert
systemctl status icu-alert
```

GPU 版本类似：

```bash
cd /opt
tar xzf icu-alert-system-gpu-1.0.0.el8.x86_64.tar.gz
cd /opt/icu-alert-system-gpu
vi .env
./install.sh
systemctl start icu-alert-gpu
systemctl status icu-alert-gpu
```

## GPU 运行前提

- OEL 8.2 主机已安装可用 NVIDIA 驱动
- `nvidia-smi` 正常
- 当前打包链按 CUDA 12.1 PyTorch wheel 构建
- 默认会写入 `.env`:

```env
ICU_ACCELERATION=gpu
```

如果要强制退回 CPU，可改成：

```env
ICU_ACCELERATION=cpu
```

## 当前打包内容

- 后端可执行文件
- Python 运行时依赖
- 前端静态资源
- `config.yaml`
- `knowledge_base`
- `.env` 模板

## 说明

- CPU 包默认安装 `torch + onnxruntime`
- GPU 包默认安装 `torch + onnxruntime-gpu`
- `TemporalRiskModelRuntime` 现在会优先尝试 CUDA / GPU 推理
- `sentence-transformers` 相关 embedding 模型也会优先尝试 CUDA
