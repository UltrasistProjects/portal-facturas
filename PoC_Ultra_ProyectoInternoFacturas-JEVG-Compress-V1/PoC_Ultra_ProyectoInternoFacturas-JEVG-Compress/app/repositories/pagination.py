from dataclasses import dataclass
from math import ceil
from typing import Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    page: int
    per_page: int
    total: int

    @property
    def pages(self) -> int:
        return max(1, ceil(self.total / self.per_page))

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages


def paginate(db: Session, stmt: Select, page: int, per_page: int) -> Page:
    """Pagina en SQL (LIMIT/OFFSET); una pagina fuera de rango se ajusta a la ultima existente."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    page = min(max(1, page), max(1, ceil(total / per_page)))
    items = list(db.scalars(stmt.limit(per_page).offset((page - 1) * per_page)).unique())
    return Page(items, page, per_page, total)
