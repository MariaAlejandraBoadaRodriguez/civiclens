"""Runtime configuration read from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    allowed_origins: list[str] = ["http://localhost:3000"]
    default_locale: str = "en"
    database_url: str = "postgresql+psycopg://civiclens:civiclens@localhost:5432/civiclens"


settings = Settings()
