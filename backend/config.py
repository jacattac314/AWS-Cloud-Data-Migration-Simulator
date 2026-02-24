"""Application configuration loaded from environment variables / .env file."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Cloud Migration Command Center"
    APP_ENV: str = "development"
    SECRET_KEY: str = "dev-secret-change-in-production"

    DATABASE_URL: str = "sqlite:///./migration_cmd_center.db"

    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_CHAT_MODEL: str = "gpt-4o"

    BACKEND_URL: str = "http://localhost:8000"

    # AWS (optional – used if deploying to real AWS)
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
