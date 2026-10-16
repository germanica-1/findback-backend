
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.security import get_current_user
from app.core.supabase import supabase_request
from app.schemas.posts import CategoryResponse, PostCreate, PostResponse
from uuid import UUID

from app.schemas.posts import (
    CategoryResponse,
    PostCreate,
    PostResponse,
    PostUpdate,
)


router = APIRouter(prefix="/api/v1", tags=["Posts"])
bearer_scheme = HTTPBearer(auto_error=False)

POST_FIELDS = (
    "id,user_id,category_id,post_type,status,title,description,"
    "location,item_date,created_at,updated_at"
)


def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required.")
    return credentials.credentials


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    user: dict[str, Any] = Depends(get_current_user),
):
    del user  # get_current_user validates the token with Supabase Auth.

    result = await supabase_request(
        settings,
        token,
        "GET",
        "categories",
        params={"select": "id,name", "order": "id.asc"},
    )
    return result


@router.get("/posts", response_model=list[PostResponse])
async def list_posts(
    post_type: str | None = Query(default=None, pattern="^(missing|found)$"),
    status: str | None = Query(default=None, pattern="^(open|resolved)$"),
    category_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    user: dict[str, Any] = Depends(get_current_user),
):
    del user

    params = {
        "select": POST_FIELDS,
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }

    if post_type:
        params["post_type"] = f"eq.{post_type}"

    if status:
        params["status"] = f"eq.{status}"

    if category_id is not None:
        params["category_id"] = f"eq.{category_id}"

    result = await supabase_request(
        settings,
        token,
        "GET",
        "posts",
        params=params,
    )
    return result


@router.post("/posts", response_model=PostResponse, status_code=201)
async def create_post(
    post: PostCreate,
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    user: dict[str, Any] = Depends(get_current_user),
):
    payload = post.model_dump(mode="json")
    payload["user_id"] = user["id"]

    result = await supabase_request(
        settings,
        token,
        "POST",
        "posts",
        params={"select": POST_FIELDS},
        payload=payload,
        extra_headers={"Prefer": "return=representation"},
    )

    if not isinstance(result, list) or not result:
        raise HTTPException(
            status_code=502,
            detail="The post was not returned after creation.",
        )

    return result[0]



@router.patch("/posts/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: UUID,
    post: PostUpdate,
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    user: dict[str, Any] = Depends(get_current_user),
):
    del user  # Supabase RLS enforces post ownership.

    payload = post.model_dump(mode="json", exclude_unset=True)

    if not payload:
        raise HTTPException(
            status_code=422,
            detail="Provide at least one field to update.",
        )

    if any(value is None for value in payload.values()):
        raise HTTPException(
            status_code=422,
            detail="Updated fields cannot be null.",
        )

    result = await supabase_request(
        settings,
        token,
        "PATCH",
        "posts",
        params={
            "id": f"eq.{post_id}",
            "select": POST_FIELDS,
        },
        payload=payload,
        extra_headers={"Prefer": "return=representation"},
    )

    if not isinstance(result, list) or not result:
        raise HTTPException(
            status_code=404,
            detail="Post not found or you do not have permission to edit it.",
        )

    return result[0]

