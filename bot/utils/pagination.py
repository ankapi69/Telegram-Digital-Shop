from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class Page(Generic[T]):
    items: list[T]
    page: int  # 1-based
    pages: int
    total: int


def paginate(items: list[T], page: int, per_page: int) -> Page[T]:
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, pages))
    start = (page - 1) * per_page
    return Page(items=items[start : start + per_page], page=page, pages=pages, total=total)
