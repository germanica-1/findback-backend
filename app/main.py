from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from typing import Any
from fastapi import Depends

from app.core.security import get_current_user
from app.api.v1.posts import router as posts_router
from app.api.v1.comments import router as comments_router

settings = get_settings()

app = FastAPI(
    title="FINDBACK API",
    description="Lost and Found Platform API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "apikey"],
)


app.include_router(posts_router)
app.include_router(comments_router)

@app.get("/")
async def root():
    return {
        "message": "Welcome to FINDBACK API",
        "environment": settings.app_env,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api/v1/me")
async def get_me(
    user: dict[str, Any] = Depends(get_current_user),
):
    return {
        "id": user["id"],
        "email": user.get("email"),
    }
