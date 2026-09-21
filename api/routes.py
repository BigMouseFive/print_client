"""FastAPI 路由（兼容原 Flask 端点路径）"""

import base64
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..config import FNSKU_PRINTER, BOX_PRINTER
from ..core.printer import get_printer
from ..core.pdf_generator import generate_fnsku_pdf
from ..core.pdf_cropper import resize_pdf_to_size
from .models import FnskuPrintRequest, FnskuBatchItem

router = APIRouter()
printer = get_printer()

# 内存日志
print_log: list[dict] = []


def _add_log(level: str, message: str) -> None:
    print_log.insert(0, {
        "time": datetime.now().strftime("%H:%M:%S"),
        "level": level,
        "message": message,
    })
    if len(print_log) > 100:
        print_log.pop()


@router.get("/ping")
def ping():
    return {"status": "ok", "printer": FNSKU_PRINTER}


@router.get("/.well-known/amazon-service")
def service_metadata(request: Request):
    """Stable service contract consumed by the LAN discovery agent."""
    return {
        "service_type": "print-agent",
        "service_id": getattr(request.app.state, "service_id", None),
        "api_version": 1,
        "endpoints": {
            "fnsku": "/print/fnsku",
            "fnsku_batch": "/print/fnsku/batch",
            "box": "/print/box",
            "readiness": "/v1/readiness",
        },
        "metadata_path": "/.well-known/amazon-service",
        "readiness_path": "/v1/readiness",
    }


@router.get("/v1/readiness")
def readiness():
    """Ready only when every configured print destination has a CUPS queue."""
    result = printer.readiness([FNSKU_PRINTER, BOX_PRINTER])
    return result


@router.get("/printers")
def list_printers():
    names = printer.list_printers()
    return {
        "status": "ok",
        "installed_printers": names,
        "config": {
            "FNSKU_PRINTER": FNSKU_PRINTER,
            "BOX_PRINTER": BOX_PRINTER,
        },
    }


@router.get("/logs")
def api_logs():
    return print_log


@router.post("/print/fnsku")
def api_fnsku(data: FnskuPrintRequest):
    try:
        pdf = generate_fnsku_pdf(data.fnsku, data.sku, data.msku_shipping)
        printer.print_pdf(pdf, FNSKU_PRINTER, data.copies, media_size="60x40mm")
        _add_log("ok", f"FNSKU {data.fnsku} x {data.copies}")
        return {"status": "ok"}
    except Exception as e:
        _add_log("err", str(e))
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.post("/print/fnsku/batch")
def api_fnsku_batch(items: list[FnskuBatchItem]):
    results, ok_count = [], 0
    for item in items:
        try:
            pdf = generate_fnsku_pdf(item.fnsku, item.sku, item.msku_shipping)
            printer.print_pdf(pdf, FNSKU_PRINTER, item.copies, media_size="60x40mm")
            results.append({"fnsku": item.fnsku, "status": "ok"})
            ok_count += 1
        except Exception as e:
            results.append({"fnsku": item.fnsku, "status": "error", "message": str(e)})
    _add_log("ok", f"批量打印 {ok_count}/{len(items)} 条 FNSKU")
    return {"status": "ok", "results": results}


@router.post("/print/box")
async def api_box(request: Request, copies: int = 1):
    try:
        pdf_bytes = await request.body()
        if not pdf_bytes:
            return JSONResponse(status_code=400, content={"status": "error", "message": "未收到 PDF 数据"})
        pdf_bytes = resize_pdf_to_size(pdf_bytes, 100, 100)
        printer.print_pdf(pdf_bytes, BOX_PRINTER, copies, media_size="100x100mm")
        _add_log("ok", f"外箱标签 x {copies}")
        return {"status": "ok"}
    except Exception as e:
        _add_log("err", str(e))
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.post("/preview/fnsku")
def api_preview_fnsku(data: FnskuPrintRequest):
    try:
        pdf = generate_fnsku_pdf(data.fnsku, data.sku, data.msku_shipping)
        return {"status": "ok", "pdf": base64.b64encode(pdf).decode("utf-8")}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.post("/preview/box")
async def api_preview_box(request: Request):
    try:
        pdf_bytes = await request.body()
        if not pdf_bytes:
            return JSONResponse(status_code=400, content={"status": "error", "message": "未收到 PDF 数据"})
        pdf = resize_pdf_to_size(pdf_bytes, 100, 100)
        return {"status": "ok", "pdf": base64.b64encode(pdf).decode("utf-8")}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
