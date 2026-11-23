from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Backend(Base):
    __tablename__ = "backends"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    base_url: Mapped[str] = mapped_column(String(2048))
    weight: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class APIKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    key_prefix: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class RateLimitPolicy(Base):
    __tablename__ = "rate_limit_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    algorithm: Mapped[str] = mapped_column(String(24), default="token_bucket")
    limit: Mapped[int] = mapped_column(Integer, default=60)
    window_seconds: Mapped[int] = mapped_column(Integer, default=60)
    scope: Mapped[str] = mapped_column(String(24), default="api_key")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Route(Base):
    __tablename__ = "routes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    path_prefix: Mapped[str] = mapped_column(String(512), index=True)
    methods: Mapped[list] = mapped_column(JSON, default=lambda: ["GET"])
    backend_id: Mapped[int] = mapped_column(ForeignKey("backends.id", ondelete="RESTRICT"))
    policy_id: Mapped[int | None] = mapped_column(ForeignKey("rate_limit_policies.id", ondelete="SET NULL"))
    strategy: Mapped[str] = mapped_column(String(24), default="round_robin")
    auth_required: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class RouteBackend(Base):
    __tablename__ = "route_backends"
    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"))
    backend_id: Mapped[int] = mapped_column(ForeignKey("backends.id", ondelete="CASCADE"))
    weight: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
