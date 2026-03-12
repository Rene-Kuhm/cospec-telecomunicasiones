import math
from datetime import UTC, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ResponseMeta(BaseModel):
    timestamp: datetime
    version: str = "v1"


class ApiResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool = True
    data: T
    error: None = None
    meta: ResponseMeta

    @classmethod
    def ok(cls, data: T) -> "ApiResponse[T]":
        return cls(
            success=True,
            data=data,
            error=None,
            meta=ResponseMeta(timestamp=datetime.now(UTC)),
        )


class ErrorDetail(BaseModel):
    type: str
    code: str
    message: str
    trace_id: str
    timestamp: datetime


class ErrorResponse(BaseModel):
    success: bool = False
    data: None = None
    error: ErrorDetail
    meta: ResponseMeta


class PageMeta(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta

    @classmethod
    def of(cls, items: list[T], total: int, page: int, limit: int) -> "PaginatedResponse[T]":
        total_pages = max(1, math.ceil(total / limit)) if limit > 0 else 1
        return cls(
            items=items,
            meta=PageMeta(page=page, limit=limit, total=total, total_pages=total_pages),
        )
