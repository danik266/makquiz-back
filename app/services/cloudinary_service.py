"""
cloudinary_service.py - Сервис для работы с Cloudinary
Читает настройки из .env файла через config.settings
"""

import cloudinary
import cloudinary.uploader
import cloudinary.api
import tempfile
import os
from app.config import settings

# Инициализация Cloudinary из .env
cloudinary.config(
    cloud_name=getattr(settings, 'CLOUDINARY_CLOUD_NAME', None),
    api_key=getattr(settings, 'CLOUDINARY_API_KEY', None),
    api_secret=getattr(settings, 'CLOUDINARY_API_SECRET', None),
    secure=True
)


def is_configured() -> bool:
    """Проверяет, настроен ли Cloudinary"""
    cloud_name = getattr(settings, 'CLOUDINARY_CLOUD_NAME', None)
    api_key = getattr(settings, 'CLOUDINARY_API_KEY', None)
    api_secret = getattr(settings, 'CLOUDINARY_API_SECRET', None)
    
    return bool(cloud_name and api_key and api_secret)


async def upload_file(file_bytes: bytes, folder: str = "flashcards", filename: str = None) -> str | None:
    """
    Загружает файл в Cloudinary.
    
    Args:
        file_bytes: Байты файла
        folder: Папка в Cloudinary
        filename: Опциональное имя файла (без расширения)
    
    Returns:
        URL загруженного изображения или None при ошибке
    """
    if not is_configured():
        print("⚠️ Cloudinary не настроен! Добавь CLOUDINARY_* в .env")
        return None
    
    try:
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        
        # Загружаем в Cloudinary
        options = {
            "folder": folder,
            "resource_type": "image",
            "overwrite": True,
            "transformation": [
                {"quality": "auto:good"},
                {"fetch_format": "auto"}
            ]
        }
        
        if filename:
            options["public_id"] = filename
        
        result = cloudinary.uploader.upload(tmp_path, **options)
        
        # Удаляем временный файл
        os.unlink(tmp_path)
        
        url = result.get("secure_url")
        print(f"✅ Cloudinary upload: {url}")
        return url
        
    except Exception as e:
        print(f"❌ Cloudinary upload error: {e}")
        return None


async def upload_from_url(image_url: str, folder: str = "flashcards") -> str | None:
    """
    Загружает изображение по URL в Cloudinary.
    Используется для сохранения AI-сгенерированных изображений.
    
    Args:
        image_url: URL исходного изображения
        folder: Папка в Cloudinary
    
    Returns:
        URL в Cloudinary или None при ошибке
    """
    if not is_configured():
        print("⚠️ Cloudinary не настроен!")
        return image_url  # Возвращаем оригинальный URL как fallback
    
    try:
        result = cloudinary.uploader.upload(
            image_url,
            folder=folder,
            resource_type="image",
            transformation=[
                {"quality": "auto:good"},
                {"fetch_format": "auto"}
            ]
        )
        
        url = result.get("secure_url")
        print(f"✅ Cloudinary (from URL): {url}")
        return url
        
    except Exception as e:
        print(f"❌ Cloudinary upload from URL error: {e}")
        return image_url  # Возвращаем оригинальный URL как fallback


async def delete_image(public_id: str) -> bool:
    """
    Удаляет изображение из Cloudinary.
    """
    if not is_configured():
        return False
    
    try:
        result = cloudinary.uploader.destroy(public_id)
        return result.get("result") == "ok"
    except Exception as e:
        print(f"❌ Cloudinary delete error: {e}")
        return False


def extract_public_id(cloudinary_url: str) -> str | None:
    """
    Извлекает public_id из URL Cloudinary.
    """
    if not cloudinary_url or "cloudinary.com" not in cloudinary_url:
        return None
    
    try:
        parts = cloudinary_url.split("/upload/")
        if len(parts) < 2:
            return None
        
        path = parts[1]
        
        if path.startswith("v"):
            path = "/".join(path.split("/")[1:])
        
        public_id = path.rsplit(".", 1)[0]
        return public_id
    except:
        return None