"""Create the local owner identity used for newly issued API keys."""
from alembic import op
import sqlalchemy as sa

revision = "0005_admin_owner"
down_revision = "0004_traffic_events"
branch_labels = None
depends_on = None

def upgrade():
    users = sa.table("users", sa.column("id", sa.Integer), sa.column("email", sa.String), sa.column("password_hash", sa.String), sa.column("is_admin", sa.Boolean))
    op.bulk_insert(users, [{"id": 1, "email": "local-admin@traffic.test", "password_hash": "disabled-local-owner", "is_admin": True}])

def downgrade():
    op.execute("DELETE FROM users WHERE id = 1 AND email = 'local-admin@traffic.test'")
