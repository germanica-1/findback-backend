from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.security import get_current_user
from app.core.supabase import supabase_request

from app.schemas.comments import (
    CommentCreate,
    CommentResponse,
    CommentUpdate,
)


router = APIRouter(prefix="/api/v1", tags=["Comments"])
bearer_scheme = HTTPBearer(auto_error=False)

COMMENT_FIELDS = (
    "id,post_id,user_id,content,created_at,updated_at"
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


@router.get(
    "/posts/{post_id}/comments",
    response_model=list[CommentResponse],
)
async def get_post_comments(
    post_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    token: str = Depends(require_token),
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    # Confirm that the parent post exists.
    posts = await supabase_request(
        settings,
        token,
        "GET",
        "posts",
        params={
            "select": "id",
            "id": f"eq.{post_id}",
            "limit": "1",
        },
    )

    if not posts:
        raise HTTPException(
            status_code=404,
            detail="Post not found.",
        )

    comments = await supabase_request(
        settings,
        token,
        "GET",
        "comments",
        params={
            "select": COMMENT_FIELDS,
            "post_id": f"eq.{post_id}",
            "order": "created_at.asc",
            "limit": str(limit),
            "offset": str(offset),
        },
    )

    return comments



@router.post(
    "/posts/{post_id}/comments",
    response_model=CommentResponse,
    status_code=201,
)
async def create_post_comment(
    post_id: UUID,
    comment_data: CommentCreate,
    token: str = Depends(require_token),
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    # Confirm that the parent post exists.
    posts = await supabase_request(
        settings,
        token,
        "GET",
        "posts",
        params={
            "select": "id",
            "id": f"eq.{post_id}",
            "limit": "1",
        },
    )

    if not posts:
        raise HTTPException(
            status_code=404,
            detail="Post not found.",
        )

    # Derive the author from the authenticated Supabase user.
    payload = {
        "post_id": str(post_id),
        "user_id": user["id"],
        "content": comment_data.content,
    }

    comments = await supabase_request(
        settings,
        token,
        "POST",
        "comments",
        params={"select": COMMENT_FIELDS},
        payload=payload,
        extra_headers={"Prefer": "return=representation"},
    )

    if not comments:
        raise HTTPException(
            status_code=502,
            detail="The comment could not be created.",
        )

    return comments[0]


@router.patch(
    "/comments/{comment_id}",
    response_model=CommentResponse,
)
async def update_comment(
    comment_id: UUID,
    comment_data: CommentUpdate,
    token: str = Depends(require_token),
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    updated_comments = await supabase_request(
        settings,
        token,
        "PATCH",
        "comments",
        params={
            "id": f"eq.{comment_id}",
            "select": COMMENT_FIELDS,
        },
        payload={
            "content": comment_data.content,
        },
        extra_headers={"Prefer": "return=representation"},
    )

    if not updated_comments:
        raise HTTPException(
            status_code=404,
            detail="Comment not found or you are not allowed to edit it.",
        )

    return updated_comments[0]



@router.delete(
    "/comments/{comment_id}",
    status_code=204,
)
async def delete_comment(
    comment_id: UUID,
    token: str = Depends(require_token),
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    deleted_comments = await supabase_request(
        settings,
        token,
        "DELETE",
        "comments",
        params={
            "id": f"eq.{comment_id}",
            "select": "id",
        },
        extra_headers={"Prefer": "return=representation"},
    )

    if not deleted_comments:
        raise HTTPException(
            status_code=404,
            detail="Comment not found or you are not allowed to delete it.",
        )

    return Response(status_code=204)

