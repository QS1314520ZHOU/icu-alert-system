"""
ICU智能预警系统 - EXE 入口
"""
import multiprocessing
import sys
import os

# PyInstaller 打包后的路径修正
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    os.chdir(BASE_DIR)
    os.environ.setdefault('DOTENV_PATH', os.path.join(BASE_DIR, '.env'))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if __name__ == '__main__':
    multiprocessing.freeze_support()

    # 直接导入 app 对象，不用字符串
    from app.main import app as application

    import uvicorn
    print("=" * 50)
    print("  ICU智能预警系统 正在启动...")
    print(f"  工作目录: {BASE_DIR}")
    print("  访问地址: http://127.0.0.1:8000")
    print("=" * 50)

    uvicorn.run(
        application,        # 直接传对象，不是字符串
        host="0.0.0.0",
        port=8000,
        workers=1,
        log_level="info",
    )
