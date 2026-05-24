"""API 请求/响应模型"""

from pydantic import BaseModel


class FnskuPrintRequest(BaseModel):
    fnsku: str
    sku: str
    origin: str = "made in china"
    copies: int = 1


class FnskuBatchItem(BaseModel):
    fnsku: str
    sku: str
    origin: str = "made in china"
    copies: int = 1


class PrintResponse(BaseModel):
    status: str
    message: str | None = None
