"""Add route backend pools for balancing traffic across upstreams."""
from alembic import op
import sqlalchemy as sa

revision = "0003_backend_pools"
down_revision = "0002_demo_routes"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("routes", sa.Column("strategy", sa.String(24), nullable=False, server_default="round_robin"))
    op.create_table("route_backends",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("route_id", sa.Integer(), sa.ForeignKey("routes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("backend_id", sa.Integer(), sa.ForeignKey("backends.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("route_id", "backend_id", name="uq_route_backend"))
    pool = sa.table("route_backends", sa.column("route_id", sa.Integer), sa.column("backend_id", sa.Integer), sa.column("weight", sa.Integer), sa.column("is_active", sa.Boolean))
    op.bulk_insert(pool, [
        {"route_id": 1, "backend_id": 1, "weight": 1, "is_active": True},
        {"route_id": 1, "backend_id": 2, "weight": 2, "is_active": True},
        {"route_id": 2, "backend_id": 2, "weight": 1, "is_active": True},
    ])

def downgrade():
    op.drop_table("route_backends")
    op.drop_column("routes", "strategy")
