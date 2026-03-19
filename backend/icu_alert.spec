# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ============ 自动收集所有 app 子模块 ============
app_imports = collect_submodules('app')
tzdata_imports = collect_submodules('tzdata')

# ============ 数据文件 ============
datas = [
    ('static', 'static'),
    ('config.yaml', '.'),
    ('.env', '.'),
]
datas += collect_data_files('sentence_transformers')
datas += collect_data_files('transformers')
datas += collect_data_files('tzdata')

# ============ 隐式导入 ============
hidden_imports = app_imports + tzdata_imports + [
    # uvicorn
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    # FastAPI / Starlette
    'fastapi',
    'starlette.routing',
    'starlette.middleware',
    'starlette.middleware.cors',
    # 数据库
    'pymongo',
    'redis',
    'redis.asyncio',
    # AI 相关
    'sentence_transformers',
    'torch',
    'transformers',
    'tokenizers',
    'numpy',
    'httpx',
    # 加密
    'jose',
    'passlib',
    'bcrypt',
    # 其他
    'pydantic',
    'pydantic_settings',
    'yaml',
    'dotenv',
    'websockets',
    'zoneinfo',
]

# ============ 排除英伟达/CUDA ============
excludes = [
    'nvidia',
    'nvidia.cublas',
    'nvidia.cuda_cupti',
    'nvidia.cuda_nvrtc',
    'nvidia.cuda_runtime',
    'nvidia.cudnn',
    'nvidia.cufft',
    'nvidia.curand',
    'nvidia.cusolver',
    'nvidia.cusparse',
    'nvidia.nccl',
    'nvidia.nvjitlink',
    'nvidia.nvtx',
    'triton',
    'torch.cuda',
    'matplotlib',
    'PIL',
    'scipy',
    'pandas',
    'tkinter',
    'unittest',
    'test',
    'setuptools',
    'pip',
]

a = Analysis(
    ['run_server.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ICU-Alert-System',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ICU-Alert-System',
)
