from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import Settings


async def supabase_request(
    settings: Settings,
    access_token: str,
    method: str,
    table: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    """Make a user-scoped request to Supabase PostgREST."""

    headers = {
        "apikey": settings.supabase_publishable_key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    if extra_headers:
        headers.update(extra_headers)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(
                method=method,
                url=f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}",
                headers=headers,
                params=params,
                json=payload,
            )
    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="The database service is temporarily unavailable.",
        )

    if not response.is_success:
        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=response.status_code,
                detail="The request is not authorized.",
            )

        if response.status_code == 409:
            raise HTTPException(
                status_code=409,
                detail="The request conflicts with existing data.",
            )

        if response.status_code in (400, 404, 422):
            raise HTTPException(
                status_code=400,
                detail="The database rejected the request. Check the supplied data.",
            )

        raise HTTPException(
            status_code=502,
            detail="The database request failed.",
        )

    if response.status_code == 204 or not response.content:
        return None

    return response.json()

