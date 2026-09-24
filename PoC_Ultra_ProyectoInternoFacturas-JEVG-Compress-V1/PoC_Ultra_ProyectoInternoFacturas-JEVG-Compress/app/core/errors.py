"""Excepciones de dominio. Un handler global las traduce a respuestas HTTP 4xx."""


class BusinessRuleError(Exception):
    """Violacion de una regla de negocio provocada por la accion del usuario."""

    status_code = 409

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidTransitionError(BusinessRuleError, ValueError):
    """Transicion de estado no permitida por ALLOWED_TRANSITIONS."""


class DuplicateInvoiceError(BusinessRuleError):
    """La factura viola una restriccion de unicidad fiscal (UUID o numero por proveedor)."""


class InvalidInputError(BusinessRuleError):
    """Dato de entrada invalido para la operacion (p. ej. una decision de revision desconocida)."""

    status_code = 400
