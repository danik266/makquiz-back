from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.ai_service import generate_cards_from_text

router = APIRouter()

class GenerateRequest(BaseModel):
    text: str

@router.post("/preview")
async def preview_cards(request: GenerateRequest):
    """
    Принимает текст, возвращает сгенерированные карточки (без сохранения в БД).
    Это нужно, чтобы пользователь мог отредактировать их перед созданием колоды.
    """
    if not request.text:
        raise HTTPException(status_code=400, detail="Text is required")
    
    cards_data = await generate_cards_from_text(request.text)
    return {"cards": cards_data}