"""Contenido de los archivos en la base de datos (despliegue en Vercel).

- stored_files: el contenido de cada archivo cargado con STORAGE_BACKEND=database, por su ruta relativa a la raiz de
  almacenamiento (la misma de documents.path), con su tamano y SHA-256. CHECK: el tamano coincide con el contenido.
- Con STORAGE_BACKEND=local (el valor por defecto) la tabla queda vacia: los archivos siguen solo en storage/.

El downgrade se niega si la tabla tiene archivos: borrarla perderia documentos que no existen en ningun disco.
"""

import sqlalchemy as sa
from alembic import op

revision = "0022_stored_files"
down_revision = "0021_currency_catalog_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stored_files",
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("size = octet_length(content)", name="ck_stored_files_size"),
        sa.PrimaryKeyConstraint("path", name="pk_stored_files"),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM stored_files")):
        raise NotImplementedError(
            "stored_files tiene archivos: revertir perderia documentos guardados solo en la base de datos. "
            "Restaure un respaldo."
        )
    op.drop_table("stored_files")
