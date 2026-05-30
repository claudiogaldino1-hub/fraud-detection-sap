"""
FastAPI application entry point.
"""

from datetime import timedelta

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm

from api.auth import (
    Token,
    authenticate_user,
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from api.routers import alerts, contestation, export, feedback, models

app = FastAPI(
    title="SAP P2P Fraud Detection API",
    description=(
        "Sistema enterprise de detecção de fraude financeira para o fluxo Procure to Pay (P2P) "
        "com Isolation Forest, AutoEncoder e análise de grafo de relacionamento. "
        "Narrativas geradas pela Claude API. Exportação para Power BI."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/auth/token", response_model=Token, tags=["Auth"])
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=token, role=user.role, expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(alerts.router)
app.include_router(feedback.router)
app.include_router(models.router)
app.include_router(export.router)
app.include_router(contestation.router)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/", tags=["Health"])
async def root():
    return {
        "name": "SAP P2P Fraud Detection API",
        "docs": "/docs",
        "health": "/health",
    }
