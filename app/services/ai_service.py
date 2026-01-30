"""
ai_service.py - AI генерация карточек
"""

from google import genai
from google.genai import types
import json
import os
import requests
from typing import List, Dict, Optional
# Импортируем настройки, чтобы ключ точно загрузился из .env
from app.config import settings 

# Функция для получения клиента с ключом
def get_client():
    if not settings.GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY не найден в .env или config.py")
    return genai.Client(api_key=settings.GOOGLE_API_KEY)

async def generate_cards_from_text(text: str, count: int = 10) -> List[Dict]:
    """Генерация карточек из текста"""
    try:
        client = get_client()
        
        prompt = f"""
        Создай {count} образовательных флеш-карточек из следующего текста.
        Верни ТОЛЬКО валидный JSON массив (без markdown ```json ... ```):
        [
            {{
                "front": "Вопрос",
                "back": "Ответ",
                "image_query": "short english query (2-3 words)"
            }}
        ]

        Текст:
        {text[:15000]}
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash', # Или gemini-1.5-flash
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                temperature=0.7
            )
        )
        
        text_response = response.text.strip()
        # Чистим markdown если он все же есть
        if text_response.startswith("```json"):
            text_response = text_response.replace("```json", "").replace("```", "")
            
        cards = json.loads(text_response)
        
        # Добавляем картинки
        for card in cards:
            if card.get("image_query"):
                card["image_url"] = await search_image(card["image_query"])
        
        return cards[:count]
    
    except Exception as e:
        print(f"AI Error (Text): {e}")
        return generate_fallback_cards(text, count)


async def generate_cards_from_topic(topic: str, count: int = 10) -> List[Dict]:
    """Генерация карточек по теме"""
    try:
        client = get_client()
        
        prompt = f"""
        Создай {count} образовательных флеш-карточек по теме: "{topic}".
        Верни ТОЛЬКО валидный JSON массив (без markdown):
        [
            {{
                "front": "Вопрос",
                "back": "Ответ",
                "image_query": "short english query"
            }}
        ]
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                temperature=0.7
            )
        )
        
        text_response = response.text.strip()
        if text_response.startswith("```json"):
             text_response = text_response.replace("```json", "").replace("```", "")

        cards = json.loads(text_response)
        
        for card in cards:
            if card.get("image_query"):
                card["image_url"] = await search_image(card["image_query"])
        
        return cards[:count]
    
    except Exception as e:
        print(f"AI Error (Topic): {e}")
        return [
            {
                "front": f"Вопрос про {topic} #{i+1}", 
                "back": "Ответ от заглушки (AI ошибка)", 
                "image_query": topic
            } for i in range(5)
        ]

async def search_image(query: str) -> Optional[str]:
    """Поиск изображения через Unsplash"""
    if not settings.UNSPLASH_ACCESS_KEY:
        return None
        
    try:
        url = "https://api.unsplash.com/search/photos"
        params = {"query": query, "per_page": 1, "orientation": "landscape"}
        headers = {"Authorization": f"Client-ID {settings.UNSPLASH_ACCESS_KEY}"}
        
        resp = requests.get(url, params=params, headers=headers, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if data["results"]:
                return data["results"][0]["urls"]["regular"]
    except Exception:
        pass
    return None

def generate_fallback_cards(text: str, count: int) -> List[Dict]:
    """Заглушка при ошибках"""
    return [{
        "front": "Ошибка генерации",
        "back": "Проверьте консоль сервера. Возможно, текст слишком короткий или ключ не работает.",
        "image_query": "error"
    }]


async def generate_quiz_from_text(text: str, count: int = 10) -> List[Dict]:
    """Генерация квиз-вопросов из текста"""
    try:
        client = get_client()

        prompt = f"""
        Создай {count} квиз-вопросов (multiple choice) из следующего текста.
        Верни ТОЛЬКО валидный JSON массив (без markdown ```json ... ```):
        [
            {{
                "question": "Вопрос здесь?",
                "options": ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4"],
                "correct_answers": [2],
                "explanation": "Объяснение правильного ответа",
                "image_query": "short english query (2-3 words)"
            }}
        ]

        Требования:
        - Каждый вопрос должен иметь 2-6 вариантов ответа
        - correct_answers содержит индексы правильных ответов (начиная с 0)
        - Для True/False вопросов используй 2 варианта: ["True", "False"]
        - Можно указать несколько правильных ответов, например [0, 2]

        Текст:
        {text[:15000]}
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                temperature=0.7
            )
        )

        text_response = response.text.strip()
        if text_response.startswith("```json"):
            text_response = text_response.replace("```json", "").replace("```", "")

        questions = json.loads(text_response)

        # Добавляем картинки
        for question in questions:
            if question.get("image_query"):
                question["image_url"] = await search_image(question["image_query"])

        return questions[:count]

    except Exception as e:
        print(f"AI Error (Quiz from Text): {e}")
        return generate_fallback_quiz(text, count)


async def generate_quiz_from_topic(topic: str, count: int = 10) -> List[Dict]:
    """Генерация квиз-вопросов по теме"""
    try:
        client = get_client()

        prompt = f"""
        Создай {count} квиз-вопросов (multiple choice) по теме: "{topic}".
        Верни ТОЛЬКО валидный JSON массив (без markdown):
        [
            {{
                "question": "Вопрос здесь?",
                "options": ["Вариант 1", "Вариант 2", "Вариант 3", "Вариант 4"],
                "correct_answers": [2],
                "explanation": "Объяснение правильного ответа",
                "image_query": "short english query"
            }}
        ]

        Требования:
        - 2-6 вариантов ответа на вопрос
        - correct_answers - индексы правильных ответов (от 0)
        - Можно несколько правильных ответов
        - Вопросы должны быть разнообразными и охватывать разные аспекты темы
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type='application/json',
                temperature=0.7
            )
        )

        text_response = response.text.strip()
        if text_response.startswith("```json"):
            text_response = text_response.replace("```json", "").replace("```", "")

        questions = json.loads(text_response)

        for question in questions:
            if question.get("image_query"):
                question["image_url"] = await search_image(question["image_query"])

        return questions[:count]

    except Exception as e:
        print(f"AI Error (Quiz from Topic): {e}")
        return generate_fallback_quiz(topic, count)


def generate_fallback_quiz(context: str, count: int) -> List[Dict]:
    """Заглушка для квизов при ошибках"""
    return [{
        "question": f"Ошибка генерации квиза #{i+1}",
        "options": ["Вариант A", "Вариант B", "Вариант C", "Вариант D"],
        "correct_answers": [0],
        "explanation": "Проверьте консоль сервера. Возможно, текст слишком короткий или API ключ не работает.",
        "image_query": "error"
    } for i in range(min(count, 3))]


async def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Чтение файлов"""
    import io
    filename = filename.lower()
    
    try:
        if filename.endswith('.txt'):
            return file_bytes.decode('utf-8', errors='ignore')
        
        elif filename.endswith('.pdf'):
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            return "\n".join([page.extract_text() for page in reader.pages])
            
        elif filename.endswith('.docx'):
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            return "\n".join([p.text for p in doc.paragraphs])
            
        else:
            return ""
    except Exception as e:
        print(f"File Error: {e}")
        return ""