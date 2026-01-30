"""
models.py - Полная модель данных с поддержкой системы приглашений для учителей
"""

from typing import List, Optional
from datetime import datetime
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
import random
import string


class Deck(Document):
    name: str
    description: Optional[str] = None
    user_id: PydanticObjectId
    author_name: Optional[str] = None

    # Тип контента
    content_type: str = "flashcards"  # "flashcards" | "quiz"

    # Режимы обучения
    learning_mode: str = "all_at_once"
    cards_per_day: int = 10
    total_cards: int = 0

    # Метаданные генерации
    generation_mode: Optional[str] = None
    source_info: Optional[str] = None

    # Публичность
    is_public: bool = True
    
    # Статистика
    plays_count: int = 0
    views_count: int = 0
    
    # Даты
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    start_date: datetime = Field(default_factory=datetime.now)
    
    class Settings:
        name = "decks"


class Card(Document):
    """Модель карточки с SM-2 алгоритмом"""

    deck_id: PydanticObjectId
    front: str
    back: str
    image_query: Optional[str] = None
    image_url: Optional[str] = None

    # SM-2 параметры
    is_new: bool = True
    is_learned: bool = False
    repetitions: int = 0
    interval: int = 0
    ease_factor: float = 2.5

    # Статистика
    times_reviewed: int = 0
    times_correct: int = 0
    times_incorrect: int = 0
    difficulty: float = 0.0

    # Временные метки
    created_at: datetime = Field(default_factory=datetime.now)
    last_review: Optional[datetime] = None
    next_review: Optional[datetime] = None
    unlock_date: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "cards"
        indexes = [
            "deck_id",
            "is_new",
            "next_review",
            "unlock_date"
        ]


class ContentItem(Document):
    """Унифицированная модель для карточек и квиз-вопросов"""

    deck_id: PydanticObjectId
    item_type: str  # "flashcard" | "quiz_question"
    order: int = 0

    # Поля для карточек (null для квиз-вопросов)
    front: Optional[str] = None
    back: Optional[str] = None
    image_query: Optional[str] = None
    image_url: Optional[str] = None

    # Поля для квиз-вопросов (null для карточек)
    question: Optional[str] = None
    options: Optional[List[str]] = None  # 2-6 вариантов ответа
    correct_answers: Optional[List[int]] = None  # индексы правильных ответов
    explanation: Optional[str] = None

    # SM-2 параметры (только для карточек)
    is_new: bool = True
    is_learned: bool = False
    repetitions: int = 0
    interval: int = 0
    ease_factor: float = 2.5

    # Статистика
    times_reviewed: int = 0
    times_correct: int = 0
    times_incorrect: int = 0
    difficulty: float = 0.0

    # Временные метки
    created_at: datetime = Field(default_factory=datetime.now)
    last_review: Optional[datetime] = None
    next_review: Optional[datetime] = None
    unlock_date: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "content_items"
        indexes = [
            "deck_id",
            "item_type",
            "is_new",
            "next_review",
            "unlock_date"
        ]


class DeckInvitation(Document):
    """Приглашение к колоде для учителей"""
    deck_id: PydanticObjectId
    teacher_id: PydanticObjectId
    code: str = Field(default_factory=lambda: ''.join(random.choices(string.digits, k=8)))
    
    # Статистика использования
    uses_count: int = 0
    max_uses: Optional[int] = None  # None = неограниченно
    
    # Список студентов, которые присоединились
    joined_students: List[PydanticObjectId] = []
    
    # Настройки
    is_active: bool = True
    expires_at: Optional[datetime] = None
    
    # Даты
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Settings:
        name = "deck_invitations"
        indexes = ["code", "deck_id", "teacher_id"]


class StudentDeckAccess(Document):
    """Доступ студента к колоде учителя"""
    student_id: PydanticObjectId
    deck_id: PydanticObjectId
    teacher_id: PydanticObjectId
    invitation_code: str
    
    # Прогресс студента
    progress: float = 0.0  # Процент завершения
    cards_studied: int = 0
    last_studied: Optional[datetime] = None
    
    # Метаданные
    joined_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = True
    
    class Settings:
        name = "student_deck_access"
        indexes = [
            ("student_id", "deck_id"),
            "teacher_id",
            "deck_id"
        ]

