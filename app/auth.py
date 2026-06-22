import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import Config
from app.rate_limiter import limit_route

config = Config()
router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger("vela.auth")
if config.secret_key == "change-me":
    logger.warning(
        "JWT secret_key is using the default insecure value. Set a strong secret in config.yaml or VELA_SECRET_KEY."
    )

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

ALGORITHM = "HS256"


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class TokenData(BaseModel):
    sub: str


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=config.token_expire_minutes))
    to_encode.update({"iat": now, "exp": expire})
    return jwt.encode(to_encode, config.secret_key, algorithm=ALGORITHM)


def authenticate_user(username: str, password: str) -> bool:
    if username != config.username:
        return False
    provided = password.encode("utf-8")
    expected = config.password_hash.encode("utf-8")
    try:
        return bcrypt.checkpw(provided, expected)
    except ValueError:
        return False


def verify_token_string(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, config.secret_key, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if subject is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload missing subject",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return TokenData(sub=subject)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_token(token: str = Depends(oauth2_scheme)) -> TokenData:
    return verify_token_string(token)


async def verify_websocket_token(websocket: WebSocket) -> TokenData:
    auth_header = websocket.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise WebSocketException(code=1008, reason="Could not validate credentials")

    token = auth_header.split(" ", 1)[1]
    try:
        return verify_token_string(token)
    except HTTPException:
        raise WebSocketException(code=1008, reason="Could not validate credentials")


@router.post("/token", response_model=TokenResponse)
@limit_route("/auth/token")
async def token(request: Request, body: LoginRequest):
    if not authenticate_user(body.username, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": body.username})
    return TokenResponse(
        access_token=access_token,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=config.token_expire_minutes),
    )
