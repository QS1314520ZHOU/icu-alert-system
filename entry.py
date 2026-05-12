"""
ICU智能预警系统 - 打包入口 (GPU 版)
基于项目原有 run_server.py 改写
"""
import multiprocessing
import sys
import os
import signal
import traceback
import subprocess


def get_base_path():
    """获取运行时基础路径"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resolve_runtime_path(*relative_parts):
    """优先使用 PyInstaller _MEIPASS 内资源，其次回退到程序目录。"""
    candidates = []
    base = get_base_path()
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        candidates.append(os.path.join(sys._MEIPASS, *relative_parts))
    candidates.append(os.path.join(base, *relative_parts))

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[0]


def setup_external_code_path():
    """Prefer source files placed next to the packaged launcher.

    The GPU package keeps the heavy Python/torch runtime frozen, but app code is
    copied to the deployment directory as app/. Putting the deployment root at
    the front of sys.path lets small source delta packages update backend code
    without rebuilding the large PyInstaller bundle.
    """
    base = get_base_path()
    external_app_dir = os.environ.get('ICU_EXTERNAL_APP_DIR', '').strip()
    external_root = os.path.dirname(external_app_dir) if external_app_dir else base
    external_app = external_app_dir or os.path.join(external_root, 'app')
    if os.path.isdir(external_app) and external_root not in sys.path:
        sys.path.insert(0, external_root)
        print(f"[ICU] 外置后端代码: {external_app}")


def load_dotenv_file():
    """加载 .env 文件"""
    base = get_base_path()
    search_paths = [
        os.environ.get('DOTENV_PATH', '').strip(),
        os.path.join(os.getcwd(), '.env'),
        os.path.join(base, '.env'),
    ]
    # frozen 模式下也检查 _internal
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        search_paths.append(os.path.join(sys._MEIPASS, '.env'))

    for env_path in search_paths:
        if os.path.isfile(env_path):
            print(f"[ICU] 加载配置文件: {env_path}")
            try:
                from dotenv import load_dotenv
                load_dotenv(env_path, override=False)
                return
            except ImportError:
                pass
            # 手动解析
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' not in line:
                        continue
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and not key.startswith('#'):
                        os.environ.setdefault(key, value)
            return
    print("[ICU] 警告: 未找到 .env 文件")


def setup_cuda_env():
    """配置 CUDA 环境"""
    if os.environ.get('FORCE_CPU', '').lower() in ('true', '1', 'yes'):
        os.environ['CUDA_VISIBLE_DEVICES'] = ''
        print("[ICU] FORCE_CPU=true, 已禁用 GPU")
        return

    base = get_base_path()
    internal = os.path.join(base, '_internal') if getattr(sys, 'frozen', False) else None

    lib_paths = []
    if internal and os.path.isdir(internal):
        lib_paths.append(internal)
        for relative in [
            os.path.join('torch', 'lib'),
            os.path.join('onnxruntime', 'capi'),
        ]:
            candidate = os.path.join(internal, relative)
            if os.path.isdir(candidate):
                lib_paths.append(candidate)
        nvidia_root = os.path.join(internal, 'nvidia')
        if os.path.isdir(nvidia_root):
            for name in os.listdir(nvidia_root):
                candidate = os.path.join(nvidia_root, name, 'lib')
                if os.path.isdir(candidate):
                    lib_paths.append(candidate)

    for d in ['/usr/local/cuda/lib64', '/usr/local/cuda-12.1/lib64', '/usr/lib/x86_64-linux-gnu']:
        if d and os.path.isdir(d):
            lib_paths.append(d)

    if lib_paths:
        existing = [p for p in os.environ.get('LD_LIBRARY_PATH', '').split(':') if p]
        merged = []
        for path in lib_paths + existing:
            if path not in merged:
                merged.append(path)
        os.environ['LD_LIBRARY_PATH'] = ':'.join(merged)


def check_gpu():
    """检查 GPU 状态。

    打包环境下避免在应用导入前主动 import torch/onnxruntime，
    否则更容易触发 PyInstaller 二进制扩展的重复加载问题。
    """
    if os.environ.get('FORCE_CPU', '').lower() in ('true', '1', 'yes'):
        print("[ICU] GPU 预检: 已显式禁用 (FORCE_CPU=true)")
        return
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader'],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            print("[ICU] GPU 预检:")
            for line in result.stdout.strip().splitlines():
                print(f"[ICU]   {line}")
        else:
            print("[ICU] GPU 预检: 未检测到可用 GPU 或 nvidia-smi 不可用，运行时将按需回退 CPU")
    except Exception as e:
        print(f"[ICU] GPU 预检失败: {e}")


def import_self_test():
    """Fail the packaged binary early if bundled ML imports are broken."""
    required_checks = [
        ("torch", "import torch; print('torch', torch.__version__, 'cuda', getattr(torch.version, 'cuda', None))"),
    ]
    failed = False
    for name, code in required_checks:
        try:
            namespace = {}
            exec(code, namespace, namespace)
        except Exception as exc:
            failed = True
            print(f"[ICU][SELFTEST] {name} import failed: {exc.__class__.__name__}: {exc}")
            print(traceback.format_exc())
    if failed:
        sys.exit(86)
    print("[ICU][SELFTEST] packaged torch import OK")


def graceful_shutdown(signum, frame):
    print(f"\n[ICU] 收到信号 {signum}, 正在关闭...")
    sys.exit(0)


if __name__ == '__main__':
    multiprocessing.freeze_support()

    # PyInstaller 打包后的路径修正
    BASE_DIR = get_base_path()
    os.environ.setdefault('ICU_APP_ROOT', BASE_DIR)
    os.environ.setdefault('ICU_CONFIG_PATH', resolve_runtime_path('config.yaml'))
    os.environ.setdefault('ICU_FRONTEND_DIR', resolve_runtime_path('static'))
    os.environ.setdefault('DOTENV_PATH', os.path.join(BASE_DIR, '.env'))
    if getattr(sys, 'frozen', False):
        os.chdir(BASE_DIR)

    # 加载配置
    load_dotenv_file()

    # 设置 CUDA
    setup_cuda_env()

    # 优先加载部署目录中的外置 app/，支持后续小体积源码增量更新。
    setup_external_code_path()

    if os.environ.get('ICU_IMPORT_SELF_TEST', '').lower() in ('1', 'true', 'yes'):
        import_self_test()
        sys.exit(0)

    # 信号处理
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    # 读取配置
    host = os.environ.get('ICU_HOST', '0.0.0.0')
    port = int(os.environ.get('ICU_PORT', '8000'))
    workers = int(os.environ.get('ICU_WORKERS', '1'))
    log_level = os.environ.get('LOG_LEVEL', 'info')

    print("=" * 55)
    print("  ICU 智能预警系统 正在启动...")
    print(f"  工作目录: {BASE_DIR}")
    print(f"  监听地址: http://{host}:{port}")
    print(f"  Workers:  {workers}")
    print("=" * 55)

    # 检查 GPU
    check_gpu()

    # 导入 app
    try:
        from app.main import app as application
    except ImportError as e:
        print(f"[ICU] 导入失败: {e}")
        print(traceback.format_exc())
        print(f"[ICU] sys.path = {sys.path}")
        print(f"[ICU] 当前目录内容: {os.listdir(BASE_DIR)}")
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            print(f"[ICU] _MEIPASS 内容: {os.listdir(sys._MEIPASS)[:20]}")
        sys.exit(1)

    # 挂载前端静态文件
    try:
        from fastapi.staticfiles import StaticFiles
        from starlette.responses import FileResponse

        static_dir = None
        for candidate in ['static', os.path.join(BASE_DIR, 'static')]:
            if os.path.isdir(candidate):
                static_dir = candidate
                break

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            meipass_static = os.path.join(sys._MEIPASS, 'static')
            if os.path.isdir(meipass_static) and static_dir is None:
                static_dir = meipass_static

        if static_dir:
            application.mount("/static", StaticFiles(directory=static_dir), name="static")
            index_html = os.path.join(static_dir, 'index.html')
            if os.path.isfile(index_html):
                from starlette.middleware.base import BaseHTTPMiddleware
                from starlette.requests import Request

                class SPAFallback(BaseHTTPMiddleware):
                    async def dispatch(self, request: Request, call_next):
                        response = await call_next(request)
                        path = request.url.path
                        if (response.status_code == 404
                                and not path.startswith(('/api/', '/ws', '/health', '/docs', '/openapi', '/static/', '/assets/'))
                                and path not in ('/manifest.webmanifest', '/sw.js', '/registerSW.js')):
                            return FileResponse(index_html)
                        return response

                application.add_middleware(SPAFallback)
                print(f"[ICU] 前端静态文件: {static_dir} (SPA 模式)")
            else:
                print(f"[ICU] 前端静态文件: {static_dir}")
        else:
            print("[ICU] 警告: 未找到 static 目录，前端页面不可用")
    except Exception as e:
        print(f"[ICU] 静态文件挂载失败: {e}")

    # 启动
    import uvicorn
    uvicorn.run(
        application,
        host=host,
        port=port,
        workers=workers,
        log_level=log_level,
    )
