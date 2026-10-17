from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.security import get_current_user
from app.core.supabase import supabase_request

from app.schemas.profiles import ProfileResponse, ProfileUpdate
from app.schemas.posts import PostResponse

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


@router.patch("/profiles/me", response_model=ProfileResponse)
async def update_my_profile(
    profile_data: ProfileUpdate,
    token: str = Depends(require_token),
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    payload = profile_data.model_dump(exclude_unset=True)

    if not payload:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one profile field to update.",
        )

    # Do not allow empty names, but allow clearing bio and avatar_url.
    if "full_name" in payload:
        if payload["full_name"] is None or not payload["full_name"].strip():
            raise HTTPException(
                status_code=422,
                detail="Full name cannot be empty.",
            )
        payload["full_name"] = payload["full_name"].strip()

    updated_profiles = await supabase_request(
        settings,
        token,
        "PATCH",
        "profiles",
        params={
            "id": f"eq.{user['id']}",
            "select": PROFILE_FIELDS,
        },
        payload=payload,
        extra_headers={"Prefer": "return=representation"},
    )

    if not updated_profiles:
        raise HTTPException(
            status_code=404,
            detail="Profile not found or could not be updated.",
        )

    return updated_profiles[0]


@router.get("/profiles/{user_id}", response_model=ProfileResponse)
async def get_public_profile(
    user_id: UUID,
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
            "id": f"eq.{user_id}",
            "limit": "1",
        },
    )

    if not profiles:
        raise HTTPException(
            status_code=404,
            detail="Profile not found.",
        )

    return profiles[0]


@router.get(
    "/profiles/{user_id}/posts",
    response_model=list[PostResponse],
)
async def get_user_posts(
    user_id: UUID,
    status: Literal["open", "resolved"] | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    token: str = Depends(require_token),
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    # Confirm that the profile exists.
    profiles = await supabase_request(
        settings,
        token,
        "GET",
        "profiles",
        params={
            "select": "id",
            "id": f"eq.{user_id}",
            "limit": "1",
        },
    )

    if not profiles:
        raise HTTPException(
            status_code=404,
            detail="Profile not found.",
        )

    params = {
        "select": (
            "id,user_id,category_id,post_type,status,title,"
            "description,location,item_date,created_at,updated_at"
        ),
        "user_id": f"eq.{user_id}",
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }

    if status is not None:
        params["status"] = f"eq.{status}"

    posts = await supabase_request(
        settings,
        token,
        "GET",
        "posts",
        params=params,
    )

    return posts

