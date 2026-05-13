# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None

app_imports = collect_submodules('app')
tzdata_imports = collect_submodules('tzdata')
torch_imports = collect_submodules('torch')
transformer_imports = collect_submodules('transformers')
chronos_imports = collect_submodules('chronos')
sentence_transformer_imports = collect_submodules('sentence_transformers')
tokenizer_imports = collect_submodules('tokenizers')
safetensors_imports = collect_submodules('safetensors')
huggingface_hub_imports = collect_submodules('huggingface_hub')
numpy_imports = collect_submodules('numpy')

def collect_pkg_datas(pkg_name, *, include_py_files=False):
    try:
        return collect_data_files(pkg_name, include_py_files=include_py_files)
    except TypeError:
        return collect_data_files(pkg_name)

datas = [
    ('static', 'static'),
    ('config.yaml', '.'),
    ('.env', '.'),
    ('knowledge_base', 'knowledge_base'),
]
datas += collect_pkg_datas('sentence_transformers', include_py_files=True)
datas += collect_pkg_datas('transformers', include_py_files=True)
datas += collect_pkg_datas('chronos', include_py_files=True)
datas += collect_pkg_datas('tokenizers', include_py_files=True)
datas += collect_pkg_datas('safetensors')
datas += collect_pkg_datas('huggingface_hub')
datas += collect_data_files('torch')
datas += collect_data_files('tzdata')
datas += collect_data_files('numpy')

binaries = []
binaries += collect_dynamic_libs('torch')
binaries += collect_dynamic_libs('numpy')

hidden_imports = (
    app_imports
    + tzdata_imports
    + torch_imports
    + transformer_imports
    + chronos_imports
    + sentence_transformer_imports
    + tokenizer_imports
    + safetensors_imports
    + huggingface_hub_imports
    + numpy_imports
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
        'chronos',
        'tokenizers',
        'numpy',
        'numpy._core',
        'numpy._core._exceptions',
        'numpy._core._multiarray_tests',
        'numpy._core._multiarray_umath',
        'numpy.linalg',
        'numpy.linalg.lapack_lite',
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
