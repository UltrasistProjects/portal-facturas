from app.rules.base import outcome


def date_rules(invoice):
    received_day = invoice.created_at.day if invoice.created_at else 1
    return [outcome("DAT-001", "DAT", received_day <= 20, "WARNING", "Factura recibida dentro de la fecha preferente", "Factura recibida despues de la fecha preferente. Puede programarse para el siguiente ciclo.", "Dia 1 al 20", received_day, warning=True)]

