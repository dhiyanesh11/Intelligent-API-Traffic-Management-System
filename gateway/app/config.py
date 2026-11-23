from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://traffic:traffic-dev-only@localhost:5432/traffic"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "replace-this-with-a-long-random-secret"
    jwt_algorithm: str = "HS256"

settings = Settings()
