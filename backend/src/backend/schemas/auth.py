import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from backend.auth.password import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH


def _validate_password_bytes(value: str) -> str:
    # bcrypt's limit is 72 *bytes*, not characters, so a short password made
    # of multi-byte characters can still be too long.
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes.")

    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    full_name: str | None = Field(default=None, max_length=255)
    invite_code: str | None = Field(default=None, max_length=64)

    _check_password = field_validator("password")(_validate_password_bytes)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    current_password: str | None = None

    _check_password = field_validator("new_password")(_validate_password_bytes)


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    role: str
    is_active: bool
    has_password: bool
    has_google: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
