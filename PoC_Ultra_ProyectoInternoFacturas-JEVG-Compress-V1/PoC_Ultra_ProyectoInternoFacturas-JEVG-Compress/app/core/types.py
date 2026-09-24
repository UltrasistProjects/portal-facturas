"""Tipos de columna con semantica explicita que SQLite no ofrece de forma nativa."""

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import DateTime, Integer
from sqlalchemy.types import TypeDecorator


class ScaledDecimal(TypeDecorator):
    """Decimal exacto almacenado como entero escalado (p. ej. centavos): SQLite no tiene tipo decimal y guarda
    Numeric como REAL (AUDITORIA BD-02). La aplicacion sigue leyendo y escribiendo Decimal.

    Un valor con mas decimales que la escala se rechaza: la persistencia nunca redondea en silencio.
    """

    impl = Integer
    cache_ok = True

    def __init__(self, scale: int):
        super().__init__()
        self.scale = scale

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
        if not amount.is_finite():
            raise ValueError(f"Valor no finito: {value}")
        scaled = amount.scaleb(self.scale)
        if scaled != scaled.to_integral_value():
            raise ValueError(f"{amount} tiene mas de {self.scale} decimales; redondee explicitamente antes de guardar")
        return int(scaled)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Decimal(int(value)).scaleb(-self.scale)


def to_money(value: Decimal) -> Decimal:
    """Redondeo explicito a centavos (ROUND_HALF_UP) para importes de origen externo, como el XML del CFDI."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def Money() -> ScaledDecimal:  # noqa: N802 - se usa como un tipo de columna
    """Importe monetario en centavos."""
    return ScaledDecimal(2)


class UTCDateTime(TypeDecorator):
    """Fecha-hora normalizada a UTC al escribir y devuelta con tzinfo=UTC al leer.

    SQLite no guarda el offset: sin esto, DateTime(timezone=True) devuelve valores naive.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
