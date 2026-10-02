## MODIFIED Requirements

### Requirement: Alta de factura con datos validados
El alta de factura SHALL verificar, en este orden:
1. que el usuario esté vinculado a un proveedor, y que éste esté "Autorizado" (`ACTIVE`); si no tiene proveedor, HTTP 409 "Su usuario no está vinculado a un proveedor. Contacte al Administrador"; si el proveedor no está autorizado, HTTP 409 "Su proveedor no está autorizado para registrar facturas"; también al abrir el formulario;
2. los datos del formulario con el esquema `InvoiceCreate`:
   - `invoice_number` de 1 a 100 caracteres;
   - `service_period` con formato `MM/AAAA` y mes entre 01 y 12;
   - `project_name` de 2 a 200 caracteres;
3. que el contrato pertenezca al proveedor y esté activo.

Los errores de datos SHALL mostrarse en el mismo formulario con HTTP 400. Un número de factura repetido para el mismo proveedor SHALL rechazarse con un mensaje claro, sin HTTP 500. La factura creada SHALL quedar en "Borrador" y el alta SHALL llevar a la carga documental.

#### Scenario: Periodo inválido
- **WHEN** un proveedor crea una factura con `service_period = "13/2026"`
- **THEN** la respuesta es HTTP 400, el formulario muestra el error del periodo y no se crea la factura

#### Scenario: Número de factura repetido
- **WHEN** un proveedor crea una factura con un `invoice_number` que ya usó en otra factura propia
- **THEN** la respuesta es HTTP 409 con el mensaje "Ya existe una factura con ese número para el proveedor" y no se crea la factura

#### Scenario: Proveedor inactivo
- **WHEN** un proveedor cuyo registro está inactivo abre el formulario de alta o lo envía
- **THEN** la respuesta es HTTP 409 "Su proveedor no está autorizado para registrar facturas" y no se crea la factura

#### Scenario: Alta correcta
- **WHEN** un proveedor autorizado crea una factura con datos válidos y un contrato propio activo
- **THEN** la factura queda en "Borrador" y la respuesta redirige a su carga documental

#### Scenario: Usuario sin proveedor
- **WHEN** un usuario Proveedor sin proveedor abre el formulario de alta o lo envía
- **THEN** la respuesta es HTTP 409 "Su usuario no está vinculado a un proveedor. Contacte al Administrador" y no se crea la factura
