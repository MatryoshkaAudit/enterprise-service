import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from matryoshka_db.db_models import User

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "SOVEREIGN_MATRYOSHKA_SECRET_KEY_GOST_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 60 * 60 * 24 * 7  # 7 days


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _base64url_decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode("utf-8"))


def create_jwt_token(payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))

    # Add expiration
    token_payload = payload.copy()
    if "exp" not in token_payload:
        token_payload["exp"] = int(time.time()) + ACCESS_TOKEN_EXPIRE_SECONDS

    encoded_payload = _base64url_encode(json.dumps(token_payload, separators=(",", ":")).encode("utf-8"))

    signing_input = f"{encoded_header}.{encoded_payload}".encode()
    signature = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    encoded_signature = _base64url_encode(signature)

    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def decode_jwt_token(token: str) -> dict[str, Any] | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, signature_b64 = parts

        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_sig = _base64url_decode(signature_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_data = json.loads(_base64url_decode(payload_b64).decode("utf-8"))
        if payload_data.get("exp", 0) < int(time.time()):
            logger.warning("Срок действия токена истек")
            return None

        return payload_data
    except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning(f"Ошибка валидации структуры JWT: {e}")
        return None


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def authenticate(self, email: str, password: str) -> User | None:
        query = select(User).where(User.email == email.strip().lower())
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            return None
        if not user.verify_password(password):
            return None
        return user

    async def get_user_by_id(self, user_id: int) -> User | None:
        query = select(User).where(User.id == user_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_user_by_role(self, role: str) -> User | None:
        query = select(User).where(User.role == role).limit(1)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    def issue_token(self, user: User) -> str:
        payload = {
            "sub": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "organization": user.organization,
            "department": user.department,
            "inn": user.inn,
        }
        return create_jwt_token(payload)
