"""Tipos de columna con semantica explicita sobre PostgreSQL."""

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import DateTime, Numeric
from sqlalchemy.types import TypeDecorator


class ExactNumeric(TypeDecorator):
    """NUMERIC(precision, scale) leido y escrito como Decimal (AUDITORIA BD-02).

    PostgreSQL redondea al guardar un valor con mas decimales que la escala (10.005 -> 10.01). Aqui ese valor se
    rechaza antes de enviarlo: la persistencia nunca redondea en silencio.
    """

    impl = Numeric
    cache_ok = True

    def __init__(self, precision: int, scale: int):
        super().__init__(precision=precision, scale=scale, asdecimal=True)
        self.precision = precision
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
        return amount


def to_money(value: Decimal) -> Decimal:
    """Redondeo explicito a centavos (ROUND_HALF_UP) para importes de origen externo, como el XML del CFDI."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def Money() -> ExactNumeric:  # noqa: N802 - se usa como un tipo de columna
    """Importe monetario: NUMERIC(16, 2)."""
    return ExactNumeric(16, 2)


class UTCDateTime(TypeDecorator):
    """TIMESTAMPTZ normalizado a UTC.

    Al escribir, un valor naive se interpreta como UTC y uno con otra zona se convierte; al leer siempre se devuelve
    con tzinfo=UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
