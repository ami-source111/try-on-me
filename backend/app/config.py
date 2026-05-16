from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str

    # fal.ai
    fal_key: str

    # Local media storage
    media_path: str = "/app/media"
    media_url: str = "http://localhost/media"

    # App
    backend_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
