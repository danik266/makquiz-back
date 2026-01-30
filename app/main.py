from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.database import init_db
from app.routes import decks, auth,teacher, live
from app.config import settings
from pathlib import Path
from fastapi.staticfiles import StaticFiles
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print("🚀 Server started!")
    yield
    print("👋 Server shutting down...")

app = FastAPI(lifespan=lifespan)

# --- ВАЖНО: Настройка CORS ---
# Мы разрешаем запросы с локалхоста фронтенда
origins = [
    "http://localhost:3000",  # Для локальной разработки
    "https://makquiz-front.vercel.app", # Твой фронтенд на Vercel
    "https://makquiz-front.vercel.app/" # На всякий случай со слэшем
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,    # Разрешаем запросы с этих адресов
    allow_credentials=True,   # Разрешаем куки и авторизацию
    allow_methods=["*"],      # Разрешаем все методы (GET, POST, PUT, DELETE...)
    allow_headers=["*"],      # Разрешаем все заголовки
)
BASE_DIR = Path(__file__).resolve().parent.parent 
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

print(f"📂 Static files served from: {STATIC_DIR}")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(decks.router, prefix="/api/decks", tags=["Decks"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(teacher.router, prefix="/api/teacher", tags=["teacher"])
app.include_router(live.router, prefix="/api/live", tags=["Live"])
@app.get("/")
async def root():
    return {"status": "ok"}