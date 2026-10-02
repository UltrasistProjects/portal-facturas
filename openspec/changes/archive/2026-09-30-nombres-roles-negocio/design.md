## Context

`Role` era un `StrEnum` con nombre y valor iguales (`PROVIDER = "PROVIDER"`), y `enum_column` construye un `SAEnum(native_enum=False, create_constraint=True)`: la columna es `VARCHAR` con un `CHECK` llamado como la enumeración (`role`), con la longitud del valor más largo (8). `ck_users_provider_supplier` (change `usuario-proveedor-vinculado`) compara con el literal `'PROVIDER'`. Las plantillas comparan `user.role.value` con literales.

## Goals / Non-Goals

**Goals:** que el nombre del rol sea el del negocio en la enumeración, en la base de datos, en la interfaz y en la documentación, y migrar los datos existentes sin perder a ningún usuario.

**Non-Goals:** reescribir la auditoría histórica; renombrar identificadores que no son nombres de rol ni rutas.

## Decisions

### D1. Miembros en mayúsculas y valores con el nombre del negocio

`ADMINISTRADOR = "Administrador"`, `PROVEEDOR = "Proveedor"`, `PMO = "PMO"`. Los miembros siguen la convención de constantes de Python y el valor es exactamente el nombre del negocio, que es lo que se guarda y se muestra. Así la interfaz muestra `role.value` sin tabla de traducción.

### D2. Guardar el valor, no el nombre del miembro

`SAEnum` guarda por defecto el nombre del miembro, así que `users.role` quedaría como `ADMINISTRADOR`. `enum_column` pasa `values_callable` para que se guarde el valor. En las demás enumeraciones el nombre y el valor coinciden, así que su columna y su `CHECK` no cambian (`alembic check` sin diferencias).

*Alternativa descartada:* un `values_callable` solo para `Role`. Complica `enum_column` sin beneficio, porque el resultado es el mismo para las demás.

### D3. Migración `0014_business_role_names`

En una transacción: quitar los `CHECK role` y `ck_users_provider_supplier`, ampliar `role` a `VARCHAR(13)`, renombrar con un `CASE` (`ADMIN`→`Administrador`, `PROVIDER`→`Proveedor`, `INTERNAL`→`PMO`) y recrear ambos `CHECK` con los nombres nuevos. El downgrade renombra antes de reducir la columna a `VARCHAR(8)`, porque los nombres nuevos no caben.

No se audita cada usuario: su rol no cambia, solo cambia cómo se llama. La auditoría previa (por ejemplo `"role": "PROVIDER"` en `USER_CREATED`) no se modifica, porque es evidencia del momento en que se registró.

### D4. Proveedor como opción por defecto del selector

El orden del selector es Proveedor, PMO, Administrador: la opción preseleccionada sigue siendo la de menor privilegio, como antes.

## Risks / Trade-offs

- **Base sin migrar:** con el código nuevo, un `users.role = 'ADMIN'` no se puede leer. Mitigación: la migración forma parte del despliegue (`alembic upgrade head`), como en los changes anteriores.
- **Auditoría con dos nomenclaturas:** los registros previos dicen `PROVIDER` y los nuevos `Proveedor`. Se documenta en el README.
