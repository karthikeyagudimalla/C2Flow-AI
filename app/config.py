
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    APP_NAME = os.getenv("APP_NAME", "Garuda Ops API")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    JWT_SECRET = os.getenv("JWT_SECRET", "")
    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    )


settings = Settings()
