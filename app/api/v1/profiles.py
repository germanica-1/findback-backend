
from urllib.parse import quote
from uuid import UUID, uuid4
from typing import Literal

import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.security import get_current_user
from app.core.supabase import supabase_request
from app.schemas.profiles import ProfileResponse, ProfileUpdate
from app.schemas.posts import PostResponse

router = APIRouter(prefix="/api/v1", tags=["Profiles"])
bearer_scheme = HTTPBearer(auto_error=False)

MAX_FILE_SIZE = 5 * 1024 * 1024
BUCKET = "item-images"
AVATAR_FOLDER = "avatars"
SIGNED_URL_EXPIRY = 3600

PROFILE_FIELDS = (
    "id,full_name,bio,avatar_url,role,created_at,updated_at"
)


def detect_image_type(contents: bytes) -> tuple[str, str]:
    """Validate image contents and return a safe file extension and MIME type."""
    if contents.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"

    if contents.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"

    if (
        len(contents) >= 12
        and contents[:4] == b"RIFF"
        and contents[8:12] == b"WEBP"
    ):
        return "webp", "image/webp"

    raise HTTPException(
        status_code=415,
        detail="Unsupported image. Upload a valid JPEG, PNG, or WebP image.",
    )


def encode_storage_path(storage_path: str) -> str:
    return "/".join(
        quote(segment, safe="")
        for segment in storage_path.split("/")
    )


def is_avatar_path(value: str | None, user_id: str | UUID | None = None) -> bool:
    """Recognize stored avatar paths, optionally restricted to their owner."""
    if not value or value.startswith(("http://", "https://", "/")):
        return False

    parts = value.split("/")

    if len(parts) != 3 or parts[1] != AVATAR_FOLDER:
        return False

    return user_id is None or parts[0] == str(user_id)


async def create_signed_avatar_url(
    settings: Settings,
    access_token: str,
    storage_path: str,
) -> str:
    """Create a temporary URL for an image in the private Storage bucket."""
    encoded_path = encode_storage_path(storage_path)

    signing_url = (
        f"{settings.supabase_url.rstrip('/')}"
        f"/storage/v1/object/sign/{BUCKET}/{encoded_path}"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                signing_url,
                headers={
                    "apikey": settings.supabase_publishable_key,
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"expiresIn": SIGNED_URL_EXPIRY},
            )
    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="The image storage service is temporarily unavailable.",
        )

    if not response.is_success:
        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=response.status_code,
                detail="Storage access was denied. Check the bucket policies.",
            )

        raise HTTPException(
            status_code=502,
            detail="Could not generate the profile image URL.",
        )

    data = response.json()
    signed_url = data.get("signedURL") or data.get("signedUrl")

    if not signed_url:
        raise HTTPException(
            status_code=502,
            detail="The image storage service returned an invalid response.",
        )

    if signed_url.startswith(("http://", "https://")):
        return signed_url

    if signed_url.startswith("/storage/v1/"):
        return f"{settings.supabase_url.rstrip('/')}{signed_url}"

    if signed_url.startswith("/"):
        return (
            f"{settings.supabase_url.rstrip('/')}"
            f"/storage/v1{signed_url}"
        )

    return (
        f"{settings.supabase_url.rstrip('/')}"
        f"/storage/v1/{signed_url}"
    )


async def profile_with_avatar_url(
    profile: dict,
    settings: Settings,
    access_token: str,
) -> dict:
    """Return a profile with a usable URL without changing the stored path."""
    result = dict(profile)
    avatar = result.get("avatar_url")

    if avatar and not avatar.startswith(("http://", "https://")):
        result["avatar_url"] = await create_signed_avatar_url(
            settings,
            access_token,
            avatar,
        )

    return result


