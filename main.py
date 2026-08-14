"""佳博打印代理服务 - FastAPI 跨平台版"""

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

try:
    from . import config
    from .api.routes import router
    from .registrar import ErpRegistrar
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import config
    from api.routes import router
    from registrar import ErpRegistrar

logger = logging.getLogger("print_client")

PORT = config.PORT


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时向 ERP 自注册（ERP_URL 为空则不启用）
    registrar = None
    if config.ERP_URL:
        registrar = ErpRegistrar(
            erp_url=config.ERP_URL,
            port=config.PORT,
            token=config.ERP_TOKEN,
            node_name=config.PRINT_AGENT_NAME,
            interval=config.ERP_HEARTBEAT_INTERVAL,
            advertise_url=config.PRINT_AGENT_ADVERTISE_URL,
            prefer_prefixes=config.PRINT_AGENT_IP_PREFIXES,
            meta={
                "fnsku_printer": config.FNSKU_PRINTER,
                "box_printer": config.BOX_PRINTER,
                "platform": sys.platform,
                "version": config.VERSION,
            },
        )
        registrar.start()
    else:
        logger.info("未配置 ERP_URL，跳过 ERP 自注册")
    yield
    if registrar:
        registrar.stop()


app = FastAPI(title="佳博打印代理服务", version=config.VERSION, lifespan=lifespan)
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
    if sys.platform == "win32":
        platform_label = "Windows"
    elif sys.platform == "darwin":
        platform_label = "macOS (CUPS)"
    else:
        platform_label = "Linux (CUPS)"
    print(f"  平台：{platform_label}")
    print("=" * 52)
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
