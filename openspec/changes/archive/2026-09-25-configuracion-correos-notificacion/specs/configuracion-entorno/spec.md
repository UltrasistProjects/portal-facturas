## ADDED Requirements

### Requirement: Transporte de correo configurable por entorno
El transporte de correo SHALL configurarse con variables de entorno:
- `MAIL_BACKEND`: `smtp` o `file`; sin definir, `smtp` si `APP_ENV=production` y `file` en los demás entornos;
- `MAIL_FROM`: remitente de los correos; obligatorio con `smtp`, y con `file` toma por omisión "Portal de Proveedores ULTRASIST <no-reply@portal.local>";
- `MAIL_OUTBOX_DIR`: directorio donde el transporte `file` escribe cada correo como archivo `.eml`; por omisión `./outbox`, relativo a la raíz del proyecto;
- `SMTP_HOST`: obligatorio con `smtp`;
- `SMTP_PORT`: por omisión 587;
- `SMTP_SECURITY`: `starttls`, `ssl` o `none`; por omisión `starttls`;
- `SMTP_USERNAME` y `SMTP_PASSWORD`: opcionales; si hay usuario, el transporte inicia sesión;
- `SMTP_TIMEOUT`: segundos de espera, de 1 a 120; por omisión 10.

Un valor fuera de su dominio, o la falta de `SMTP_HOST` o `MAIL_FROM` con `smtp`, MUST impedir el arranque con un mensaje que nombre la variable. El transporte `file` MUST NOT enviar correos.

#### Scenario: Valores por omisión fuera de producción
- **WHEN** `APP_ENV=development` y no se define ninguna variable de correo
- **THEN** el transporte es `file`, el directorio de salida es `<raíz del proyecto>/outbox` y el remitente es "Portal de Proveedores ULTRASIST <no-reply@portal.local>"

#### Scenario: SMTP sin servidor
- **WHEN** `MAIL_BACKEND=smtp`, `MAIL_FROM` está definido y `SMTP_HOST` no
- **THEN** el arranque falla indicando que `SMTP_HOST` es obligatoria con `MAIL_BACKEND=smtp`

#### Scenario: SMTP sin remitente
- **WHEN** `MAIL_BACKEND=smtp`, `SMTP_HOST` está definido y `MAIL_FROM` no
- **THEN** el arranque falla indicando que `MAIL_FROM` es obligatoria con `MAIL_BACKEND=smtp`

#### Scenario: Cifrado desconocido
- **WHEN** `SMTP_SECURITY=tls`
- **THEN** el arranque falla indicando los valores permitidos

## MODIFIED Requirements

### Requirement: Verificaciones de seguridad al arranque fuera de desarrollo
Cuando `APP_ENV` sea `production`, el sistema SHALL abortar el arranque si detecta alguna condición insegura:
- usuarios activos con correo `@poc.local`;
- `SESSION_HTTPS_ONLY=false`;
- `MAIL_BACKEND=file`, porque los correos no se enviarían y quedarían escritos en disco;
- `SMTP_SECURITY=none`, porque las credenciales y los correos viajarían sin cifrar.

#### Scenario: Usuario demo activo en producción
- **WHEN** `APP_ENV=production` y existe un usuario activo `admin@poc.local`
- **THEN** el arranque falla con un mensaje que lista las cuentas demo activas a deshabilitar

#### Scenario: Cookie sin Secure en producción
- **WHEN** `APP_ENV=production` y `SESSION_HTTPS_ONLY=false`
- **THEN** el arranque falla indicando que en producción la cookie debe ser `Secure`

#### Scenario: Transporte de archivo en producción
- **WHEN** `APP_ENV=production` y `MAIL_BACKEND=file`
- **THEN** el arranque falla indicando que en producción los correos deben enviarse por SMTP

#### Scenario: SMTP sin cifrar en producción
- **WHEN** `APP_ENV=production`, `MAIL_BACKEND=smtp` y `SMTP_SECURITY=none`
- **THEN** el arranque falla indicando que en producción la conexión SMTP debe cifrarse

#### Scenario: Desarrollo no aplica verificaciones de producción
- **WHEN** `APP_ENV=development` y existen usuarios `@poc.local`
- **THEN** la aplicación arranca normalmente
