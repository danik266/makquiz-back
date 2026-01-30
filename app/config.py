"""
config.py - Конфигурация приложения
"""

from pydantic_settings import BaseSettings
from typing import Optional, List
import os

class Settings(BaseSettings):
    # MongoDB
    # Если переменной нет, лучше пусть будет пусто, чем localhost (чтобы сразу видеть ошибку)
    # Но для надежности оставим заглушку, которую надо перекрыть в Render
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    
    # Ключи API
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
    # Добавляем "*" (разрешить всем) и твой Vercel явно
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000", 
        "http://127.0.0.1:3000",
        "https://makquiz-front.vercel.app",
        "*"  # <--- ВАЖНО: Разрешает всё (для тестов)
    ]
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()