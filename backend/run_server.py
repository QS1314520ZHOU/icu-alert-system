"""
ICU智能预警系统 - EXE 入口
"""
import multiprocessing
import os
import socket
import sys

from dotenv import load_dotenv


def _load_runtime_env(base_dir: str) -> None:
    candidates = []
    internal_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(internal_env):
        candidates.append(internal_env)

    external_env = os.path.join(base_dir, ".env")
    if os.path.exists(external_env):
        candidates.append(external_env)

    explicit_path = os.environ.get("DOTENV_PATH", "").strip()
    if explicit_path and os.path.exists(explicit_path):
        candidates.append(explicit_path)

    seen = set()
    for path in candidates:
        normalized = os.path.abspath(path)
        if normalized in seen:
            continue
        load_dotenv(normalized, override=True)
        seen.add(normalized)


def _get_runtime_host() -> str:
    return os.environ.get("APP_HOST", "0.0.0.0").strip() or "0.0.0.0"


def _get_runtime_port() -> int:
    raw = os.environ.get("APP_PORT") or os.environ.get("PORT") or "8000"
    try:
        port = int(raw)
    except ValueError as exc:
        raise SystemExit(f"Invalid APP_PORT/PORT value: {raw}") from exc
    if not 1 <= port <= 65535:
        raise SystemExit(f"APP_PORT out of range: {port}")
    return port


def _get_access_url(host: str, port: int) -> str:
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def _show_windows_error(message: str, title: str = "ICU Alert") -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    except Exception:
        pass


def _ensure_port_available(host: str, port: int) -> None:
    test_host = "0.0.0.0" if host in {"0.0.0.0", "::"} else host
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((test_host, port))
    except OSError as exc:
        message = (
            f"Port {port} is already in use.\n"
            f"Edit APP_PORT in the .env file next to the EXE and try again."
        )
        print(message)
        _show_windows_error(message)
        raise SystemExit(1) from exc
    finally:
        sock.close()

# PyInstaller 打包后的路径修正
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    os.chdir(BASE_DIR)
    os.environ.setdefault('ICU_APP_ROOT', BASE_DIR)
    os.environ.setdefault('ICU_CONFIG_PATH', os.path.join(BASE_DIR, 'config.yaml'))
    os.environ.setdefault('ICU_FRONTEND_DIR', os.path.join(BASE_DIR, 'static'))
    os.environ.setdefault('DOTENV_PATH', os.path.join(BASE_DIR, '.env'))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    os.environ.setdefault('ICU_APP_ROOT', BASE_DIR)
    os.environ.setdefault('ICU_CONFIG_PATH', os.path.join(BASE_DIR, 'config.yaml'))
    os.environ.setdefault('ICU_FRONTEND_DIR', os.path.join(BASE_DIR, 'static'))

_load_runtime_env(BASE_DIR)

if __name__ == '__main__':
    multiprocessing.freeze_support()
    host = _get_runtime_host()
    port = _get_runtime_port()
    _ensure_port_available(host, port)

    # 直接导入 app 对象，不用字符串
    from app.main import app as application

    import uvicorn
    print("=" * 50)
    print("  ICU智能预警系统 正在启动...")
    print(f"  工作目录: {BASE_DIR}")
    print(f"  访问地址: {_get_access_url(host, port)}")
    print("=" * 50)

    uvicorn.run(
        application,        # 直接传对象，不是字符串
        host=host,
        port=port,
        workers=1,
        log_level="info",
    )
