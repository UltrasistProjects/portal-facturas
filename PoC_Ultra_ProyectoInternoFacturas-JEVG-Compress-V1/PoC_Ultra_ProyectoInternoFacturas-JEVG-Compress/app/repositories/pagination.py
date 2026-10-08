from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil
from typing import Generic, TypeVar
from urllib.parse import urlencode

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

T = TypeVar("T")
# Registros por pagina de los listados (listados-paginados); el Audit Log usa 50.
PER_PAGE = 25


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


def paginate(db: Session, stmt: Select, page: int, per_page: int = PER_PAGE) -> Page:
    """Pagina en SQL (LIMIT/OFFSET); una pagina fuera de rango se ajusta a la ultima existente."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    page = min(max(1, page), max(1, ceil(total / per_page)))
    items = list(db.scalars(stmt.limit(per_page).offset((page - 1) * per_page)).unique())
    return Page(items, page, per_page, total)


def escape_like(value: str) -> str:
    """% y _ se buscan como caracteres literales."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search(stmt: Select, q: str, *columns) -> Select:
    """Busqueda sin distinguir mayusculas en cualquiera de las columnas; sin texto, la consulta no cambia."""
    text = (q or "").strip()
    if not text:
        return stmt
    pattern = f"%{escape_like(text)}%"
    return stmt.where(or_(*(column.ilike(pattern, escape="\\") for column in columns)))


def list_query(**params) -> str:
    """Cadena de consulta con los parametros no vacios, para la paginacion y las redirecciones."""
    return urlencode({key: value for key, value in params.items() if value not in (None, "")})


# Lo unico que una accion en una fila conserva del listado desde el que se hizo (listados-paginados, D4).
RETURN_KEYS = ("q", "status", "page")


def back_to(url: str, form: Mapping[str, str]) -> str:
    """URL del listado con la busqueda, el filtro y la pagina del formulario; cualquier otra clave se ignora."""
    values = {key: str(form.get(key) or "").strip() for key in RETURN_KEYS}
    if not values["page"].isdigit() or values["page"] in {"0", "1"}:
        values["page"] = ""
    query = list_query(**values)
    return f"{url}?{query}" if query else url
