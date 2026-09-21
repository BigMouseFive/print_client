"""佳博打印代理服务 - FastAPI 跨平台版"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

try:
    from . import config
    from .api.routes import router
    from .mdns import MdnsPublisher, load_or_create_service_id, start_publisher_async, stop_publisher_async
    from .registrar import ErpRegistrar
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import config
    from api.routes import router
    from mdns import MdnsPublisher, load_or_create_service_id, start_publisher_async, stop_publisher_async
    from registrar import ErpRegistrar

logger = logging.getLogger("print_client")

PORT = config.PORT


@asynccontextmanager
async def lifespan(app: FastAPI):
    publisher = None
    registrar = None

    if config.MDNS_ENABLED:
        service_id = load_or_create_service_id(Path(config.MDNS_IDENTITY_PATH))
        publisher = MdnsPublisher(
            service_id=service_id,
            port=config.PORT,
            instance_name=config.MDNS_INSTANCE_NAME,
            advertise_address=config.MDNS_ADVERTISE_ADDRESS,
        )
        # zeroconf registration is synchronous and may wait on the network;
        # never run it directly on the ASGI event loop.
        await start_publisher_async(publisher)
        app.state.service_id = service_id
        logger.info("mDNS print-agent discovery enabled")
    else:
        app.state.service_id = None
        logger.info("mDNS discovery disabled")

    # Legacy ERP heartbeat remains available as an explicit opt-in. In mDNS
    # mode it is disabled by default, so ERP_URL is not required.
    if config.ERP_URL and config.ERP_REGISTRATION_ENABLED:
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
        logger.info("未启用 ERP 自注册")
    try:
        yield
    finally:
        if registrar:
            registrar.stop()
        if publisher:
            await stop_publisher_async(publisher)


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
