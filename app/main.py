from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

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


@app.get("/")
async def root():
    return {
        "message": "Welcome to FINDBACK API",
        "environment": settings.app_env,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
