from uuid import UUID
from typing import Literal
import httpx
from urllib.parse import quote
from fastapi import APIRouter, Depends, Query, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.permissions import require_admin
from app.core.supabase import supabase_request
from app.schemas.posts import PostResponse, PostStatusUpdate
from app.services.audit import record_admin_action
from app.schemas.admin import AdminLogResponse, AdminRoleUpdate, AdminUserResponse


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



@router.get("/users", response_model=list[AdminUserResponse])
async def list_users_for_admin(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user: dict = Depends(require_admin),
):
    del user

    return await supabase_request(
        get_settings(),
        credentials.credentials,
        "GET",
        "profiles",
        params={
            "select": (
                "id,full_name,bio,avatar_url,role,created_at,updated_at"
            ),
            "order": "created_at.desc",
            "limit": str(limit),
            "offset": str(offset),
        },
    )



@router.patch("/users/{user_id}/role", response_model=AdminUserResponse)
async def update_user_role(
    user_id: UUID,
    payload: AdminRoleUpdate,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user: dict = Depends(require_admin),
):
    settings = get_settings()
    access_token = credentials.credentials

    # Read the existing role so we can audit actual changes.
    existing_users = await supabase_request(
        settings,
        access_token,
        "GET",
        "profiles",
        params={
            "select": "id,role",
            "id": f"eq.{user_id}",
            "limit": "1",
        },
    )

    if not existing_users:
        raise HTTPException(
            status_code=404,
            detail="User profile not found.",
        )

    previous_role = existing_users[0]["role"]

    # Let PostgreSQL enforce admin permissions and safeguards.
    updated_users = await supabase_request(
        settings,
        access_token,
        "POST",
        "rpc/admin_set_user_role",
        payload={
            "target_user_id": str(user_id),
            "new_role": payload.role,
        },
    )

    if not updated_users:
        raise HTTPException(
            status_code=404,
            detail="User profile not found or role was not updated.",
        )

    updated_user = updated_users[0]

    # Record actual role changes.
    if previous_role != payload.role:
        await record_admin_action(
            settings,
            actor_id=UUID(user["id"]),
            action="user_role_updated",
            post_id=None,
            details={
                "target_user_id": str(user_id),
                "previous_role": previous_role,
                "new_role": payload.role,
            },
        )

    return updated_user



@router.delete("/posts/{post_id}", status_code=204)
async def delete_post_as_admin(
    post_id: UUID,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user: dict = Depends(require_admin),
):
    settings = get_settings()
    access_token = credentials.credentials

    # 1. Find the post before attempting deletion.
    posts = await supabase_request(
        settings,
        access_token,
        "GET",
        "posts",
        params={
            "select": "id,user_id,title",
            "id": f"eq.{post_id}",
            "limit": "1",
        },
    )

    if not posts:
        raise HTTPException(
            status_code=404,
            detail="Post not found.",
        )

    post = posts[0]

    # 2. Retrieve image metadata while the post still exists.
    images = await supabase_request(
        settings,
        access_token,
        "GET",
        "post_images",
        params={
            "select": "id,storage_path",
            "post_id": f"eq.{post_id}",
        },
    )

    # 3. Delete the actual Storage objects using the backend-only key.
    # Keep image metadata and the post in place until Storage cleanup
    # has succeeded for every image.
    storage_url = (
        f"{settings.supabase_url.rstrip('/')}"
        "/storage/v1/object/item-images"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        for image in images:
            encoded_path = "/".join(
                quote(segment, safe="")
                for segment in image["storage_path"].split("/")
            )

            try:
                response = await client.delete(
                    f"{storage_url}/{encoded_path}",
                    headers={
                        "apikey": settings.supabase_service_role_key,
                        "Authorization": (
                            f"Bearer {settings.supabase_service_role_key}"
                        ),
                    },
                )
            except httpx.RequestError:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "The image storage service is unavailable. "
                        "The post has not been deleted."
                    ),
                )

            if not response.is_success:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Could not clean up the post's images. "
                        "The post has not been deleted. Check Storage "
                        "for any images already removed."
                    ),
                )

    # 4. Delete the database post. Its comments and image metadata
    # should be removed by the existing foreign-key cascade.
    deleted_posts = await supabase_request(
        settings,
        access_token,
        "DELETE",
        "posts",
        params={
            "id": f"eq.{post_id}",
            "select": "id",
        },
        extra_headers={"Prefer": "return=representation"},
    )

    if not isinstance(deleted_posts, list) or not deleted_posts:
        raise HTTPException(
            status_code=404,
            detail=(
                "The post was not deleted. Check the post and its "
                "image references before retrying."
            ),
        )

    # 5. Audit the deletion. post_id is null because the post no
    # longer exists; preserve its ID and details in the audit record.
    await record_admin_action(
        settings,
        actor_id=UUID(user["id"]),
        action="post_deleted",
        post_id=None,
        details={
            "deleted_post_id": str(post_id),
            "post_owner_id": str(post["user_id"]),
            "post_title": post["title"],
            "images_deleted": len(images),
        },
    )

    return Response(status_code=204)


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

