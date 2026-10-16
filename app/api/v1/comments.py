from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.security import get_current_user
from app.core.supabase import supabase_request
from app.schemas.comments import CommentResponse


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

