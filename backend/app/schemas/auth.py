"""Auth schemas."""

from pydantic import BaseModel, EmailStr

from app.schemas.user import UserRead


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user: UserRead
