"""Seed the two local demo services and their routes."""
from alembic import op
import sqlalchemy as sa

revision = "0002_demo_routes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    backends = sa.table("backends", sa.column("id", sa.Integer), sa.column("name", sa.String), sa.column("base_url", sa.String), sa.column("weight", sa.Integer), sa.column("is_active", sa.Boolean))
    op.bulk_insert(backends, [
        {"id": 1, "name": "backend-a", "base_url": "http://backend_a:8001", "weight": 1, "is_active": True},
        {"id": 2, "name": "backend-b", "base_url": "http://backend_b:8002", "weight": 1, "is_active": True},
    ])
    policies = sa.table("rate_limit_policies", sa.column("id", sa.Integer), sa.column("name", sa.String), sa.column("algorithm", sa.String), sa.column("limit", sa.Integer), sa.column("window_seconds", sa.Integer), sa.column("scope", sa.String), sa.column("is_active", sa.Boolean))
    op.bulk_insert(policies, [{"id": 1, "name": "default", "algorithm": "token_bucket", "limit": 60, "window_seconds": 60, "scope": "api_key", "is_active": True}])
    routes = sa.table("routes", sa.column("id", sa.Integer), sa.column("name", sa.String), sa.column("path_prefix", sa.String), sa.column("methods", sa.JSON), sa.column("backend_id", sa.Integer), sa.column("policy_id", sa.Integer), sa.column("auth_required", sa.Boolean), sa.column("is_active", sa.Boolean))
    op.bulk_insert(routes, [
        {"id": 1, "name": "demo-alpha", "path_prefix": "/alpha", "methods": ["GET", "POST", "PUT", "PATCH", "DELETE"], "backend_id": 1, "policy_id": 1, "auth_required": False, "is_active": True},
        {"id": 2, "name": "demo-beta", "path_prefix": "/beta", "methods": ["GET", "POST", "PUT", "PATCH", "DELETE"], "backend_id": 2, "policy_id": 1, "auth_required": False, "is_active": True},
    ])

def downgrade():
    op.execute("DELETE FROM routes WHERE id IN (1, 2)")
    op.execute("DELETE FROM rate_limit_policies WHERE id = 1")
    op.execute("DELETE FROM backends WHERE id IN (1, 2)")
