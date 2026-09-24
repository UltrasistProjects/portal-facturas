from app.core.timeutils import to_business
from app.rules.base import outcome


def date_rules(invoice):
    # El corte del dia 20 es un plazo de negocio en hora local, no en UTC (AUDITORIA BD-10).
    received_day = to_business(invoice.created_at).day if invoice.created_at else 1
    return [
        outcome(
            "DAT-001",
            "DAT",
            received_day <= 20,
            "WARNING",
            "Factura recibida dentro de la fecha preferente",
            "Factura recibida despues de la fecha preferente. Puede programarse para el siguiente ciclo.",
            "Dia 1 al 20",
            received_day,
            warning=True,
        )
    ]
