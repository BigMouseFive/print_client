"""API 请求/响应模型"""

from pydantic import AliasChoices, BaseModel, Field


class FnskuPrintRequest(BaseModel):
    fnsku: str
    sku: str
    msku_shipping: str = Field(
        default="made in china",
        validation_alias=AliasChoices("msku_shipping", "origin"),
    )
    copies: int = 1


class FnskuBatchItem(BaseModel):
    fnsku: str
    sku: str
    msku_shipping: str = Field(
        default="made in china",
        validation_alias=AliasChoices("msku_shipping", "origin"),
    )
    copies: int = 1


class PrintResponse(BaseModel):
    status: str
    message: str | None = None
