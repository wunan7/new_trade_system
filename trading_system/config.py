from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/finance"
    log_level: str = "INFO"
    factor_lookback_days: int = 120

    class Config:
        env_prefix = "FINANCE_"
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
