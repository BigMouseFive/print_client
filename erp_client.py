"""
ERP 打印客户端（运行在 Ubuntu ERP 服务器上）
调用 Windows 打印代理完成实际打印。

无需额外依赖（使用 Python 内置 urllib）。
"""

import json
import urllib.request
import urllib.error
import os

# ── 配置：改为 Windows 电脑的局域网 IP ───────────────
PRINT_AGENT_URL = "http://192.168.1.100:5050"
# ─────────────────────────────────────────────────────


def print_fnsku_label(fnsku: str, sku: str, msku_shipping: str, copies: int = 1) -> None:
    """打印单张 FNSKU 商品标签"""
    payload = json.dumps({
        "fnsku": fnsku,
        "sku": sku,
        "msku_shipping": msku_shipping,
        "copies": copies,
    }).encode("utf-8")
    req = urllib.request.Request(
        url=f"{PRINT_AGENT_URL}/print/fnsku",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    _do_request(req)


def print_fnsku_batch(items: list[dict]) -> list[dict]:
    """
    批量打印 FNSKU 标签（一次 HTTP 请求，效率更高）

    items 格式：
        [
            {"fnsku": "X002JGSKY9", "sku": "GS7978", "msku_shipping": "FBA-*KSA9  HAI", "copies": 2},
            ...
        ]

    返回每条结果：[{"fnsku": "...", "status": "ok"}, ...]
    """
    payload = json.dumps(items).encode("utf-8")
    req = urllib.request.Request(
        url=f"{PRINT_AGENT_URL}/print/fnsku/batch",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
        return result.get("results", [])


def print_box_label(pdf_path: str, copies: int = 1) -> None:
    """
    打印外箱标签（将 PDF 文件内容发送给 Windows 打印代理）

    pdf_path: PDF 在 Ubuntu 服务器上的路径，如 "/data/labels/box.pdf"
    """
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    req = urllib.request.Request(
        url=f"{PRINT_AGENT_URL}/print/box?copies={copies}",
        data=pdf_bytes,
        headers={"Content-Type": "application/pdf"},
        method="POST",
    )
    _do_request(req)


def check_printer_online() -> bool:
    """检查 Windows 打印代理是否在线"""
    try:
        req = urllib.request.Request(f"{PRINT_AGENT_URL}/ping")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _do_request(req: urllib.request.Request) -> None:
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("status") != "ok":
                raise RuntimeError(f"打印失败：{result.get('message')}")
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"无法连接打印代理（{PRINT_AGENT_URL}），请确认 Windows 打印服务已启动。\n错误：{e}"
        )


# ── FastAPI 路由集成（粘贴到对应路由文件）─────────────────────
"""
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from print_client import print_fnsku_label, print_fnsku_batch, print_box_label

router = APIRouter(prefix="/api/labels", tags=["labels"])

class FnskuReq(BaseModel):
    fnsku: str
    sku: str
    msku_shipping: str
    copies: int = 1

@router.post("/fnsku")
def api_print_fnsku(req: FnskuReq):
    try:
        print_fnsku_label(req.fnsku, req.sku, req.msku_shipping, req.copies)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/fnsku/batch")
def api_print_fnsku_batch(items: list[FnskuReq]):
    try:
        results = print_fnsku_batch([i.dict() for i in items])
        return {"status": "ok", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/box")
async def api_print_box(file: UploadFile = File(...), copies: int = 1):
    import tempfile, os
    content = await file.read()
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(content); tmp.close()
    try:
        print_box_label(tmp.name, copies)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp.name)
"""
