"""
Role-Based Access Control (RBAC) for the Fraud Detection API.

Roles
-----
analista  — read alerts, submit feedback
gestor    — analista + approve/reject model versions
auditor   — gestor + access audit log, export full data

JWT tokens carry the role as a claim.
"""

import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    expires_in: int


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


class User(BaseModel):
    username: str
    role: str
    disabled: bool = False


# ---------------------------------------------------------------------------
# Fake user DB — replace with real DB in production
# ---------------------------------------------------------------------------

FAKE_USERS_DB: dict = {
    "ana.analista": {
        "username": "ana.analista",
        "hashed_password": pwd_context.hash("analista123"),
        "role": "analista",
        "disabled": False,
    },
    "mario.gestor": {
        "username": "mario.gestor",
        "hashed_password": pwd_context.hash("gestor456"),
        "role": "gestor",
        "disabled": False,
    },
    "carlos.auditor": {
        "username": "carlos.auditor",
        "hashed_password": pwd_context.hash("auditor789"),
        "role": "auditor",
        "disabled": False,
    },
}

# ---------------------------------------------------------------------------
# Permissions matrix
# ---------------------------------------------------------------------------

ROLE_PERMISSIONS: dict[str, List[str]] = {
    "analista": [
        "alerts:read",
        "feedback:write",
    ],
    "gestor": [
        "alerts:read",
        "feedback:write",
        "models:approve",
        "models:read",
        "export:read",
    ],
    "auditor": [
        "alerts:read",
        "feedback:write",
        "models:approve",
        "models:read",
        "export:read",
        "audit_log:read",
        "catalog:read",
        "contestation:read",
        "contestation:write",
    ],
}

# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate_user(username: str, password: str) -> Optional[User]:
    user_data = FAKE_USERS_DB.get(username)
    if not user_data:
        return None
    if not verify_password(password, user_data["hashed_password"]):
        return None
    return User(**{k: v for k, v in user_data.items() if k != "hashed_password"})


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            raise _credentials_exception()
        return TokenData(username=username, role=role)
    except JWTError:
        raise _credentials_exception()


def _credentials_exception():
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas ou token expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> TokenData:
    return decode_token(credentials.credentials)


def require_permission(permission: str):
    async def dependency(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        role = current_user.role or ""
        allowed = ROLE_PERMISSIONS.get(role, [])
        if permission not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Perfil '{role}' não possui permissão '{permission}'.",
            )
        return current_user
    return dependency


def require_roles(*roles: str):
    async def dependency(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado. Perfis permitidos: {', '.join(roles)}.",
            )
        return current_user
    return dependency
