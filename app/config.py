from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    url: str = "postgresql+asyncpg://matryoshka:matryoshka_pass@localhost:5432/matryoshka_db"

    model_config = SettingsConfigDict(env_prefix="db_", env_file=".env", extra="ignore")


class ServiceSettings(BaseSettings):
    app_name: str = "Matryoshka Enterprise Service"
    rest_host: str = "0.0.0.0"
    rest_port: int = 8001
    grpc_port: int = 50051
    debug: bool = False
    cors_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(env_prefix="service_", env_file=".env", extra="ignore")


database_settings = DatabaseSettings()
service_settings = ServiceSettings()
