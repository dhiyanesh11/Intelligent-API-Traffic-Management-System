"""Initial identity, routing, backend and rate policy schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("email", sa.String(320), nullable=False, unique=True), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("backends", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(100), nullable=False, unique=True), sa.Column("base_url", sa.String(2048), nullable=False), sa.Column("weight", sa.Integer(), nullable=False, server_default="1"), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("api_keys", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("key_hash", sa.String(64), nullable=False, unique=True), sa.Column("key_prefix", sa.String(16), nullable=False), sa.Column("name", sa.String(100), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("rate_limit_policies", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(100), nullable=False, unique=True), sa.Column("algorithm", sa.String(24), nullable=False, server_default="token_bucket"), sa.Column("limit", sa.Integer(), nullable=False, server_default="60"), sa.Column("window_seconds", sa.Integer(), nullable=False, server_default="60"), sa.Column("scope", sa.String(24), nullable=False, server_default="api_key"), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("routes", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(100), nullable=False, unique=True), sa.Column("path_prefix", sa.String(512), nullable=False, index=True), sa.Column("methods", sa.JSON(), nullable=False, server_default="[\"GET\"]"), sa.Column("backend_id", sa.Integer(), sa.ForeignKey("backends.id", ondelete="RESTRICT"), nullable=False), sa.Column("policy_id", sa.Integer(), sa.ForeignKey("rate_limit_policies.id", ondelete="SET NULL")), sa.Column("auth_required", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))

def downgrade():
    op.drop_table("routes")
    op.drop_table("rate_limit_policies")
    op.drop_table("api_keys")
    op.drop_table("backends")
    op.drop_table("users")
