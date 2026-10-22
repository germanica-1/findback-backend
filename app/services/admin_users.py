
import asyncio

import httpx
from fastapi import HTTPException

from app.core.config import Settings


async def get_auth_emails_by_user_id(
    settings: Settings,
    user_ids: list[str],
) -> dict[str, str]:
    """Fetch emails for specific Supabase Auth user IDs."""

    if not user_ids:
        return {}

    base_url = (
        f"{settings.supabase_url.rstrip('/')}"
        "/auth/v1/admin/users"
    )

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    async def fetch_email(
        client: httpx.AsyncClient,
        user_id: str,
    ) -> tuple[str, str | None]:
        try:
            response = await client.get(
                f"{base_url}/{user_id}",
                headers=headers,
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=503,
                detail="Could not reach the authentication service.",
            )

        if response.status_code == 404:
            return user_id, None

        if not response.is_success:
            raise HTTPException(
                status_code=502,
                detail="Could not retrieve user email addresses.",
            )

        try:
            auth_user = response.json()
            email = auth_user.get("email")
            return user_id, email if isinstance(email, str) and email else None
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=502,
                detail="The authentication service returned invalid user data.",
            )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            results = await asyncio.gather(
                *(fetch_email(client, user_id) for user_id in user_ids)
            )
    except HTTPException:
        raise

    return {
        user_id: email
        for user_id, email in results
        if email is not None
    }

