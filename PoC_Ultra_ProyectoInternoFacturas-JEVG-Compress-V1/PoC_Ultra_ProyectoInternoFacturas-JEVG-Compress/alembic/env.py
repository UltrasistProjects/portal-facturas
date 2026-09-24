from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import Base, install_sqlite_pragmas

config = context.config
# Un llamador (p. ej. las pruebas) puede fijar otra BD en config.attributes["database_url"].
config.set_main_option("sqlalchemy.url", config.attributes.get("database_url") or settings.database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    install_sqlite_pragmas(connectable)
    with connectable.connect() as connection:
        sqlite = connection.dialect.name == "sqlite"
        if sqlite:
            # Procedimiento de SQLite para reconstruir tablas (batch): FKs desactivadas durante la migracion,
            # fuera de cualquier transaccion, y verificacion de integridad al terminar.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
        if sqlite:
            violations = connection.execute(text("PRAGMA foreign_key_check")).fetchall()
            if violations:
                raise RuntimeError(
                    f"La migracion dejo {len(violations)} violaciones de llave foranea: {violations[:10]}"
                )


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
