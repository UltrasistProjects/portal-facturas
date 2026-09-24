"""Cuentas demo: unica fuente para el seed y el acceso rapido del login. Solo se exponen en development."""

from dataclasses import dataclass

DEMO_EMAIL_DOMAIN = "@poc.local"


@dataclass(frozen=True)
class DemoAccount:
    label: str
    email: str
    password: str
    quick_access: bool = True


DEMO_ACCOUNTS = (
    DemoAccount("Administrador", "admin@poc.local", "Admin#Demo2026"),
    DemoAccount("PMO", "pmo@poc.local", "Pmo#Demo2026"),
    DemoAccount("Proveedor", "proveedor1@poc.local", "Proveedor#Demo2026"),
    DemoAccount("Proveedor fisico", "proveedor2@poc.local", "Proveedor#Demo2026", quick_access=False),
)


def quick_access_accounts(app_env: str) -> list[DemoAccount]:
    return [account for account in DEMO_ACCOUNTS if account.quick_access] if app_env == "development" else []
