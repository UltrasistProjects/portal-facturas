## Why

La ERS v1.3 (glosario, 2.4, 2.5, RF-03, 3.3, 3.4 y 3.5), la HU-03 y la validación de HUs nombran "ClickCloud" (también "ClickCloude") como un **gestor de secretos** donde se resguardaría la contraseña temporal del proveedor (RN-HU03-01). Es un error de transcripción originado en notas de trabajo: el componente real es **Keycloak**, y Keycloak no es un gestor de secretos sino un **proveedor de identidad (IdP)**, un servidor de autenticación OIDC que gestiona las cuentas y sus credenciales.

El error no es sólo de nombre. Llevó a diseñar HU-03 alrededor de un "resguardo" de la contraseña: `app/services/secret_vault.py`, con un adaptador nulo a la espera de una API de ClickCloud que no existe. Hay que corregir el concepto en las fuentes de verdad antes de rediseñar la autenticación (`add-keycloak-authentication`).

## What Changes

- **ERS → v1.4:** se reescriben las 8 frases afectadas al concepto correcto (no basta con cambiar el nombre), se reformula RN-HU03-01 y se agrega la fila 1.4 al control de versiones.
- **RN-HU03-01 corregida:** "Las credenciales del proveedor, incluida la contraseña temporal, se gestionan exclusivamente en el proveedor de identidad (Keycloak); el sistema de proveedores no almacena contraseñas ni sus hashes."
- **Spec `acceso-proveedores`:** el requirement "Usuario y contraseña temporal al autorizar" deja de hablar de un "gestor de secretos" y nombra el punto de integración con el proveedor de identidad. El comportamiento no cambia en este cambio.
- **Documentación y comentarios del código:** `README.md`, EP-01, docstrings de `secret_vault.py` y `supplier_access_service.py`, y el nombre y los mensajes de las pruebas que dicen "gestor de secretos".
- **Sin cambios de comportamiento en el código.** El punto de integración `secret_vault` se conserva con su adaptador nulo; lo sustituye el aprovisionamiento en Keycloak de `add-keycloak-authentication`.

**Fuera de alcance:**
- los cambios archivados en `openspec/changes/archive/` y los documentos de `docs/superseded/`: son registro histórico, se conservan como se escribieron;
- que el portal deje de guardar el hash (la parte de comportamiento de RN-HU03-01 corregida): la implementa `add-keycloak-authentication`.

## Capabilities

### New Capabilities
<!-- Ninguna. -->

### Modified Capabilities
- `acceso-proveedores`: el requirement "Usuario y contraseña temporal al autorizar" cambia "gestor de secretos" por "proveedor de identidad (Keycloak)" en su texto y en su escenario de resguardo.

## Impact

- **Documentos:** `docs/source-of-truth/ERS_Portal_Proveedores_ULTRASIST_MVP.docx` (v1.3 → v1.4), `docs/stories/epics/EP-01 Acceso y gestion de facturas del proveedor.md`.
- **PoC** (rutas relativas a `PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress-V1/PoC_Ultra_ProyectoInternoFacturas-JEVG-Compress/`): `README.md`, `app/services/secret_vault.py` y `app/services/supplier_access_service.py` (sólo docstrings), `tests/test_acceso_proveedores.py` (nombre del test y mensajes).
- **Spec:** `openspec/specs/acceso-proveedores/spec.md` al archivar.
- **Código, esquema y dependencias:** sin cambios.
