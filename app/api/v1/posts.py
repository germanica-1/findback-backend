from typing import Any
import httpx
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, Response
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
    PostStatusUpdate,
)
from app.schemas.feed import FeedPostResponse


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


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: UUID,
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    user: dict[str, Any] = Depends(get_current_user),
):
    del user  # Supabase RLS enforces owner/admin permissions.

    result = await supabase_request(
        settings,
        token,
        "DELETE",
        "posts",
        params={"id": f"eq.{post_id}"},
        extra_headers={"Prefer": "return=representation"},
    )

    if not isinstance(result, list) or not result:
        raise HTTPException(
            status_code=404,
            detail="Post not found or you do not have permission to delete it.",
        )

    return Response(status_code=204)



@router.patch("/posts/{post_id}/status", response_model=PostResponse)
async def update_post_status(
    post_id: UUID,
    body: PostStatusUpdate,
    token: str = Depends(require_token),
    settings: Settings = Depends(get_settings),
    user: dict[str, Any] = Depends(get_current_user),
):
    del user  # Supabase RLS enforces owner/admin permissions.

    result = await supabase_request(
        settings,
        token,
        "PATCH",
        "posts",
        params={
            "id": f"eq.{post_id}",
            "select": POST_FIELDS,
        },
        payload={"status": body.status},
        extra_headers={"Prefer": "return=representation"},
    )

    if not isinstance(result, list) or not result:
        raise HTTPException(
            status_code=404,
            detail="Post not found or you do not have permission to update it.",
        )

    return result[0]


@router.get("/posts/feed", response_model=list[FeedPostResponse])
async def list_posts_feed(
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
        "select": (
            f"{POST_FIELDS},"
            "author:profiles!posts_user_id_fkey(id,full_name,avatar_url),"
            "category:categories(id,name),"
            "images:post_images(id,storage_path,alt_text,created_at),"
            "comments(count)"
        ),
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

    posts = await supabase_request(
        settings,
        token,
        "GET",
        "posts",
        params=params,
    )

    if not posts:
        return []

    results = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for post in posts:
            feed_images = []

            for image_record in post.pop("images", []):
                storage_path = image_record["storage_path"]
                encoded_path = "/".join(
                    quote(segment, safe="")
                    for segment in storage_path.split("/")
                )

                signing_url = (
                    f"{settings.supabase_url.rstrip('/')}"
                    f"/storage/v1/object/sign/item-images/{encoded_path}"
                )

                try:
                    response = await client.post(
                        signing_url,
                        headers={
                            "apikey": settings.supabase_publishable_key,
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                        json={"expiresIn": 3600},
                    )
                except httpx.RequestError:
                    raise HTTPException(
                        status_code=503,
                        detail="The image storage service is temporarily unavailable.",
                    )

                if not response.is_success:
                    raise HTTPException(
                        status_code=502,
                        detail="Could not generate an image URL for the feed.",
                    )

                data = response.json()
                signed_url = data.get("signedURL") or data.get("signedUrl")

                if not signed_url:
                    raise HTTPException(
                        status_code=502,
                        detail="The image storage service returned an invalid response.",
                    )

                if signed_url.startswith("/storage/v1/"):
                    signed_url = (
                        f"{settings.supabase_url.rstrip('/')}{signed_url}"
                    )
                elif signed_url.startswith("/"):
                    signed_url = (
                        f"{settings.supabase_url.rstrip('/')}"
                        f"/storage/v1{signed_url}"
                    )
                elif not signed_url.startswith(("http://", "https://")):
                    signed_url = (
                        f"{settings.supabase_url.rstrip('/')}"
                        f"/storage/v1/{signed_url}"
                    )

                feed_images.append({
                    "id": image_record["id"],
                    "alt_text": image_record.get("alt_text"),
                    "created_at": image_record["created_at"],
                    "signed_url": signed_url,
                })

            comment_rows = post.pop("comments", [])
            comment_count = (
                comment_rows[0].get("count", 0)
                if comment_rows
                else 0
            )

            results.append({
                **post,
                "images": feed_images,
                "comment_count": comment_count,
            })

    return results

