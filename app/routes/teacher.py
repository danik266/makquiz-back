"""
teacher.py - API для учителей (приглашения, управление студентами)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

from app.models import (
    User, Deck, DeckInvitation, StudentDeckAccess, 
    StudySession, PydanticObjectId
)
from app.routes.auth import get_current_user

router = APIRouter()


# === SCHEMAS ===

class CreateInvitationRequest(BaseModel):
    deck_id: str
    max_uses: Optional[int] = None
    expires_in_days: Optional[int] = None


class JoinDeckRequest(BaseModel):
    code: str


# === TEACHER ENDPOINTS ===

@router.post("/invitations/create")
async def create_invitation(
    request: CreateInvitationRequest,
    current_user: User = Depends(get_current_user)
):
    """Создать приглашение к колоде (только для учителей)"""
    
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Доступно только учителям")
    
    deck_id = PydanticObjectId(request.deck_id)
    deck = await Deck.get(deck_id)
    
    if not deck or deck.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Колода не найдена или не принадлежит вам")
    
    # Проверяем, есть ли уже активное приглашение
    existing = await DeckInvitation.find_one({
        "deck_id": deck_id,
        "teacher_id": current_user.id,
        "is_active": True
    })
    
    if existing:
        # Возвращаем существующее с правильным форматом
        return {
            "code": existing.code,
            "deck_name": deck.name,
            "uses_count": existing.uses_count,
            "max_uses": existing.max_uses,
            "expires_at": existing.expires_at,
            "invitation_id": str(existing.id),
            "is_active": existing.is_active,
            # ВОТ ТУТ ТЫ ЗАБЫЛ ПРОВЕРКУ! Исправь на это:
            "students_count": len(existing.joined_students) if existing.joined_students else 0
        }
    
    # Создаем новое приглашение
    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.now() + timedelta(days=request.expires_in_days)
    
    invitation = DeckInvitation(
        deck_id=deck_id,
        teacher_id=current_user.id,
        max_uses=request.max_uses,
        expires_at=expires_at,
        is_active=True
    )
    await invitation.insert()
    
    return {
        "code": invitation.code,
        "deck_name": deck.name,
        "uses_count": 0,
        "max_uses": invitation.max_uses,
        "expires_at": invitation.expires_at,
        "invitation_id": str(invitation.id),
        "students_count": 0,  # ДОБАВЛЕНО
        "is_active": True  # ДОБАВЛЕНО
    }

@router.get("/invitations/my")
async def get_my_invitations(
    current_user: User = Depends(get_current_user)
):
    """Получить все мои приглашения"""
    
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Доступно только учителям")
    
    invitations = await DeckInvitation.find(
        {"teacher_id": current_user.id}
    ).sort("-created_at").to_list()
    
    result = []
    for inv in invitations:
        deck = await Deck.get(inv.deck_id)
        result.append({
            "id": str(inv.id),
            "code": inv.code,
            "deck_id": str(inv.deck_id),
            "deck_name": deck.name if deck else "Удалена",
            "uses_count": inv.uses_count,
            "max_uses": inv.max_uses,
            "is_active": inv.is_active,
            "expires_at": inv.expires_at,
            "created_at": inv.created_at,
            "students_count": len(inv.joined_students) if inv.joined_students else 0
        })
    
    return result


@router.delete("/invitations/{invitation_id}")
async def deactivate_invitation(
    invitation_id: PydanticObjectId,
    current_user: User = Depends(get_current_user)
):
    """Деактивировать приглашение"""
    
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Доступно только учителям")
    
    invitation = await DeckInvitation.get(invitation_id)
    if not invitation or invitation.teacher_id != current_user.id:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    
    invitation.is_active = False
    await invitation.save()
    
    return {"message": "Приглашение деактивировано"}


@router.get("/students")
async def get_my_students(
    deck_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """Получить список студентов (по всем колодам или конкретной)"""
    
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Доступно только учителям")
    
    query = StudentDeckAccess.find({"teacher_id": current_user.id})    

    if deck_id:
        query = query.find({"deck_id": PydanticObjectId(deck_id)})
    
    accesses = await query.sort(-StudentDeckAccess.joined_at).to_list()
    
    result = []
    for access in accesses:
        student = await User.get(access.student_id)
        deck = await Deck.get(access.deck_id)
        
        # ✅ ИСПРАВЛЕНО: Используем find() вместо find_one(), чтобы иметь возможность сортировать,
        # а затем забираем первый результат через .first_or_none()
        last_session = await StudySession.find(
    StudySession.user_id == access.student_id,
    StudySession.deck_id == access.deck_id
).sort(-StudySession.completed_at).first_or_none()
        
        result.append({
            "student_id": str(access.student_id),
            "student_name": student.username if student else "Неизвестно",
            "student_email": student.email if student else "Неизвестно",
            "deck_id": str(access.deck_id),
            "deck_name": deck.name if deck else "Удалена",
            "progress": round(access.progress, 1) if access.progress is not None else 0,
            "cards_studied": access.cards_studied or 0,
            "last_studied": access.last_studied,
            "joined_at": access.joined_at,
            "last_session_accuracy": last_session.accuracy if last_session else None,
            "is_active": access.is_active
        })
    
    return result

@router.get("/students/{student_id}/progress")
async def get_student_progress(
    student_id: PydanticObjectId,
    deck_id: str,
    current_user: User = Depends(get_current_user)
):
    """Детальный прогресс студента по колоде"""
    
    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Доступно только учителям")
    
    deck_id_obj = PydanticObjectId(deck_id)
    
    # Проверяем доступ
    access = await StudentDeckAccess.find_one(
        StudentDeckAccess.student_id == student_id,
        StudentDeckAccess.deck_id == deck_id_obj,
        StudentDeckAccess.teacher_id == current_user.id
    )
    
    if not access:
        raise HTTPException(status_code=404, detail="Студент не найден")
    
    # Получаем сессии студента
    sessions = await StudySession.find(
        StudySession.user_id == student_id,
        StudySession.deck_id == deck_id_obj
    ).sort(-StudySession.completed_at).limit(20).to_list()
    
    student = await User.get(student_id)
    deck = await Deck.get(deck_id_obj)
    
    return {
        "student": {
            "id": str(student_id),
            "name": student.username if student else "Неизвестно",
            "email": student.email if student else "Неизвестно"
        },
        "deck": {
            "id": str(deck_id),
            "name": deck.name if deck else "Удалена"
        },
        "overall_progress": access.progress,
        "cards_studied": access.cards_studied,
        "joined_at": access.joined_at,
        "last_studied": access.last_studied,
        "sessions": [
            {
                "completed_at": s.completed_at,
                "total_cards": s.total_cards,
                "correct": s.correct,
                "incorrect": s.incorrect,
                "accuracy": round(s.accuracy, 1) if s.accuracy is not None else 0,
                "duration_seconds": s.duration_seconds
            }
            for s in sessions
        ]
    }


# === STUDENT ENDPOINTS ===

@router.post("/join")
async def join_deck(
    request: JoinDeckRequest,
    current_user: User = Depends(get_current_user)
):
    """Присоединиться к колоде по коду"""
    
    # Ищем приглашение
    invitation = await DeckInvitation.find_one(
        DeckInvitation.code == request.code,
        DeckInvitation.is_active == True
    )
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Неверный код или приглашение неактивно")
    
    # Проверяем срок действия
    if invitation.expires_at and invitation.expires_at < datetime.now():
        raise HTTPException(status_code=400, detail="Срок действия приглашения истек")
    
    # Проверяем лимит использований
    if invitation.max_uses and invitation.uses_count >= invitation.max_uses:
        raise HTTPException(status_code=400, detail="Достигнут лимит использований приглашения")
    
    # Проверяем, не присоединялся ли уже
    existing = await StudentDeckAccess.find_one(
        StudentDeckAccess.student_id == current_user.id,
        StudentDeckAccess.deck_id == invitation.deck_id
    )
    
    if existing:
        return {
            "message": "Вы уже имеете доступ к этой колоде",
            "deck_id": str(invitation.deck_id),
            "already_joined": True
        }
    
    # Создаем доступ
    access = StudentDeckAccess(
        student_id=current_user.id,
        deck_id=invitation.deck_id,
        teacher_id=invitation.teacher_id,
        invitation_code=request.code
    )
    await access.insert()
    
    # Обновляем приглашение
    invitation.uses_count += 1
    if current_user.id not in invitation.joined_students:
        invitation.joined_students.append(current_user.id)
    await invitation.save()
    
    # Получаем информацию о колоде
    deck = await Deck.get(invitation.deck_id)
    teacher = await User.get(invitation.teacher_id)
    
    return {
        "message": "Успешно присоединились к колоде",
        "deck_id": str(invitation.deck_id),
        "deck_name": deck.name if deck else "Неизвестно",
        "teacher_name": teacher.username if teacher else "Неизвестно",
        "already_joined": False
    }


@router.get("/my-teachers-decks")
async def get_my_teachers_decks(
    current_user: User = Depends(get_current_user)
):
    """Получить колоды от учителей, к которым я присоединился"""
    from app.models import ContentItem

    accesses = await StudentDeckAccess.find(
        StudentDeckAccess.student_id == current_user.id,
        StudentDeckAccess.is_active == True
    ).sort(-StudentDeckAccess.joined_at).to_list()

    today = datetime.now()
    result = []

    for access in accesses:
        deck = await Deck.get(access.deck_id)
        teacher = await User.get(access.teacher_id)

        if not deck:
            continue

        # Считаем cards_due (новые + повторения) для студента
        new_due = await ContentItem.find(
            ContentItem.deck_id == access.deck_id,
            ContentItem.is_new == True,
            ContentItem.unlock_date <= today
        ).count()

        reviews_due = await ContentItem.find(
            ContentItem.deck_id == access.deck_id,
            ContentItem.is_new == False,
            ContentItem.next_review <= today
        ).count()

        cards_due = new_due + reviews_due

        # Считаем выученные карточки для студента
        learned = await ContentItem.find(
            ContentItem.deck_id == access.deck_id,
            ContentItem.is_learned == True
        ).count()

        total = await ContentItem.find(
            ContentItem.deck_id == access.deck_id
        ).count()

        # Определяем статус (такая же логика как в /api/decks/my)
        status = "active"
        if total == 0:
            status = "empty"
        elif learned == total and total > 0:
            status = "mastered"  # Полностью выучено
        elif cards_due == 0 and learned > 0:
            # Только если УЖЕ НАЧАЛИ учить И нет долгов -> done_for_today
            status = "done_for_today"
        elif cards_due > 0:
            status = "active"  # Есть что учить
        else:
            # Новая колода (learned == 0, cards_due == 0)
            status = "active"

        # Считаем прогресс
        progress = 0
        if total > 0:
            progress = round((learned / total) * 100, 1)

        result.append({
            "deck_id": str(access.deck_id),
            "deck_name": deck.name,
            "deck_description": deck.description,
            "total_cards": total,
            "teacher_name": teacher.username if teacher else "Неизвестно",
            "progress": progress,
            "cards_studied": learned,
            "cards_due": cards_due,
            "status": status,
            "content_type": deck.content_type or "flashcards",
            "learning_mode": deck.learning_mode or "all_at_once",
            "last_studied": access.last_studied,
            "joined_at": access.joined_at
        })

    return result