"""
decks.py - Полный набор эндпоинтов для работы с колодами
С CLOUDINARY для хранения всех изображений
"""
import asyncio
import uuid
import time
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

from app.models import (
    User, Deck, Card, ContentItem, StudySession, CardReview, DailyStats,
    StudentDeckAccess, PydanticObjectId
)
from app.routes.auth import get_current_user
from app.services.ai_service import (
    generate_cards_from_text, generate_cards_from_topic, extract_text_from_file,
    generate_quiz_from_text, generate_quiz_from_topic
)
# Импортируем сервисы
from app.services.image_service import generate_image_pollinations
from app.services.cloudinary_service import upload_file, is_configured
import uuid
import time
router = APIRouter()

# Разрешенные типы файлов
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png", 
    "image/gif": ".gif",
    "image/webp": ".webp"
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


# === SCHEMAS ===

class CardInput(BaseModel):
    front: Optional[str] = None
    back: Optional[str] = None
    image_query: Optional[str] = None
    image_url: Optional[str] = None
    question: Optional[str] = None
    options: Optional[List[str]] = None
    correct_answers: Optional[List[int]] = None
    explanation: Optional[str] = None


class DeckCreate(BaseModel):
    name: str
    description: Optional[str] = None
    cards: List[CardInput]
    content_type: str = "flashcards"
    learning_mode: str = "all_at_once"
    cards_per_day: Optional[int] = 10
    total_cards: int
    generation_mode: Optional[str] = None
    source_info: Optional[str] = None
    is_public: bool = True


class DeckUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    learning_mode: Optional[str] = None
    cards_per_day: Optional[int] = None


class CardUpdate(BaseModel):
    front: Optional[str] = None
    back: Optional[str] = None
    image_query: Optional[str] = None
    image_url: Optional[str] = None


class StudyResult(BaseModel):
    correct: int
    incorrect: int
    skipped: int
    duration_seconds: int


class CardAnswer(BaseModel):
    quality: int
    time_taken: Optional[int] = None

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png", 
    "image/gif": ".gif",
    "image/webp": ".webp"
}
MAX_FILE_SIZE = 10 * 1024 * 1024

class ImageRequest(BaseModel):
    prompt: str


# =====================================================
# === ЭНДПОИНТЫ ДЛЯ РАБОТЫ С ИЗОБРАЖЕНИЯМИ (CLOUDINARY) ===
# =====================================================

