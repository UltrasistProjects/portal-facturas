# HU-23 · Complemento de pagos

| Campo | Valor |
| --- | --- |
| ID | HU-23 |
| Rol | PMO / Administrador (el proveedor adjunta el complemento) |
| Módulo | B. Gestión de facturas |
| Origen | Solicitud de negocio del 2026-10-05 (nueva). No está en el documento de HUs ni en la ERS v1.4 |
| Requisito funcional | Nuevo; por definir en la siguiente versión de la ERS |
| Change OpenSpec | `complemento-de-pago` |
| Capacidad nueva | `pago-facturas` |
| Capacidades modificadas | `flujo-facturas`, `archivos-minimos-factura`, `plantillas-notificacion`, `notificaciones-correo`, `revision-pmo`, `cancelacion-facturas`, `integridad-datos` |
| Dependencias | HU-20 (Autorizada), HU-08 (buzón y envío de correos), HU-04 (archivos mínimos), HU-13 (envío a validación) |
| Versión / fecha | 1.0 · 2026-10-05 · Equipo Técnico |

## 1. Historia de usuario

**Texto de la solicitud (2026-10-05, ortografía normalizada):**

> Yo como PMO o Administrador del Sistema, una vez que actualizamos como "Pagada" una factura solo para Proveedor ya sea Internacional y Nacional, se debe mandar un mensaje al correo del contacto del proveedor, indicando que su factura "XX" (donde XX es el número de factura) ha sido pagada; y si y solo si, esta factura es de un proveedor "Nacional" y tiene forma de pago "PDD", tiene que agregar la sección: Es importante que adjunte su "Complemento de Pago" a dicha factura pagada, de tal manera que una vez que el proveedor haga esta acción, se mandará un correo al correo de "Recepción de facturas", indicando que el Complemento de Pago ha sido adjuntado a la factura "XX", donde XX es el número de factura que se acaba de adjuntar el complemento de pago; de lo contrario, es decir, si no se sube el complemento de pago en un máximo de 72 horas después del pago, el sistema bloqueará el envío de facturas subsecuentes. Esto significa que cada que se envíe una nueva factura se debe validar si hay "complementos de pagos" pendientes por subir a las facturas con forma de pago "PDD".
>
> NOTA: Es importante que dentro de la configuración de requisitos de la factura se agregue como "Opcional" el documento "Complemento de Pago".

**Redacción como HU:**

> Yo como PMO o Administrador del sistema requiero que, al actualizar como “Pagada” una factura de un proveedor nacional o internacional, se avise al proveedor que su factura fue pagada y, si es nacional con método de pago PPD, se le pida adjuntar su “Complemento de Pago”, para que Recepción de Facturas reciba el aviso cuando se adjunte y el sistema bloquee el envío de facturas subsecuentes si no se adjunta en un máximo de 72 horas.

## 2. Criterios de aceptación

1. El PMO o el Administrador marcan como "Pagada" una factura "Autorizada". "Pagada" es final: no admite cancelación, decisión ni envío.
2. Al pagar se envía al correo del proveedor en el catálogo el aviso "Su factura número XX ha sido pagada".
3. Sólo si el proveedor es nacional y el método de pago del CFDI es PPD, el aviso agrega "Es importante que adjunte su “Complemento de Pago” a dicha factura pagada" con la fecha límite (pago + 72 horas).
4. El proveedor adjunta el Complemento de Pago en la factura pagada: un CFDI de tipo P que relaciona el UUID de la factura. Cada XML válido envía a Recepción de Facturas el aviso "El Complemento de Pago ha sido adjuntado a la factura XX".
5. Con un complemento vencido (más de 72 horas sin adjuntar), cada envío a validación del proveedor se rechaza hasta que lo adjunte.
6. En la configuración de requisitos de la factura, "Complemento de pago" (XML y PDF) queda fijo como Opcional para el nacional y No aplica para el internacional.

## 3. Supuestos

- "PDD" es el método de pago **PPD** del CFDI (`MetodoPago`, pago en parcialidades o diferido).
- El "correo del contacto del proveedor" es el correo del proveedor en el catálogo.
- Las 72 horas son naturales y se cuentan desde que la factura se marca "Pagada" en el portal.
- El complemento cuenta como adjuntado con su XML; el PDF es opcional.
- El bloqueo aplica a todos los envíos a validación, también a los reenvíos desde "Observaciones"; no impide registrar facturas ni cargar documentos.

El detalle de requisitos, diseño y tareas está en el change OpenSpec `complemento-de-pago`.
