from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser, DBSession
from app.schemas.auth import LoginRequest, RegisterRequest, SessionRead, TokenResponse, UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: DBSession) -> UserRead:
    user = await AuthService.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        db=db,
    )
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DBSession,
) -> TokenResponse:
    token_data = await AuthService.login(
        email=payload.email,
        password=payload.password,
        db=db,
        request=request,
        response=response,
    )
    return TokenResponse.model_validate(token_data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: DBSession,
) -> TokenResponse:
    raw_token = request.cookies.get("refresh_token")
    if raw_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен обновления отсутствует")

    token_data = await AuthService.refresh(
        raw_rt=raw_token,
        db=db,
        request=request,
        response=response,
    )
    return TokenResponse.model_validate(token_data)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout(
    request: Request,
    response: Response,
    db: DBSession,
) -> Response:
    await AuthService.logout(request.cookies.get("refresh_token"), db=db, response=response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get("/sessions", response_model=list[SessionRead])
async def sessions(current_user: CurrentUser, db: DBSession) -> list[SessionRead]:
    active_sessions = await AuthService.list_sessions(current_user.id, db)
    return [SessionRead.model_validate(item) for item in active_sessions]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def revoke_session(
    session_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> Response:
    await AuthService.revoke_session(session_id=session_id, user_id=current_user.id, db=db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
