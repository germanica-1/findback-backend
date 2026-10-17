from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.security import get_current_user
from app.core.supabase import supabase_request
from app.schemas.profiles import ProfileResponse


router = APIRouter(prefix="/api/v1", tags=["Profiles"])
bearer_scheme = HTTPBearer(auto_error=False)

PROFILE_FIELDS = (
    "id,full_name,bio,avatar_url,role,created_at,updated_at"
)


async def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )
    return credentials.credentials


@router.get("/profiles/me", response_model=ProfileResponse)
async def get_my_profile(
    token: str = Depends(require_token),
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    profiles = await supabase_request(
        settings,
        token,
        "GET",
        "profiles",
        params={
            "select": PROFILE_FIELDS,
            "id": f"eq.{user['id']}",
            "limit": "1",
        },
    )

    if not profiles:
        raise HTTPException(
            status_code=404,
            detail="Profile not found.",
        )

    return profiles[0]

