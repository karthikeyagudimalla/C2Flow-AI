
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
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://127.0.0.1:8000/api/integrations/google-calendar/callback",
    )
    GOOGLE_AUTH_REDIRECT_URI = os.getenv(
        "GOOGLE_AUTH_REDIRECT_URI",
        "http://127.0.0.1:8000/api/auth/google/callback",
    )
    GOOGLE_TOKEN_ENCRYPTION_KEY = os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY", "")
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


settings = Settings()
