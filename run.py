#!/usr/bin/env python3
"""启动脚本（处理相对导入，支持目录重命名）"""

import os
import sys

# 动态推导包名：run.py 所在目录的 basename
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_NAME = os.path.basename(PROJECT_DIR)
PROJECT_PARENT = os.path.dirname(PROJECT_DIR)

if PROJECT_PARENT not in sys.path:
    sys.path.insert(0, PROJECT_PARENT)

# 使用动态导入，避免包名硬编码
_app_module = __import__(f"{PACKAGE_NAME}.main", fromlist=["app"])
_config_module = __import__(f"{PACKAGE_NAME}.config", fromlist=["PORT"])

app = _app_module.app
PORT = _config_module.PORT


def _platform_label() -> str:
    if sys.platform == "win32":
        return "Windows"
    if sys.platform == "darwin":
        return "macOS (CUPS)"
    return "Linux (CUPS)"


if __name__ == "__main__":
    import uvicorn
    print("=" * 52)
    print("  佳博打印代理服务 (FastAPI)")
    print("=" * 52)
    print(f"  管理界面：http://localhost:{PORT}")
    print(f"  FNSKU 打印机：{os.environ.get('FNSKU_PRINTER', 'GP-1326D')}")
    print(f"  平台：{_platform_label()}")
    print("=" * 52)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
