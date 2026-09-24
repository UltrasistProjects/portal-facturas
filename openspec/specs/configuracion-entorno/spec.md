# configuracion-entorno Specification

## Purpose
Configuración segura por entorno (`SECRET_KEY`, `DEBUG`, `APP_ENV`), rutas ancladas a la raíz del proyecto y verificaciones de arranque que impiden operar con valores inseguros.

## Requirements
### Requirement: SECRET_KEY obligatoria y robusta
El sistema SHALL negarse a arrancar si `SECRET_KEY` no está definida, si tiene menos de 32 caracteres o si comienza con el prefijo de placeholder `change-me`. La configuración MUST NOT contener ningún valor por defecto para `SECRET_KEY` ni en el código ni en `.env.example`.

#### Scenario: Arranque sin SECRET_KEY
- **WHEN** la aplicación se inicia sin `SECRET_KEY` en el entorno ni en `.env`
- **THEN** el arranque falla con un error de configuración que indica que `SECRET_KEY` es obligatoria y cómo generarla (`secrets.token_urlsafe(64)`)

#### Scenario: Placeholder rechazado
- **WHEN** `SECRET_KEY=change-me-use-a-long-random-value`
- **THEN** el arranque falla con un error que identifica el valor como placeholder inseguro

#### Scenario: Clave demasiado corta
- **WHEN** `SECRET_KEY` tiene 31 caracteres
- **THEN** el arranque falla indicando la longitud mínima de 32

#### Scenario: Generación del .env local
- **WHEN** un script de arranque local (`run_local.*`) se ejecuta y no existe `.env`
- **THEN** se crea `.env` a partir de `.env.example` con una `SECRET_KEY` aleatoria generada con `secrets.token_urlsafe(64)`

#### Scenario: .env existente no se sobrescribe
- **WHEN** un script de arranque local se ejecuta y ya existe `.env`
- **THEN** el archivo `.env` permanece sin cambios

### Requirement: Modo debug desacoplado del manejo de errores
El sistema MUST NOT pasar `debug=True` a `FastAPI(...)` bajo ninguna configuración. `DEBUG` SHALL valer `false` por defecto y su único efecto SHALL ser elevar el nivel de log a `DEBUG`.

#### Scenario: Excepción no manejada con DEBUG activo
- **WHEN** `DEBUG=true` y una petición provoca una excepción no manejada
- **THEN** la respuesta es la página de error genérica con HTTP 500, sin traceback, código fuente ni variables locales, y la traza completa queda registrada en el log

#### Scenario: Valor por defecto
- **WHEN** la variable `DEBUG` no está definida
- **THEN** el sistema opera con `debug = false`

### Requirement: APP_ENV gobierna los valores por defecto
`APP_ENV` SHALL aceptar únicamente `development`, `test` o `production`; cualquier otro valor MUST impedir el arranque. `SESSION_HTTPS_ONLY` SHALL valer `true` por defecto cuando `APP_ENV` sea distinto de `development`.

#### Scenario: Valor de entorno desconocido
- **WHEN** `APP_ENV=prod`
- **THEN** el arranque falla indicando los valores permitidos

#### Scenario: Cookie segura por defecto en producción
- **WHEN** `APP_ENV=production` y `SESSION_HTTPS_ONLY` no está definida
- **THEN** la cookie de sesión se emite con el atributo `Secure`

### Requirement: Verificaciones de seguridad al arranque fuera de desarrollo
Cuando `APP_ENV` sea `production`, el sistema SHALL abortar el arranque si detecta alguna condición insegura: usuarios activos con correo `@poc.local`, o `SESSION_HTTPS_ONLY=false`.

#### Scenario: Usuario demo activo en producción
- **WHEN** `APP_ENV=production` y existe un usuario activo `admin@poc.local`
- **THEN** el arranque falla con un mensaje que lista las cuentas demo activas a deshabilitar

#### Scenario: Cookie sin Secure en producción
- **WHEN** `APP_ENV=production` y `SESSION_HTTPS_ONLY=false`
- **THEN** el arranque falla indicando que en producción la cookie debe ser `Secure`

#### Scenario: Desarrollo no aplica verificaciones de producción
- **WHEN** `APP_ENV=development` y existen usuarios `@poc.local`
- **THEN** la aplicación arranca normalmente

### Requirement: Rutas ancladas al directorio del proyecto
Todas las rutas de la aplicación (`.env`, base de datos SQLite relativa, `storage/`, `logs/`, `app/static`, `app/templates`) SHALL resolverse contra la raíz del proyecto y MUST NOT depender del directorio de trabajo actual. Las rutas relativas provistas por configuración SHALL interpretarse relativas a la raíz del proyecto.

#### Scenario: Arranque desde otro directorio
- **WHEN** la aplicación se inicia con el directorio de trabajo fuera de la raíz del proyecto
- **THEN** usa la misma base de datos, almacenamiento, logs y recursos estáticos que al iniciarse desde la raíz, y no crea una base de datos vacía nueva

#### Scenario: Ruta relativa en configuración
- **WHEN** `STORAGE_PATH=./storage` y el directorio de trabajo es distinto de la raíz
- **THEN** el almacenamiento resuelto es `<raíz del proyecto>/storage`

