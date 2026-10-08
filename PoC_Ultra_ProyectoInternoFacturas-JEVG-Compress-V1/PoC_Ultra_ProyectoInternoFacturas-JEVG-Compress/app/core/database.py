from collections.abc import Generator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# Nombres deterministas en cualquier servidor, utiles para migraciones futuras. UNIQUE y CHECK ya se nombran
# explicitamente en los modelos; "ix" conserva la convencion por defecto de SQLAlchemy.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# pool_pre_ping descarta conexiones cortadas (p. ej. tras reiniciar el contenedor); la sesion trabaja en UTC.
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args={"options": "-c timezone=UTC"})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def violates(exc: IntegrityError, constraint_name: str) -> bool:
    """True si el IntegrityError proviene de la restriccion con ese nombre (psycopg lo expone en diag)."""
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == constraint_name
