"""
database.py - Инициализация подключения к MongoDB
"""

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.config import settings
from app.models import (
    User, Card, Deck, ContentItem, StudySession, CardReview,
    DailyStats, DeckInvitation, StudentDeckAccess,
    LiveSession, LiveSessionResult
)
async def init_db():
    """Инициализация базы данных"""
    client = AsyncIOMotorClient(settings.MONGO_URI)
    
    await init_beanie(
        database=client.nuokai_db,
        document_models=[
            User,
            Card,
            Deck,
            ContentItem,
            StudySession,
            CardReview,
            DailyStats,
            DeckInvitation,
            StudentDeckAccess,
            LiveSession,
            LiveSessionResult
        ]
    )
    print("✅ Database initialized successfully")