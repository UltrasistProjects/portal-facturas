"""Entrega de la contrasena temporal del proveedor al proveedor de identidad (HU-03, RN-HU03-01: Keycloak).

El portal nunca guarda la contrasena temporal en claro: solo su hash Argon2 en users.password_hash. RN-HU03-01 pide
que las credenciales se gestionen en Keycloak, el proveedor de identidad (IdP). Punto de integracion provisional: el
adaptador activo es NullSecretVault, que no hace nada, hasta que lo sustituya el aprovisionamiento en Keycloak
(cambio add-keycloak-authentication). Se llama antes de confirmar la autorizacion: si falla, la autorizacion se
revierte (D6).
"""

from typing import Protocol


class SecretVault(Protocol):
    name: str

    def store_temporary_password(self, *, supplier_id: int, username: str, password: str) -> None: ...


class NullSecretVault:
    """Adaptador sin proveedor de identidad: no hace nada."""

    name = "none"

    def store_temporary_password(self, *, supplier_id: int, username: str, password: str) -> None:
        return None


def get_vault() -> SecretVault:
    return NullSecretVault()
