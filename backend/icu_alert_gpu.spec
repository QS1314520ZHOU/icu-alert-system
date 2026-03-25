# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None

app_imports = collect_submodules('app')
tzdata_imports = collect_submodules('tzdata')
torch_imports = collect_submodules('torch')
transformer_imports = collect_submodules('transformers')
sentence_transformer_imports = collect_submodules('sentence_transformers')
tokenizer_imports = collect_submodules('tokenizers')

datas = [
    ('static', 'static'),
    ('config.yaml', '.'),
    ('.env', '.'),
    ('knowledge_base', 'knowledge_base'),
]
datas += collect_data_files('sentence_transformers')
datas += collect_data_files('transformers')
datas += collect_data_files('tokenizers')
datas += collect_data_files('torch')
datas += collect_data_files('tzdata')

binaries = []
binaries += collect_dynamic_libs('torch')

hidden_imports = (
    app_imports
    + tzdata_imports
    + torch_imports
    + transformer_imports
    + sentence_transformer_imports
    + tokenizer_imports
    + [
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
        'fastapi',
        'starlette.routing',
        'starlette.middleware',
        'starlette.middleware.cors',
        'pymongo',
        'redis',
        'redis.asyncio',
        'sentence_transformers',
        'torch',
        'torch.cuda',
        'torchvision',
        'torchaudio',
        'transformers',
        'tokenizers',
        'numpy',
        'httpx',
        'jose',
        'passlib',
        'bcrypt',
        'pydantic',
        'pydantic_settings',
        'yaml',
        'dotenv',
        'websockets',
        'zoneinfo',
    ]
)

excludes = [
    'matplotlib',
    'PIL',
    'tkinter',
    'unittest',
    'test',
    'pip',
]

a = Analysis(
    ['run_server.py'],
    pathex=['.'],
    binaries=binaries,
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
    name='ICU-Alert-System-GPU',
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
    name='ICU-Alert-System-GPU',
)