class LiveSession(Document):
    """Реалтайм сессия для совместного обучения"""
    deck_id: PydanticObjectId
    teacher_id: PydanticObjectId
    # Код из 6 цифр для удобного ввода
    session_code: str = Field(default_factory=lambda: ''.join(random.choices(string.digits, k=6)))

    # Настройки
    max_participants: int = 50
    
    # Статус: "waiting" (лобби), "active" (игра идет), "completed" (завершено)
    status: str = "waiting" 

    # Участники: [{nickname, joined_at, score, progress}]
    # Мы храним их тут для быстрого доступа к списку в лобби
    participants: List[dict] = []

    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Settings:
        name = "live_sessions"
        indexes = ["session_code", "teacher_id", "status"]

class LiveSessionResult(Document):
    """Детальные ответы участника"""
    session_id: PydanticObjectId
    participant_nickname: str
    
    score: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    
    # Детали ответов: [{card_id, quality/correct, time_taken}]
    answers: List[dict] = []
    
    created_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "live_session_results"
        indexes = ["session_id", "participant_nickname"]
        
class CardReview(Document):
    """История ответов на карточку"""
    card_id: PydanticObjectId
    user_id: PydanticObjectId
    deck_id: PydanticObjectId
    quality: int
    answer: str
    time_taken: Optional[int] = None
    
    interval_before: int
    interval_after: int
    ease_factor_after: float
    
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Settings:
        name = "card_reviews"
        indexes = ["card_id", "user_id", "created_at"]


class StudySession(Document):
    """Сессия изучения"""
    user_id: PydanticObjectId
    deck_id: PydanticObjectId
    
    total_cards: int
    correct: int
    incorrect: int
    skipped: int
    
    started_at: datetime
    completed_at: datetime
    duration_seconds: int
    accuracy: float
    
    class Settings:
        name = "study_sessions"
        indexes = ["user_id", "deck_id", "completed_at"]


class DailyStats(Document):
    """Ежедневная статистика пользователя"""
    user_id: PydanticObjectId
    date: datetime
    
    new_cards_learned: int = 0
    cards_reviewed: int = 0
    correct_answers: int = 0
    incorrect_answers: int = 0
    study_time_seconds: int = 0
    
    decks_studied: List[PydanticObjectId] = []
    sessions_completed: int = 0
    
    class Settings:
        name = "daily_stats"
        indexes = [
            ("user_id", "date"),
        ]


class User(Document):
    email: str = Field(index=True, unique=True)
    hashed_password: str
    username: str
    role: str = "student"

    # Настройки
    daily_goal: int = 20
    timezone: str = "UTC"

    created_at: datetime = Field(default_factory=datetime.now)

    class Settings:
        name = "users"


class LiveSession(Document):
    """Реалтайм сессия для совместного обучения"""

    deck_id: PydanticObjectId
    teacher_id: PydanticObjectId
    session_code: str = Field(default_factory=lambda: ''.join(random.choices(string.digits, k=6)))

    # Настройки сессии
    max_participants: int = 50
    allow_anonymous: bool = True

    # Статус
    status: str = "waiting"  # "waiting" | "active" | "completed" | "cancelled"

    # Участники: [{nickname, user_id?, joined_at, is_anonymous}]
    participants: List[dict] = []

    # Временные метки
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    class Settings:
        name = "live_sessions"
        indexes = ["session_code", "teacher_id", "status", "created_at"]


class LiveSessionResult(Document):
    """Результат участника в live сессии"""

    session_id: PydanticObjectId
    participant_nickname: str
    user_id: Optional[PydanticObjectId] = None  # null если анонимный

    # Метрики производительности
    score: float = 0.0  # 0-100
    correct_count: int = 0
    incorrect_count: int = 0
    total_items: int = 0

    # Детали ответов для обзора: [{item_id, answer, correct, time_taken}]
    answers: List[dict] = []

    # Тайминги (ИСПРАВЛЕНО: добавлены значения по умолчанию)
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    duration_seconds: int = 0

    class Settings:
        name = "live_session_results"
        indexes = ["session_id", "user_id"]