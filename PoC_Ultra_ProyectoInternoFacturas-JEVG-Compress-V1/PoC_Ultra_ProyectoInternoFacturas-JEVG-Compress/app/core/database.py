from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


# Se ejecutan en cada conexion nueva, fuera de transaccion (PRAGMA foreign_keys no tiene efecto dentro de una).
SQLITE_PRAGMAS = ("foreign_keys=ON", "journal_mode=WAL", "busy_timeout=5000", "synchronous=NORMAL")


def install_sqlite_pragmas(target: Engine) -> None:
    if target.dialect.name != "sqlite":
        return

    @event.listens_for(target, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        for pragma in SQLITE_PRAGMAS:
            cursor.execute(f"PRAGMA {pragma}")
        cursor.close()


if settings.database_url.startswith("sqlite"):
    db_path = settings.database_url.removeprefix("sqlite:///")
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
install_sqlite_pragmas(engine)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
