import os
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "yego_integral"
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DATABASE_URL: str = ""

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    CORS_ORIGINS_STR: str = "http://localhost:5173,http://localhost:3000"

    @property
    def CORS_ORIGINS(self) -> List[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS_STR.split(",")
            if origin.strip()
        ]

    ENVIRONMENT: str = "dev"

    SOURCE_TABLE: str = "module_ct_cabinet_drivers"
    SOURCE_SCHEMA: str = "public"

    model_config = {
        "env_file": os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        "case_sensitive": False,
        "extra": "ignore",
        "populate_by_name": True,
    }


settings = Settings()
