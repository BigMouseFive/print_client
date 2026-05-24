#!/usr/bin/env python3
"""启动脚本（处理相对导入）"""

import sys
import os

# 将父目录加入路径，使 print_agent 能被作为包导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from print_agent.main import app
from print_agent.config import PORT

if __name__ == "__main__":
    import uvicorn
    print("=" * 52)
    print("  佳博打印代理服务 (FastAPI)")
    print("=" * 52)
    print(f"  管理界面：http://localhost:{PORT}")
    print(f"  FNSKU 打印机：{os.environ.get('FNSKU_PRINTER', 'GP-1326D')}")
    print(f"  平台：{'Windows' if sys.platform == 'win32' else 'Linux (CUPS)'}")
    print("=" * 52)
    uvicorn.run(app, host="0.0.0.0", port=PORT)
