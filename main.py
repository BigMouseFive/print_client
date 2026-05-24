"""佳博打印代理服务 - FastAPI 跨平台版"""

import os
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import PORT
from .api.routes import router

app = FastAPI(title="佳博打印代理服务", version="2.0.0")
app.include_router(router)

# 静态文件（Web 管理界面）
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def index():
    html_path = os.path.join(static_dir, "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return {"message": "佳博打印代理服务运行中"}


@app.get("/app.js")
def serve_js():
    js_path = os.path.join(static_dir, "app.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    return {"message": "JS not found"}


if __name__ == "__main__":
    import uvicorn
    print("=" * 52)
    print("  佳博打印代理服务 (FastAPI)")
    print("=" * 52)
    print(f"  管理界面：http://localhost:{PORT}")
    print(f"  FNSKU 打印机：{os.environ.get('FNSKU_PRINTER', 'GP-1326D')}")
    print(f"  平台：{'Windows' if sys.platform == 'win32' else 'Linux (CUPS)'}")
    print("=" * 52)
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
