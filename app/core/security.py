
from typing import Any

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_publishable_key,
                    "Authorization": f"Bearer {credentials.credentials}",
                },
            )
    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Supabase Auth is temporarily unavailable.",
        )

    if response.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail="Supabase rejected the access token.",
        )

    if response.status_code == 403:
        raise HTTPException(
            status_code=403,
            detail="Supabase denied the authentication request.",
        )

    if not response.is_success:
        raise HTTPException(
            status_code=502,
            detail="Could not validate the user with Supabase Auth.",
        )

    return response.json()

