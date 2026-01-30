"""
image_service.py - Сервис поиска и генерации изображений с Cloudinary

Изображения ищутся через DuckDuckGo и загружаются в Cloudinary для надежного хранения.
"""

from duckduckgo_search import DDGS

# Импортируем Cloudinary сервис
from app.services.cloudinary_service import upload_from_url, is_configured


async def generate_image_pollinations(prompt: str) -> str | None:
    """
    Ищет изображение в интернете по запросу и загружает в Cloudinary.
    
    Args:
        prompt: Поисковый запрос
    
    Returns:
        URL изображения в Cloudinary (или оригинальный URL если Cloudinary не настроен)
    """
    
    # 1. Поиск изображения в интернете
    image_url = None
    try:
        with DDGS() as ddgs:
            # Исключаем сайты с водяными знаками
            search_query = f"{prompt} wallpaper -site:alamy.com -site:gettyimages.com -site:shutterstock.com -site:istockphoto.com -watermark"
            
            results = list(ddgs.images(
                search_query, 
                max_results=3,
                safesearch='moderate',
                size='Large',
                type_image='photo'
            ))
            
            if results:
                image_url = results[0]['image']
                print(f"🔍 Найдено изображение: {image_url}")
            else:
                print(f"❌ Ничего не найдено для: {prompt}")
                return None
                
    except Exception as e:
        print(f"❌ Ошибка поиска: {e}")
        return None

    if not image_url:
        return None

    # 2. Загружаем в Cloudinary
    if is_configured():
        cloudinary_url = await upload_from_url(
            image_url, 
            folder="flashcards/ai_generated"
        )
        return cloudinary_url
    else:
        # Если Cloudinary не настроен, возвращаем оригинальный URL
        print("⚠️ Cloudinary не настроен, возвращаем оригинальный URL")
        return image_url