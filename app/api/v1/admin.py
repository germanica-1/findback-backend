from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.permissions import require_admin
from app.core.supabase import supabase_request
from app.schemas.posts import PostResponse, PostStatusUpdate
from app.services.audit import record_admin_action
from app.schemas.admin import AdminLogResponse


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
    settings = get_settings()
    access_token = credentials.credentials

    # Read the current status before making the change.
    existing_posts = await supabase_request(
        settings,
        access_token,
        "GET",
        "posts",
        params={
            "select": "id,status",
            "id": f"eq.{post_id}",
            "limit": "1",
        },
    )

    if not existing_posts:
        raise HTTPException(
            status_code=404,
            detail="Post not found.",
        )

    previous_status = existing_posts[0]["status"]

    # Update the post using the administrator's own access token.
    updated_posts = await supabase_request(
        settings,
        access_token,
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
            detail="Post not found or no post was updated.",
        )

    updated_post = updated_posts[0]

    # Record only actual status changes.
    if previous_status != payload.status:
        await record_admin_action(
            settings,
            actor_id=UUID(user["id"]),
            action="post_status_updated",
            post_id=post_id,
            details={
                "previous_status": previous_status,
                "new_status": payload.status,
            },
        )

    return updated_post
        

@router.get("/logs", response_model=list[AdminLogResponse])
async def list_admin_logs(
    action: str | None = Query(default=None, min_length=1, max_length=100),
    post_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user: dict = Depends(require_admin),
):
    del user

    params = {
        "select": "id,actor_id,action,post_id,details,created_at",
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }

    if action is not None:
        params["action"] = f"eq.{action}"

    if post_id is not None:
        params["post_id"] = f"eq.{post_id}"

    return await supabase_request(
        get_settings(),
        credentials.credentials,
        "GET",
        "admin_logs",
        params=params,
    )

