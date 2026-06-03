"""BrAPI v2.1 response-envelope helpers.

Every BrAPI response is `{"metadata": {...}, "result": {...}}`. List endpoints
put rows under `result.data` with a `pagination` block; single-record endpoints
put the object directly under `result`. See https://brapi.org (v2.1 core).
"""
from __future__ import annotations

from typing import Any

_OK = "Request accepted, response successful"


def _pagination(page: int, page_size: int, total: int) -> dict:
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return {
        "currentPage": page,
        "pageSize": page_size,
        "totalCount": total,
        "totalPages": total_pages,
    }


def _metadata(pagination: dict, message: str = _OK) -> dict:
    return {
        "datafiles": [],
        "status": [{"messageType": "INFO", "message": message}],
        "pagination": pagination,
    }


def page(data: list[Any], page_num: int, page_size: int, total: int, message: str = _OK) -> dict:
    """Envelope for a list/search endpoint."""
    return {"metadata": _metadata(_pagination(page_num, page_size, total), message),
            "result": {"data": data}}


def single(result: dict, message: str = _OK) -> dict:
    """Envelope for a single-record endpoint."""
    return {"metadata": _metadata(_pagination(0, 1, 1), message), "result": result}
