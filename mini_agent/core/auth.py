import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select

from mini_agent.core.config import get_settings
from mini_agent.db.session import db_session
from mini_agent.db.models import AppUser

load_dotenv()
settings = get_settings()
JWT_SECRET_KEY = settings.jwt_secret_key
JWT_ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    settings.access_token_expire_minutes
)

# 这个 tokenUrl 会显示在 /docs 的 Authorize 按钮里。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

password_hash = PasswordHash.recommended()


@dataclass
class CurrentUser:
    user_id: str
    username: str
    role: str
    disabled: bool = False


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def get_user_by_username(username: str) -> Optional[AppUser]:
    with db_session() as db:
        stmt = select(AppUser).where(AppUser.username == username)
        return db.execute(stmt).scalar_one_or_none()


def get_user_by_id(user_id: str) -> Optional[AppUser]:
    with db_session() as db:
        stmt = select(AppUser).where(AppUser.user_id == user_id)
        return db.execute(stmt).scalar_one_or_none()


def authenticate_user(username: str, password: str) -> Optional[CurrentUser]:
    user = get_user_by_username(username)

    if user is None:
        return None

    if user.disabled:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return CurrentUser(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        disabled=user.disabled,
    )


def create_access_token(
    *,
    user_id: str,
    username: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload: Dict[str, Any] = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={
                "require": ["sub", "exp", "iat", "jti"],
            },
        )
        return payload

    except ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录。",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效 token。",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    payload = decode_access_token(token)

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token 缺少用户身份。",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在。",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用。",
        )

    return CurrentUser(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        disabled=user.disabled,
    )