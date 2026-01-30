"""
config.py - Конфигурация приложения
"""

from pydantic_settings import BaseSettings
from typing import Optional, List

class Settings(BaseSettings):
    # MongoDB
    MONGO_URI: str = "mongodb://localhost:27017"
    
    # Сделай ключ ОПЦИОНАЛЬНЫМ (добавь Optional и = None)
    GOOGLE_API_KEY: Optional[str] = None 
    UNSPLASH_ACCESS_KEY: Optional[str] = None
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    # JWT
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    
    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()