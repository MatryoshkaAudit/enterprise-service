import logging
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.services.auth_service import AuthService, decode_jwt_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["Аутентификация и роли"])


class LoginRequest(BaseModel):
    email: str
    password: str


class DemoLoginRequest(BaseModel):
    role: str  # 'enterprise' | 'regulator'


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    organization: str
    department: str | None = None
    inn: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


async def get_current_user(
    authorization: str | None = Header(None),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Отсутствует или недействителен токен авторизации Bearer",
        )
    token = authorization.split(" ")[1]
    payload = decode_jwt_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или просроченный токен сессии",
        )
    return UserResponse(
        id=payload["sub"],
        email=payload["email"],
        full_name=payload["full_name"],
        role=payload["role"],
        organization=payload["organization"],
        department=payload.get("department"),
        inn=payload.get("inn"),
    )


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_db_session)):
    auth_service = AuthService(session)
    user = await auth_service.authenticate(req.email, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )
    token = auth_service.issue_token(user)
    return LoginResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            organization=user.organization,
            department=user.department,
            inn=user.inn,
        ),
    )


@router.post("/demo-login", response_model=LoginResponse)
async def demo_login(req: DemoLoginRequest, session: AsyncSession = Depends(get_db_session)):
    """Быстрый вход для презентации комиссии (Завод или Регулятор)"""
    auth_service = AuthService(session)
    target_role = "regulator_admin" if req.role in ["regulator", "admin"] else "enterprise_engineer"
    
    user = await auth_service.get_user_by_role(target_role)
    if not user:
        # Fallback synthetic demo user if db is not seeded
        if target_role == "regulator_admin":
            user_data = UserResponse(
                id=2,
                email="inspector@minpromtorg.gov.ru",
                full_name="Лесных Иван Сергеевич",
                role="regulator_admin",
                organization="Минпромторг РФ",
                department="Ситуационный Центр ДСПСДМ",
                inn="7705596339",
            )
        else:
            user_data = UserResponse(
                id=1,
                email="engineer@lestechmash.ru",
                full_name="Смирнов Алексей Петрович",
                role="enterprise_engineer",
                organization="АО «Лестехмаш»",
                department="Отдел Главного Конструктора",
                inn="3525184920",
            )
        from app.services.auth_service import create_jwt_token
        token = create_jwt_token({
            "sub": user_data.id,
            "email": user_data.email,
            "full_name": user_data.full_name,
            "role": user_data.role,
            "organization": user_data.organization,
            "department": user_data.department,
            "inn": user_data.inn,
        })
        return LoginResponse(access_token=token, user=user_data)
        
    token = auth_service.issue_token(user)
    return LoginResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            organization=user.organization,
            department=user.department,
            inn=user.inn,
        ),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserResponse = Depends(get_current_user)):
    return current_user
