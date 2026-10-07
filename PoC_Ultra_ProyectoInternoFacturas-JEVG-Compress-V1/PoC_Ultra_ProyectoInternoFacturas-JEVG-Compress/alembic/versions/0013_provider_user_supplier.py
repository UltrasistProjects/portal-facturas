"""Usuario Proveedor vinculado a su proveedor (change usuario-proveedor-vinculado).

- Un usuario PROVIDER activo sin supplier_id (creado en /admin/users con "Ninguno") se deshabilita, se revocan sus
  sesiones y se audita USER_DEACTIVATED_WITHOUT_SUPPLIER. No se borra: su historial es evidencia de auditoria.
- Un usuario INTERNAL o ADMIN con supplier_id pierde el vinculo, auditado como USER_SUPPLIER_CLEARED.
- Despues se crea ck_users_provider_supplier. El downgrade solo lo retira: los datos no se revierten.
"""

from alembic import op

revision = "0013_provider_user_supplier"
down_revision = "0012_invoice_cancellation"
branch_labels = None
depends_on = None

CHECK = (
    "(role = 'PROVIDER' AND (supplier_id IS NOT NULL OR NOT is_active)) OR (role <> 'PROVIDER' AND supplier_id IS NULL)"
)

DEACTIVATE_ORPHANS = """
WITH orphans AS (
    UPDATE users SET is_active = false
    WHERE role = 'PROVIDER' AND supplier_id IS NULL AND is_active
    RETURNING id
), revoked AS (
    UPDATE user_sessions SET revoked_at = now()
    WHERE revoked_at IS NULL AND user_id IN (SELECT id FROM orphans)
)
INSERT INTO audit_logs (action, entity, entity_id, old_value, new_value, timestamp)
SELECT 'USER_DEACTIVATED_WITHOUT_SUPPLIER', 'User', id::text, jsonb_build_object('is_active', true),
       jsonb_build_object('is_active', false), now()
FROM orphans
"""

CLEAR_INTERNAL_SUPPLIERS = """
WITH cleared AS (
    UPDATE users u SET supplier_id = NULL
    FROM (SELECT id, supplier_id FROM users WHERE role <> 'PROVIDER' AND supplier_id IS NOT NULL) previous
    WHERE u.id = previous.id
    RETURNING u.id, previous.supplier_id
)
INSERT INTO audit_logs (action, entity, entity_id, old_value, new_value, timestamp)
SELECT 'USER_SUPPLIER_CLEARED', 'User', id::text, jsonb_build_object('supplier_id', supplier_id),
       jsonb_build_object('supplier_id', NULL), now()
FROM cleared
"""


def upgrade() -> None:
    op.execute(DEACTIVATE_ORPHANS)
    op.execute(CLEAR_INTERNAL_SUPPLIERS)
    op.create_check_constraint("ck_users_provider_supplier", "users", CHECK)


def downgrade() -> None:
    op.drop_constraint("ck_users_provider_supplier", "users", type_="check")
