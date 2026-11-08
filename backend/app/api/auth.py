"""Auth router: login and current-user."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserRead

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    token = create_access_token(user.id, user.role.value)
    return TokenResponse(
        access_token=token,
        role=user.role.value,
        user=UserRead.model_validate(user),
    )


@router.get("/auth/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)
