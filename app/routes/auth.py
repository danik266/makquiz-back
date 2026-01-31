from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from passlib.context import CryptContext
from app.models import User
from datetime import datetime, timedelta
from jose import jwt, JWTError  # Import JWTError from jose
from typing import Optional
from app.config import settings  # Assuming settings has SECRET_KEY, ALGORITHM; adjust if needed

# If no settings, fallback to hardcoded (not recommended for prod)
SECRET_KEY = settings.SECRET_KEY if hasattr(settings, 'SECRET_KEY') else "supersecretkey"
ALGORITHM = settings.ALGORITHM if hasattr(settings, 'ALGORITHM') else "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 

router = APIRouter()
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Strict OAuth2 scheme (raises 401 if no token)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Optional OAuth2 scheme (does NOT raise 401 if no token)
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- ГЛАВНАЯ ФУНКЦИЯ ЗАЩИТЫ ---
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = await User.find_one(User.email == email)
    if user is None:
        raise credentials_exception
    return user

# --- OPTIONAL USER ---
async def get_current_user_optional(token: Optional[str] = Depends(optional_oauth2_scheme)) -> Optional[User]:
    """
    Пытается получить текущего пользователя, но не вызывает ошибку, 
    если токен отсутствует. Возвращает None в таком случае.
    Если токен предоставлен но невалиден, вызывает 401.
    """
    if not token:
        return None
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = await User.find_one(User.email == email)
    if user is None:
        raise credentials_exception
    return user

# --- ЭНДПОИНТЫ ---

@router.post("/register")
async def register(user_data: UserAuth):
    if await User.find_one(User.email == user_data.email):
        raise HTTPException(status_code=400, detail="Email уже занят")
    
    hashed_pw = get_password_hash(user_data.password)
    user = User(
        email=user_data.email, 
        username=user_data.username or "Student", 
        hashed_password=hashed_pw,
        role=user_data.role
    )
    await user.insert()
    
    access_token = create_access_token({"sub": user.email})
    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "username": user.username,
        "role": user.role
    }

@router.post("/login")
async def login(user_data: UserAuth):
    user = await User.find_one(User.email == user_data.email)
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    
    token = create_access_token({"sub": user.email})
    return {
        "access_token": token, 
        "token_type": "bearer", 
        "username": user.username,
        "role": user.role
    }

# --- SCHEMAS (moved to top for clarity) ---
class UserAuth(BaseModel):
    email: str
    password: str
    username: str = None
    role: str = "student"