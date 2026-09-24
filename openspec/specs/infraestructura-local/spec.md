# infraestructura-local Specification

## Purpose
Servicio PostgreSQL local dockerizado con Docker Compose: versión fijada, expuesto sólo en localhost, credenciales desde `.env`, volumen persistente y healthcheck.

## Requirements
### Requirement: Servicio PostgreSQL con Docker Compose
La raíz de la PoC SHALL incluir un `compose.yaml` con un servicio `db` basado en la imagen oficial de PostgreSQL 18, con una etiqueta de versión menor fija (nunca `latest` ni sólo la mayor). El servicio SHALL:
- tomar `POSTGRES_USER`, `POSTGRES_DB` y `POSTGRES_PASSWORD` del `.env` de la PoC;
- negarse a arrancar si `POSTGRES_PASSWORD` no está definida;
- persistir los datos en un volumen con nombre;
- declarar un healthcheck con `pg_isready`.

#### Scenario: Arranque del servicio
- **WHEN** se ejecuta `docker compose up -d --wait db` con un `.env` generado por `scripts/create_env.py`
- **THEN** el comando termina cuando el servicio está `healthy` y acepta conexiones con las credenciales de `.env`

#### Scenario: Persistencia entre reinicios
- **WHEN** se crea una factura, se ejecuta `docker compose down` (sin `-v`) y luego `docker compose up -d --wait db`
- **THEN** la factura sigue existiendo

#### Scenario: Contraseña ausente
- **WHEN** `POSTGRES_PASSWORD` no está definida en `.env`
- **THEN** `docker compose up` falla con un mensaje que indica definir `POSTGRES_PASSWORD`

#### Scenario: Versión fijada
- **WHEN** se inspecciona `docker compose config`
- **THEN** la imagen del servicio `db` tiene la forma `postgres:18.<menor>-alpine`

### Requirement: Exposición sólo local
El puerto de PostgreSQL SHALL publicarse únicamente en `127.0.0.1`, en el puerto del host `POSTGRES_PORT`, 55432 por defecto. En este equipo el 5432 y el 5433 ya los ocupan otras instancias.

#### Scenario: Enlace a localhost
- **WHEN** se inspecciona `docker compose config`
- **THEN** el puerto publicado del servicio `db` tiene `host_ip: 127.0.0.1`

#### Scenario: Puerto configurable
- **WHEN** `.env` define `POSTGRES_PORT=56000` y se levanta el servicio
- **THEN** PostgreSQL acepta conexiones en `127.0.0.1:56000` y `DATABASE_URL` apunta a ese puerto

