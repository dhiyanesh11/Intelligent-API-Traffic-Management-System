"""Persist gateway traffic events for dashboards and ML features."""
from alembic import op
import sqlalchemy as sa

revision = "0004_traffic_events"
down_revision = "0003_backend_pools"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("traffic_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("client", sa.String(128), nullable=False),
        sa.Column("route_name", sa.String(100), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_traffic_events_request_id", "traffic_events", ["request_id"])
    op.create_index("ix_traffic_events_client", "traffic_events", ["client"])
    op.create_index("ix_traffic_events_route_name", "traffic_events", ["route_name"])
    op.create_index("ix_traffic_events_created_at", "traffic_events", ["created_at"])

def downgrade():
    op.drop_table("traffic_events")
