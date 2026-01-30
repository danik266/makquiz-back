"""
app/routes/live.py
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import traceback  # Импортируем для отладки

from app.models import (
    User, Deck, ContentItem, LiveSession, LiveSessionResult, PydanticObjectId
)
from app.routes.auth import get_current_user

router = APIRouter()

# --- Schemas ---

class CreateSessionRequest(BaseModel):
    deck_id: str
    max_participants: int = 50

class JoinSessionRequest(BaseModel):
    code: str
    nickname: str

class SubmitAnswerRequest(BaseModel):
    card_id: str
    is_correct: bool
    time_taken: int
    nickname: str  # Обязательное поле!

# --- Teacher Endpoints ---

@router.post("/create")
async def create_session(
    data: CreateSessionRequest,
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Только учителя могут создавать сессии")

    try:
        deck = await Deck.get(PydanticObjectId(data.deck_id))
    except:
        raise HTTPException(status_code=404, detail="Неверный ID колоды")
        
    if not deck:
        raise HTTPException(status_code=404, detail="Колода не найдена")

    session = LiveSession(
        deck_id=deck.id,
        teacher_id=current_user.id,
        max_participants=data.max_participants,
        status="waiting",
        participants=[]
    )
    await session.insert()

    return {
        "session_id": str(session.id),
        "code": session.session_code,
        "deck_name": deck.name
    }

@router.post("/{session_id}/start")
async def start_session(
    session_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    session = await LiveSession.get(session_id)
    if not session or session.teacher_id != current_user.id:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    session.status = "active"
    session.started_at = datetime.now()
    await session.save()
    return {"status": "active"}

@router.post("/{session_id}/finish")
async def finish_session(
    session_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    session = await LiveSession.get(session_id)
    if not session or session.teacher_id != current_user.id:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    session.status = "completed"
    session.completed_at = datetime.now()
    await session.save()
    return {"status": "completed"}

@router.get("/{session_id}/stats")
async def get_session_stats_teacher(
    session_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    session = await LiveSession.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    if session.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")

    results = await LiveSessionResult.find(
        LiveSessionResult.session_id == session.id
    ).to_list()

    return {
        "code": session.session_code,
        "status": session.status,
        "participants_count": len(session.participants),
        "participants_list": session.participants,
        "results": [
            {
                "nickname": r.participant_nickname,
                "score": r.score,
                "correct": r.correct_count,
                "incorrect": r.incorrect_count
            } for r in results
        ]
    }

@router.get("/history")
async def get_teacher_history(current_user: User = Depends(get_current_user)):
    sessions = await LiveSession.find(
        LiveSession.teacher_id == current_user.id
    ).sort(-LiveSession.created_at).limit(20).to_list()

    response = []
    for s in sessions:
        deck = await Deck.get(s.deck_id)
        response.append({
            "id": str(s.id),
            "code": s.session_code,
            "deck_name": deck.name if deck else "Удалена",
            "date": s.created_at,
            "participants": len(s.participants),
            "status": s.status
        })
    return response

# --- Student/Player Endpoints ---

@router.post("/join")
async def join_session(request: JoinSessionRequest):
    """Студент присоединяется к сессии"""
    session = await LiveSession.find_one(
        LiveSession.session_code == request.code,
        LiveSession.status == "waiting"
    )
    
    # Если не нашли в ожидании, ищем в активных (реконнект)
    if not session:
        session = await LiveSession.find_one(
            LiveSession.session_code == request.code,
            LiveSession.status == "active"
        )
    
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена или завершена")

    # Проверка уникальности ника (если новый)
    is_new = not any(p['nickname'] == request.nickname for p in session.participants)
    
    if is_new:
        if len(session.participants) >= session.max_participants:
            raise HTTPException(status_code=400, detail="Комната полна")
        
        session.participants.append({
            "nickname": request.nickname,
            "joined_at": datetime.now().isoformat()
        })
        await session.save()

    return {
        "message": "Joined",
        "session_id": str(session.id),
        "deck_id": str(session.deck_id)
    }

@router.get("/{session_id}/status")
async def get_session_status_player(session_id: PydanticObjectId):
    session = await LiveSession.get(session_id)
    if not session:
        raise HTTPException(status_code=404)
    return {"status": session.status}

@router.get("/{session_id}/cards")
async def get_session_cards(session_id: PydanticObjectId):
    """Получить карточки без авторизации (для Live)"""
    session = await LiveSession.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    # Получаем контент
    cards = await ContentItem.find(
        ContentItem.deck_id == session.deck_id
    ).sort(+ContentItem.order).to_list()
    
    return cards
@router.post("/{session_id}/review")
async def review_session(
    session_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    session = await LiveSession.get(session_id)
    if not session or session.teacher_id != current_user.id:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    session.status = "review" # Новый статус
    await session.save()
    return {"status": "review"}
@router.post("/{session_id}/answer")
async def submit_live_answer(
    session_id: PydanticObjectId,
    data: SubmitAnswerRequest
):
    """Студент отправляет ответ (с возвратом очков)"""
    try:
        session = await LiveSession.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
            
        if session.status != "active":
            if session.status == "completed":
                 return {"status": "game_over", "score": 0} # Или вернуть текущий счет, если найдем
            return {"error": "Session not active"}

        # Ищем результат
        result = await LiveSessionResult.find_one(
            LiveSessionResult.session_id == session.id,
            LiveSessionResult.participant_nickname == data.nickname
        )
        
        # Если результата нет (первый ответ), создаем его
        if not result:
            result = LiveSessionResult(
                session_id=session.id,
                participant_nickname=data.nickname,
                score=0.0,
                correct_count=0,
                incorrect_count=0,
                answers=[]
            )
            await result.insert()

        # Добавляем ответ
        new_answer = {
            "card_id": data.card_id,
            "is_correct": data.is_correct,
            "time_taken": data.time_taken
        }
        
        if result.answers is None:
            result.answers = []
            
        result.answers.append(new_answer)
        
        if data.is_correct:
            result.correct_count += 1
            # Расчет очков: чем быстрее, тем больше (макс 1000)
            # data.time_taken приходит с фронта (там у вас пока хардкод 5 сек)
            score_add = max(500, 1000 - (data.time_taken * 10))
            result.score += float(score_add)
        else:
            result.incorrect_count += 1
            
        await result.save()
        
        # === ВОТ ГЛАВНОЕ ИЗМЕНЕНИЕ ===
        # Возвращаем текущий счет обратно на фронтенд
        return {
            "status": "ok",
            "score": int(result.score)  # Превращаем в int, чтобы было красиво (950, а не 950.0)
        }

    except Exception as e:
        print("🔥 ERROR in submit_live_answer:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))