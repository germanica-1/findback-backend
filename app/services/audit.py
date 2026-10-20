
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException

from app.core.config import Settings


async def record_admin_action(
    settings: Settings,
    *,
    actor_id: UUID,
    action: str,
    post_id: UUID | None,
    details: dict[str, Any],
) -> None:
    """Insert an admin audit record using the backend-only service role."""

    url = (
        f"{settings.supabase_url.rstrip('/')}"
        "/rest/v1/admin_logs"
    )

    payload = {
        "actor_id": str(actor_id),
        "action": action,
        "post_id": str(post_id) if post_id is not None else None,
        "details": details,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                headers={
                    "apikey": settings.supabase_service_role_key,
                    "Authorization": (
                        f"Bearer {settings.supabase_service_role_key}"
                    ),
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json=payload,
            )
    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Could not reach the audit logging service.",
        )

    if not response.is_success:
        # Do not return Supabase's raw response or expose credentials.
        raise HTTPException(
            status_code=502,
            detail="Could not record the administrative action.",
        )

