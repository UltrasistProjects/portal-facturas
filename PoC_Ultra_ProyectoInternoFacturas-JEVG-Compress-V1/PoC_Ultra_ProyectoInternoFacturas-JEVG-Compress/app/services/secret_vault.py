"""Resguardo de la contrasena temporal del proveedor en el gestor de secretos (HU-03, RN-HU03-01: ClickCloud).

El portal nunca guarda la contrasena temporal en claro: solo su hash Argon2 en users.password_hash. RN-HU03-01 pide
resguardarla en ClickCloud; mientras no se tengan su API y sus credenciales, el adaptador activo es NullSecretVault, que
no guarda nada. Un adaptador real implementa `store_temporary_password` y se devuelve en `get_vault()`. Se llama
antes de confirmar la autorizacion: si falla, la autorizacion se revierte (D6).
"""

from typing import Protocol


class SecretVault(Protocol):
    name: str

    def store_temporary_password(self, *, supplier_id: int, username: str, password: str) -> None: ...


class NullSecretVault:
    """Adaptador sin gestor de secretos: no guarda nada."""

    name = "none"

    def store_temporary_password(self, *, supplier_id: int, username: str, password: str) -> None:
        return None


def get_vault() -> SecretVault:
    return NullSecretVault()
