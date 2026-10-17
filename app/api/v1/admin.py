from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.permissions import require_admin
from app.core.supabase import supabase_request
from app.schemas.posts import PostResponse, PostStatusUpdate

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

bearer_scheme = HTTPBearer()


@router.get("/posts", response_model=list[PostResponse])
async def list_posts_for_moderation(
    status: Literal["open", "resolved"] | None = None,
    post_type: Literal["missing", "found"] | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user: dict = Depends(require_admin),
):
    del user  # require_admin verifies the user's database role.

    params = {
        "select": (
            "id,user_id,category_id,post_type,status,title,"
            "description,location,item_date,created_at,updated_at"
        ),
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }

    if status is not None:
        params["status"] = f"eq.{status}"

    if post_type is not None:
        params["post_type"] = f"eq.{post_type}"

    return await supabase_request(
        get_settings(),
        credentials.credentials,
        "GET",
        "posts",
        params=params,
    )


@router.patch("/posts/{post_id}/status", response_model=PostResponse)
async def update_post_status_as_admin(
    post_id: UUID,
    payload: PostStatusUpdate,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user: dict = Depends(require_admin),
):
    del user  # require_admin verifies the user's database role.

    updated_posts = await supabase_request(
        get_settings(),
        credentials.credentials,
        "PATCH",
        "posts",
        params={
            "id": f"eq.{post_id}",
            "select": (
                "id,user_id,category_id,post_type,status,title,"
                "description,location,item_date,created_at,updated_at"
            ),
        },
        payload={"status": payload.status},
        extra_headers={"Prefer": "return=representation"},
    )

    if not updated_posts:
        raise HTTPException(
            status_code=404,
            detail="Post not found.",
        )

    return updated_posts[0]

