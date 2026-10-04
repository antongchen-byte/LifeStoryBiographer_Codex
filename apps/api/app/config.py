from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = ""
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts"
    interview_database_url: str = ""
    environment: str = "development"
    database_url: str = "postgresql+psycopg://biographer:biographer@postgres:5432/biographer"
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint: str = "http://minio:9000"
    s3_public_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "biographer"
    s3_region: str = "us-east-1"
    s3_server_side_encryption: bool = False
    upload_max_bytes: int = 2_147_483_648
    upload_part_bytes: int = 8 * 1024 * 1024
    upload_url_seconds: int = 900
    temporal_address: str = "temporal:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "biographer-media"
    scanner: str = "disabled"
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    session_days: int = 7
    allow_registration: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_environment(self) -> "Settings":
        if self.upload_part_bytes < 5 * 1024 * 1024:
            raise ValueError("Multipart parts must be at least 5 MiB")
        if self.scanner not in {"disabled", "clamav"}:
            raise ValueError("SCANNER must be disabled or clamav")
        if self.environment == "production":
            if self.scanner != "clamav" or not self.s3_server_side_encryption:
                raise ValueError("Production requires scanning and storage encryption")
            if not self.s3_endpoint.startswith("https://") or not self.s3_public_endpoint.startswith(
                "https://"
            ):
                raise ValueError("Production storage requires HTTPS")
            if self.s3_secret_key == "minioadmin":
                raise ValueError("Production cannot use development storage credentials")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
