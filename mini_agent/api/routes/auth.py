from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from mini_agent.core.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    CurrentUser,
    authenticate_user,
    create_access_token,
    get_current_user,
)
from mini_agent.core.rate_limit import (
    check_login_rate_limit,
    rate_limit_headers,
)


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class MeResponse(BaseModel):
    user_id: str
    username: str
    role: str


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Dict[str, Any]:
    login_rate = await check_login_rate_limit(
        request=request,
        username=form_data.username,
    )

    for key, value in rate_limit_headers(login_rate).items():
        response.headers[key] = value

    user = await run_in_threadpool(
        authenticate_user,
        form_data.username,
        form_data.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误。",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/me", response_model=MeResponse)
def me(current_user: CurrentUser = Depends(get_current_user)) -> Dict[str, Any]:
    return {
        "user_id": current_user.user_id,
        "username": current_user.username,
        "role": current_user.role,
    }