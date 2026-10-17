from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.security import get_current_user
from app.core.supabase import supabase_request

bearer_scheme = HTTPBearer(auto_error=False)


async def require_admin(
    user: dict[str, Any] = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    profiles = await supabase_request(
        settings,
        credentials.credentials,
        "GET",
        "profiles",
        params={
            "select": "id,role",
            "id": f"eq.{user['id']}",
            "limit": "1",
        },
    )

    if not profiles:
        raise HTTPException(
            status_code=403,
            detail="A valid user profile is required.",
        )

    if profiles[0]["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Administrator access required.",
        )

    return user