async def delete_storage_object(
    settings: Settings,
    access_token: str,
    storage_path: str,
) -> bool:
    """Best-effort Storage cleanup. Never expose credentials to the client."""
    encoded_path = encode_storage_path(storage_path)
    storage_url = (
        f"{settings.supabase_url.rstrip('/')}"
        f"/storage/v1/object/{BUCKET}/{encoded_path}"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.delete(
                storage_url,
                headers={
                    "apikey": settings.supabase_publishable_key,
                    "Authorization": f"Bearer {access_token}",
                },
            )
        return response.is_success
    except httpx.RequestError:
        return False


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
        raise HTTPException(status_code=404, detail="Profile not found.")

    return await profile_with_avatar_url(profiles[0], settings, token)


@router.post(
    "/profiles/me/avatar",
    response_model=ProfileResponse,
)
async def upload_my_avatar(
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    access_token = credentials.credentials
    user_id = str(user["id"])

    contents = await file.read(MAX_FILE_SIZE + 1)

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty.",
        )

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Image size must not exceed 5 MB.",
        )

    extension, content_type = detect_image_type(contents)

    # Confirm the user's profile exists and retain the previous avatar path.
    profiles = await supabase_request(
        settings,
        access_token,
        "GET",
        "profiles",
        params={
            "select": PROFILE_FIELDS,
            "id": f"eq.{user_id}",
            "limit": "1",
        },
    )

    if not profiles:
        raise HTTPException(status_code=404, detail="Profile not found.")

    old_avatar = profiles[0].get("avatar_url")

    # The filename is random; never trust a client-provided filename.
    storage_path = (
        f"{user_id}/{AVATAR_FOLDER}/{uuid4()}.{extension}"
    )
    encoded_path = encode_storage_path(storage_path)

    storage_url = (
        f"{settings.supabase_url.rstrip('/')}"
        f"/storage/v1/object/{BUCKET}/{encoded_path}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            upload_response = await client.post(
                storage_url,
                headers={
                    "apikey": settings.supabase_publishable_key,
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": content_type,
                    "x-upsert": "false",
                },
                content=contents,
            )
    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="The image storage service is temporarily unavailable.",
        )


    if not upload_response.is_success:
        # Log only the status and response body.
        # Never log authorization headers, tokens, or environment variables.
        print(
            "Avatar Storage upload failed:",
            upload_response.status_code,
            upload_response.text[:1000],
        )

        if upload_response.status_code in (401, 403):
            raise HTTPException(
                status_code=upload_response.status_code,
                detail=(
                    "Storage rejected the upload. Check the authenticated "
                    "user's Storage permissions and RLS policies."
                ),
            )

        raise HTTPException(
            status_code=502,
            detail=(
                "Image upload failed. Check the backend terminal for "
                "the Storage error."
            ),
        )

    # Persist the permanent storage path, never the expiring signed URL.
    try:
        updated_profiles = await supabase_request(
            settings,
            access_token,
            "PATCH",
            "profiles",
            params={
                "id": f"eq.{user_id}",
                "select": PROFILE_FIELDS,
            },
            payload={"avatar_url": storage_path},
            extra_headers={"Prefer": "return=representation"},
        )
    except HTTPException:
        await delete_storage_object(settings, access_token, storage_path)
        raise

    if not updated_profiles:
        await delete_storage_object(settings, access_token, storage_path)
        raise HTTPException(
            status_code=502,
            detail="The image uploaded, but the profile could not be updated.",
        )

    # Remove the previous avatar only after the new path has been saved.
    # Never delete an arbitrary URL or a post image.
    if is_avatar_path(old_avatar, user_id) and old_avatar != storage_path:
        await delete_storage_object(settings, access_token, old_avatar)

    return await profile_with_avatar_url(
        updated_profiles[0],
        settings,
        access_token,
    )


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

    return await profile_with_avatar_url(
        updated_profiles[0],
        settings,
        token,
    )


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
        raise HTTPException(status_code=404, detail="Profile not found.")

    return await profile_with_avatar_url(profiles[0], settings, token)


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
        raise HTTPException(status_code=404, detail="Profile not found.")

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

    return await supabase_request(
        settings,
        token,
        "GET",
        "posts",
        params=params,
    )

