"""Cuentas demo: unica fuente para el seed. Sus contrasenas no estan en el repositorio: en development el seed usa
DEMO_PASSWORD del .env y en otro entorno genera temporales que muestra una sola vez (add-keycloak-authentication)."""

from dataclasses import dataclass

from app.core.constants import Role

DEMO_EMAIL_DOMAIN = "@poc.local"


@dataclass(frozen=True)
class DemoAccount:
    label: str
    email: str
    role: Role


DEMO_ACCOUNTS = (
    DemoAccount("Administrador", "admin@poc.local", Role.ADMINISTRADOR),
    DemoAccount("PMO", "pmo@poc.local", Role.PMO),
    DemoAccount("Proveedor", "proveedor1@poc.local", Role.PROVEEDOR),
    DemoAccount("Proveedor fisico", "proveedor2@poc.local", Role.PROVEEDOR),
    # Proveedor internacional (HU-15/16): factura con Invoice en PDF, sin CFDI.
    DemoAccount("Proveedor internacional", "proveedor3@poc.local", Role.PROVEEDOR),
)