@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Загрузка изображения в Cloudinary"""
    if not is_configured():
        raise HTTPException(status_code=503, detail="Cloudinary не настроен")
    
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Неподдерживаемый формат")
    
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Файл слишком большой")
    
    unique_id = f"user_{current_user.id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    image_url = await upload_file(content, "flashcards/user_uploads", unique_id)
    
    if not image_url:
        raise HTTPException(status_code=500, detail="Ошибка загрузки")
    
    return {"image_url": image_url}


@router.get("/cloudinary-status")
async def cloudinary_status():
    return {"configured": is_configured()}


@router.post("/generate-image-manual")
async def generate_image_manual(
    req: ImageRequest,
    current_user: User = Depends(get_current_user)
):
    """Генерация картинки AI по запросу (сохраняется в Cloudinary)"""
    if not req.prompt:
        raise HTTPException(status_code=400, detail="Пустой запрос")
    
    url = await generate_image_pollinations(req.prompt)
    
    if not url:
        raise HTTPException(status_code=500, detail="Не удалось найти изображение")
    
    return {"image_url": url}


@router.delete("/delete-image")
async def delete_image_endpoint(
    image_url: str = Query(...),
    current_user: User = Depends(get_current_user)
):
    """Удаление изображения из Cloudinary"""
    if "cloudinary.com" not in image_url:
        raise HTTPException(status_code=400, detail="Это не Cloudinary изображение")
    
    # Проверяем, что это изображение пользователя
    if f"user_{current_user.id}_" not in image_url:
        raise HTTPException(status_code=403, detail="Нет доступа к этому изображению")
    
    public_id = extract_public_id(image_url)
    if public_id:
        success = await delete_image(public_id)
        if success:
            return {"message": "Изображение удалено"}
    
    return {"message": "Не удалось удалить (возможно, уже удалено)"}


@router.get("/cloudinary-status")
async def cloudinary_status():
    """Проверка статуса Cloudinary"""
    return {
        "configured": is_configured(),
        "message": "Cloudinary настроен" if is_configured() else "Cloudinary не настроен"
    }


# =====================================================
# === ГЕНЕРАЦИЯ КАРТОЧЕК ===
# =====================================================

@router.post("/generate/preview")
async def generate_preview(
    text: Optional[str] = Form(None),
    topic: Optional[str] = Form(None),
    mode: str = Form(...),
    card_count: int = Form(20),
    learning_mode: str = Form("all_at_once"),
    cards_per_day: Optional[int] = Form(10),
    content_type: str = Form("flashcards"),
    file: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user)
):
    content = ""
    
    # 1. Получение текста
    if mode == "file":
        if not file:
            raise HTTPException(status_code=400, detail="Файл не загружен")
        file_bytes = await file.read()
        try:
            content = await extract_text_from_file(file_bytes, file.filename)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Ошибка чтения: {str(e)}")
    elif mode == "text":
        content = text
    
    # 2. Генерация AI
    items = []
    if mode == "topic":
        if content_type == "quiz":
            items = await generate_quiz_from_topic(topic, card_count)
        else:
            items = await generate_cards_from_topic(topic, card_count)
    else:
        if content_type == "quiz":
            items = await generate_quiz_from_text(content, card_count)
        else:
            items = await generate_cards_from_text(content, card_count)

    # 3. Генерация картинок (сохраняются в Cloudinary)
    print(f"🚀 Старт генерации картинок для {len(items)} объектов...")
    
    final_items = []
    for index, item in enumerate(items):
        query = item.get("image_query")
        if not query:
            if "question" in item:
                query = item["question"]
            elif "front" in item:
                query = item["front"]

        if query:
            try:
                print(f"[{index+1}/{len(items)}] Ищем: {query}")
                url = await generate_image_pollinations(query)
                item["image_url"] = url
            except Exception as e:
                print(f"Сбой поиска картинки: {e}")
                item["image_url"] = None
        
        final_items.append(item)

    print("✅ Все готово!")
    return {"cards": final_items}

@router.get("/my")
async def get_my_decks(
    limit: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """Получение моих колод с умным статусом"""
    query = Deck.find(Deck.user_id == current_user.id).sort(-Deck.updated_at)
    if limit:
        query = query.limit(limit)

    decks = await query.to_list()

    today = datetime.now()
    results = []

    for deck in decks:
        # Считаем всего и выученных
        total = await ContentItem.find(ContentItem.deck_id == deck.id).count()
        learned = await ContentItem.find(
            ContentItem.deck_id == deck.id,
            ContentItem.is_learned == True
        ).count()

        # Считаем "Долги" (Cards Due)
        new_due = await ContentItem.find(
            ContentItem.deck_id == deck.id,
            ContentItem.is_new == True,
            ContentItem.unlock_date <= today
        ).count()

        reviews_due = await ContentItem.find(
            ContentItem.deck_id == deck.id,
            ContentItem.is_new == False,
            ContentItem.next_review <= today
        ).count()

        cards_due = new_due + reviews_due

        # Определяем статус
        status = "active"

        if total == 0:
            status = "empty"
        elif learned == total and total > 0:
            status = "mastered"
        elif cards_due == 0 and learned > 0:
            status = "done_for_today"
        elif cards_due > 0:
            status = "active"
        else:
            status = "active"

        # Формируем ответ
        deck_dict = deck.dict()
        deck_dict["id"] = str(deck.id)
        deck_dict["total_cards"] = total
        deck_dict["learned_cards"] = learned
        deck_dict["cards_due"] = cards_due
        deck_dict["status"] = status

        if total > 0:
            deck_dict["progress"] = round((learned / total * 100), 1)
        else:
            deck_dict["progress"] = 0

        results.append(deck_dict)

    # Сортировка: Active -> Done -> Mastered -> Empty
    def sort_key(d):
        priority = {"active": 0, "done_for_today": 1, "mastered": 2, "empty": 3}
        return priority.get(d["status"], 4)

    results.sort(key=sort_key)

    return results
# =====================================================
# === СОЗДАНИЕ И УПРАВЛЕНИЕ КОЛОДАМИ ===
# =====================================================

@router.post("/")
async def create_deck(
    deck_data: DeckCreate,
    current_user: User = Depends(get_current_user)
):
    """Создание новой колоды или квиза"""

    new_deck = Deck(
        name=deck_data.name,
        description=deck_data.description,
        user_id=current_user.id,
        author_name=current_user.username,
        content_type=deck_data.content_type,
        learning_mode=deck_data.learning_mode,
        cards_per_day=deck_data.cards_per_day or 10,
        total_cards=len(deck_data.cards),
        generation_mode=deck_data.generation_mode,
        source_info=deck_data.source_info,
        is_public=deck_data.is_public,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    await new_deck.insert()

    # Вычисляем даты разблокировки для spaced режима
    unlock_dates = []
    if deck_data.learning_mode == "spaced":
        for i in range(len(deck_data.cards)):
            day_offset = i // (deck_data.cards_per_day or 10)
            unlock_date = datetime.now() + timedelta(days=day_offset)
            unlock_dates.append(unlock_date)

    # Создаем контент
    for idx, c in enumerate(deck_data.cards):
        if deck_data.content_type == "quiz":
            content_item = ContentItem(
                deck_id=new_deck.id,
                item_type="quiz_question",
                order=idx,
                question=c.question,
                options=c.options,
                correct_answers=c.correct_answers,
                explanation=c.explanation,
                image_query=c.image_query,
                image_url=c.image_url,
                unlock_date=unlock_dates[idx] if unlock_dates else datetime.now(),
                created_at=datetime.now()
            )
        else:
            content_item = ContentItem(
                deck_id=new_deck.id,
                item_type="flashcard",
                order=idx,
                front=c.front,
                back=c.back,
                image_query=c.image_query,
                image_url=c.image_url,
                unlock_date=unlock_dates[idx] if unlock_dates else datetime.now(),
                created_at=datetime.now()
            )
        await content_item.insert()

    message = "Квиз создан" if deck_data.content_type == "quiz" else "Колода создана"

    return {
        "id": str(new_deck.id),
        "message": message,
        "content_type": deck_data.content_type,
        "learning_mode": deck_data.learning_mode,
        "total_cards": len(deck_data.cards),
    }


@router.get("/")
async def get_user_decks(current_user: User = Depends(get_current_user)):
    """Получение всех колод пользователя"""
    decks = await Deck.find(Deck.user_id == current_user.id).sort(-Deck.created_at).to_list()
    
    result = []
    for deck in decks:
        total = await ContentItem.find(ContentItem.deck_id == deck.id).count()
        learned = await ContentItem.find(
            ContentItem.deck_id == deck.id,
            ContentItem.is_learned == True
        ).count()
        
        now = datetime.now()
        due = await ContentItem.find(
            ContentItem.deck_id == deck.id,
            ContentItem.unlock_date <= now,
            ContentItem.is_learned == False
        ).count()
        
        deck_dict = deck.dict()
        deck_dict["id"] = str(deck.id)
        deck_dict["total_cards"] = total
        deck_dict["learned_cards"] = learned
        deck_dict["cards_due"] = due
        deck_dict["progress"] = (learned / total * 100) if total > 0 else 0
        
        result.append(deck_dict)
    
    return result


@router.get("/public")
async def get_public_decks(
    search: Optional[str] = Query(None),
    content_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0)
):
    """Получение публичных колод"""
    query = {"is_public": True}
    
    if content_type:
        query["content_type"] = content_type
    
    decks_query = Deck.find(query)
    
    if search:
        decks_query = Deck.find(
            {"$and": [
                query,
                {"$or": [
                    {"name": {"$regex": search, "$options": "i"}},
                    {"description": {"$regex": search, "$options": "i"}}
                ]}
            ]}
        )
    
    decks = await decks_query.sort(-Deck.plays_count).skip(skip).limit(limit).to_list()
    
    result = []
    for deck in decks:
        deck_dict = deck.dict()
        deck_dict["id"] = str(deck.id)
        result.append(deck_dict)
    
    return result


@router.get("/{deck_id}")
async def get_deck(
    deck_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    """Получение информации о колоде"""
    deck = await Deck.get(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Колода не найдена")
    
    is_owner = deck.user_id == current_user.id
    has_access = await StudentDeckAccess.find_one(
        StudentDeckAccess.student_id == current_user.id,
        StudentDeckAccess.deck_id == deck_id
    )
    
    if not is_owner and not has_access and not deck.is_public:
        raise HTTPException(status_code=403, detail="Нет доступа к этой колоде")
    
    deck.views_count += 1
    await deck.save()
    
    total = await ContentItem.find(ContentItem.deck_id == deck_id).count()
    learned = await ContentItem.find(
        ContentItem.deck_id == deck_id,
        ContentItem.is_learned == True
    ).count()
    
    now = datetime.now()
    due = await ContentItem.find(
        ContentItem.deck_id == deck_id,
        ContentItem.unlock_date <= now,
        ContentItem.is_learned == False
    ).count()
    
    if total == 0:
        status = "empty"
    elif learned == total:
        status = "mastered"
    elif due == 0 and deck.learning_mode == "spaced":
        status = "done_for_today"
    else:
        status = "active"
    
    deck_dict = deck.dict()
    deck_dict["id"] = str(deck.id)
    deck_dict["total_cards"] = total
    deck_dict["learned_cards"] = learned
    deck_dict["cards_due"] = due
    deck_dict["status"] = status
    deck_dict["is_owner"] = is_owner
    
    return deck_dict


@router.put("/{deck_id}")
async def update_deck(
    deck_id: PydanticObjectId,
    update_data: DeckUpdate,
    current_user: User = Depends(get_current_user)
):
    """Обновление колоды"""
    deck = await Deck.get(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Колода не найдена")
    
    if deck.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет прав на редактирование")
    
    update_dict = update_data.dict(exclude_unset=True)
    update_dict["updated_at"] = datetime.now()
    
    for key, value in update_dict.items():
        setattr(deck, key, value)
    
    await deck.save()
    
    return {"message": "Колода обновлена"}


@router.delete("/{deck_id}")
async def delete_deck(
    deck_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    """Удаление колоды"""
    deck = await Deck.get(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Колода не найдена")
    
    if deck.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет прав на удаление")
    
    await ContentItem.find(ContentItem.deck_id == deck_id).delete()
    await deck.delete()
    
    return {"message": "Колода удалена"}


@router.post("/{deck_id}/reset")
async def reset_deck_progress(
    deck_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    """Сброс прогресса колоды"""
    deck = await Deck.get(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Колода не найдена")
    
    cards = await ContentItem.find(ContentItem.deck_id == deck_id).to_list()
    
    for card in cards:
        card.is_new = True
        card.is_learned = False
        card.repetitions = 0
        card.interval = 0
        card.ease_factor = 2.5
        card.times_reviewed = 0
        card.times_correct = 0
        card.times_incorrect = 0
        card.difficulty = 0.0
        card.last_review = None
        card.next_review = None
        await card.save()
    
    return {"message": "Прогресс сброшен", "cards_reset": len(cards)}


# =====================================================
# === СЕССИИ ИЗУЧЕНИЯ ===
# =====================================================

@router.get("/{deck_id}/study-session")
async def get_study_session(
    deck_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    """Получение карточек для изучения"""
    deck = await Deck.get(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Колода не найдена")
    
    now = datetime.now()
    
    if deck.learning_mode == "spaced":
        new_cards = await ContentItem.find(
            ContentItem.deck_id == deck_id,
            ContentItem.is_new == True,
            ContentItem.unlock_date <= now
        ).sort(+ContentItem.order).limit(deck.cards_per_day).to_list()
        
        review_cards = await ContentItem.find(
            ContentItem.deck_id == deck_id,
            ContentItem.is_new == False,
            ContentItem.is_learned == False,
            ContentItem.next_review <= now
        ).sort(+ContentItem.next_review).to_list()
    else:
        new_cards = await ContentItem.find(
            ContentItem.deck_id == deck_id,
            ContentItem.is_learned == False
        ).sort(+ContentItem.order).to_list()
        
        review_cards = []
    
    def format_card(card):
        card_dict = card.dict()
        card_dict["_id"] = str(card.id)
        return card_dict
    
    return {
        "new_cards": [format_card(c) for c in new_cards],
        "review_cards": [format_card(c) for c in review_cards],
        "total_new": len(new_cards),
        "total_review": len(review_cards)
    }


@router.get("/{deck_id}/cards")
async def get_deck_cards(
    deck_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    """Получение всех карточек колоды"""
    deck = await Deck.get(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Колода не найдена")
    
    cards = await ContentItem.find(
        ContentItem.deck_id == deck_id
    ).sort(+ContentItem.order).to_list()
    
    result = []
    for card in cards:
        card_dict = card.dict()
        card_dict["id"] = str(card.id)
        result.append(card_dict)
    
    return result


@router.post("/cards/{card_id}/answer")
async def answer_card(
    card_id: PydanticObjectId,
    answer: CardAnswer,
    current_user: User = Depends(get_current_user)
):
    """Ответ на карточку с SM-2 алгоритмом"""
    card = await ContentItem.get(card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    
    deck = await Deck.get(card.deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Колода не найдена")
    
    interval_before = card.interval
    
    if answer.quality >= 3:
        if card.repetitions == 0:
            card.interval = 1
        elif card.repetitions == 1:
            card.interval = 6
        else:
            card.interval = round(card.interval * card.ease_factor)
        
        card.repetitions += 1
        card.ease_factor = max(
            1.3,
            card.ease_factor + (0.1 - (5 - answer.quality) * (0.08 + (5 - answer.quality) * 0.02))
        )
        card.times_correct += 1
        
        if deck.learning_mode == "all_at_once":
            card.is_learned = True
        else:
            if card.repetitions >= 3 and card.interval >= 7:
                card.is_learned = True
    else:
        card.repetitions = 0
        card.interval = 1
        card.ease_factor = max(1.3, card.ease_factor - 0.2)
        card.times_incorrect += 1
        card.is_learned = False
    
    card.is_new = False
    card.times_reviewed += 1
    card.last_review = datetime.now()
    card.next_review = datetime.now() + timedelta(days=card.interval)
    
    if card.times_reviewed > 0:
        card.difficulty = 1.0 - (card.times_correct / card.times_reviewed)
    
    await card.save()
    
    review = CardReview(
        card_id=card_id,
        user_id=current_user.id,
        deck_id=card.deck_id,
        quality=answer.quality,
        answer="good" if answer.quality >= 3 else "again",
        time_taken=answer.time_taken,
        interval_before=interval_before,
        interval_after=card.interval,
        ease_factor_after=card.ease_factor,
        created_at=datetime.now()
    )
    await review.insert()
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    daily_stats = await DailyStats.find_one(
        DailyStats.user_id == current_user.id,
        DailyStats.date == today
    )
    
    if not daily_stats:
        daily_stats = DailyStats(
            user_id=current_user.id,
            date=today,
            new_cards_learned=0,
            cards_reviewed=0,
            correct_answers=0,
            incorrect_answers=0,
            study_time_seconds=0,
            decks_studied=[],
            sessions_completed=0
        )
    
    if card.times_reviewed == 1:
        daily_stats.new_cards_learned += 1
    else:
        daily_stats.cards_reviewed += 1
    
    if answer.quality >= 3:
        daily_stats.correct_answers += 1
    else:
        daily_stats.incorrect_answers += 1
    
    if card.deck_id not in daily_stats.decks_studied:
        daily_stats.decks_studied.append(card.deck_id)
    
    if answer.time_taken:
        daily_stats.study_time_seconds += answer.time_taken
    
    await daily_stats.save()
    
    return {
        "message": "Ответ сохранен",
        "next_review": card.next_review,
        "interval": card.interval
    }


@router.post("/{deck_id}/complete-session")
async def complete_session(
    deck_id: PydanticObjectId,
    result: StudyResult,
    current_user: User = Depends(get_current_user)
):
    """Завершение сессии"""
    deck = await Deck.get(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Колода не найдена")
    
    deck.plays_count += 1
    await deck.save()
    
    total = result.correct + result.incorrect + result.skipped
    accuracy = (result.correct / total * 100) if total > 0 else 0
    
    session = StudySession(
        user_id=current_user.id,
        deck_id=deck_id,
        total_cards=total,
        correct=result.correct,
        incorrect=result.incorrect,
        skipped=result.skipped,
        started_at=datetime.now() - timedelta(seconds=result.duration_seconds),
        completed_at=datetime.now(),
        duration_seconds=result.duration_seconds,
        accuracy=accuracy
    )
    await session.insert()

    access = await StudentDeckAccess.find_one(
        StudentDeckAccess.student_id == current_user.id,
        StudentDeckAccess.deck_id == deck_id
    )

    if access:
        total_cards_count = await ContentItem.find(ContentItem.deck_id == deck_id).count()
        learned_cards_count = await ContentItem.find(
            ContentItem.deck_id == deck_id,
            ContentItem.is_learned == True
        ).count()
        
        access.cards_studied = learned_cards_count
        access.progress = (learned_cards_count / total_cards_count * 100) if total_cards_count > 0 else 0
        access.last_studied = datetime.now()
        
        await access.save()

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    daily_stats = await DailyStats.find_one(
        DailyStats.user_id == current_user.id,
        DailyStats.date == today
    )
    if daily_stats:
        daily_stats.sessions_completed += 1
        await daily_stats.save()
    
    return {"message": "Сессия завершена", "session_id": str(session.id)}
# =====================================================
# === ПРЕВЬЮ И КЛОНИРОВАНИЕ ===
# =====================================================

@router.get("/{deck_id}/preview")
async def get_deck_preview(
    deck_id: PydanticObjectId,
    current_user: Optional[User] = Depends(get_current_user)
):
    """Превью первых 5 карточек колоды"""
    deck = await Deck.get(deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Колода не найдена")
    
    # Проверка доступа
    if not deck.is_public:
        if not current_user or deck.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Нет доступа")
    
    # Получаем первые 5 карточек
    cards = await ContentItem.find(
        ContentItem.deck_id == deck_id
    ).sort(+ContentItem.order).limit(5).to_list()
    
    result = []
    for card in cards:
        card_dict = {
            "_id": str(card.id),
            "front": card.front,
            "back": card.back,
            "question": card.question,
            "options": card.options,
            "image_url": card.image_url
        }
        result.append(card_dict)
    
    return {"cards": result}


@router.post("/{deck_id}/clone")
async def clone_deck(
    deck_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    """Копирование публичной колоды к себе"""
    original = await Deck.get(deck_id)
    if not original:
        raise HTTPException(status_code=404, detail="Колода не найдена")
    
    # Нельзя клонировать свою же колоду
    if original.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Это уже ваша колода")
    
    # Проверка что колода публичная
    if not original.is_public:
        raise HTTPException(status_code=403, detail="Колода приватная")
    
    # Создаём копию колоды
    new_deck = Deck(
        name=original.name,
        description=original.description,
        user_id=current_user.id,
        author_name=current_user.username,
        content_type=original.content_type,
        learning_mode=original.learning_mode,
        cards_per_day=original.cards_per_day,
        total_cards=original.total_cards,
        generation_mode=original.generation_mode,
        source_info=f"Скопировано от {original.author_name}",
        is_public=False,  # Копия по умолчанию приватная
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    await new_deck.insert()
    
    # Копируем все карточки
    original_cards = await ContentItem.find(
        ContentItem.deck_id == deck_id
    ).sort(+ContentItem.order).to_list()
    
    for card in original_cards:
        new_card = ContentItem(
            deck_id=new_deck.id,
            item_type=card.item_type,
            order=card.order,
            front=card.front,
            back=card.back,
            question=card.question,
            options=card.options,
            correct_answers=card.correct_answers,
            explanation=card.explanation,
            image_query=card.image_query,
            image_url=card.image_url,
            unlock_date=datetime.now(),
            created_at=datetime.now()
        )
        await new_card.insert()
    
    return {
        "message": "Колода скопирована",
        "new_deck_id": str(new_deck.id)
    }

# =====================================================
# === СТАТИСТИКА ===
# =====================================================

@router.get("/stats/history")
async def get_study_history(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user)
):
    """История прохождений"""
    sessions = await StudySession.find(
        StudySession.user_id == current_user.id
    ).sort(-StudySession.completed_at).limit(limit).to_list()
    
    result = []
    for session in sessions:
        session_dict = session.dict()
        deck = await Deck.get(session.deck_id)
        session_dict["deck_name"] = deck.name if deck else "Удаленная колода"
        result.append(session_dict)
    
    return result


@router.get("/stats/today")
async def get_today_stats(current_user: User = Depends(get_current_user)):
    """Статистика за сегодня"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    stats = await DailyStats.find_one(
        DailyStats.user_id == current_user.id,
        DailyStats.date == today
    )
    
    if not stats:
        return {
            "new_cards_learned": 0,
            "cards_reviewed": 0,
            "correct_answers": 0,
            "incorrect_answers": 0,
            "study_time_seconds": 0,
            "decks_studied": [],
            "sessions_completed": 0
        }
    
    return stats.dict()


@router.get("/stats/week")
async def get_week_stats(current_user: User = Depends(get_current_user)):
    """Статистика за неделю"""
    week_ago = datetime.now() - timedelta(days=7)
    week_ago = week_ago.replace(hour=0, minute=0, second=0, microsecond=0)
    
    stats = await DailyStats.find(
        DailyStats.user_id == current_user.id,
        DailyStats.date >= week_ago
    ).sort(+DailyStats.date).to_list()
    
    return stats