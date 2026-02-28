from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    MONGODB_URI: str = "mongodb://localhost:27017"
    JWT_SECRET_KEY: str = "change-me-to-a-random-secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    # Upstox OAuth credentials
    UPSTOX_API_KEY: str = ""
    UPSTOX_API_SECRET: str = ""
    UPSTOX_REDIRECT_URI: str = "http://localhost:8000/auth/upstox/callback"
    # Paste a valid access token here to skip the OAuth flow during development
    UPSTOX_ACCESS_TOKEN: str = ""


settings = Settings()
