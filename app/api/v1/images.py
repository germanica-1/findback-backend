from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
    Response,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.security import get_current_user
from app.core.supabase import supabase_request
from app.schemas.post_images import PostImageResponse, PostImageWithUrlResponse


router = APIRouter(prefix="/api/v1", tags=["Post Images"])

bearer_scheme = HTTPBearer()
MAX_FILE_SIZE = 5 * 1024 * 1024

ALLOWED_TYPES = {
    "jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    "png": ("image/png", b"\x89PNG\r\n\x1a\n"),
}


def detect_image_type(contents: bytes) -> tuple[str, str]:
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


@router.post(
    "/posts/{post_id}/images",
    response_model=PostImageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_post_image(
    post_id: UUID,
    file: UploadFile = File(...),
    alt_text: str | None = Form(default=None),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user: dict = Depends(get_current_user),
):
    settings = get_settings()
    access_token = credentials.credentials

    # Confirm that the post exists and belongs to the current user.
    posts = await supabase_request(
        settings,
        access_token,
        "GET",
        "posts",
        params={
            "select": "id,user_id",
            "id": f"eq.{post_id}",
            "limit": "1",
        },
    )

    if not posts:
        raise HTTPException(status_code=404, detail="Post not found.")

    if str(posts[0]["user_id"]) != str(user["id"]):
        raise HTTPException(
            status_code=403,
            detail="You can only upload images to your own posts.",
        )

    if alt_text is not None and len(alt_text) > 500:
        raise HTTPException(
            status_code=422,
            detail="Alternative text must not exceed 500 characters.",
        )

    contents = await file.read(MAX_FILE_SIZE + 1)

    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Image size must not exceed 5 MB.",
        )

    extension, content_type = detect_image_type(contents)

    # Never use the original filename as the storage path.
    storage_path = (
        f"{user['id']}/{post_id}/{uuid4()}.{extension}"
    )

    # Register metadata first. If storage upload fails, we can remove
    # this metadata row using the user's existing RLS permissions.
    inserted = await supabase_request(
        settings,
        access_token,
        "POST",
        "post_images",
        params={
            "select": "id,post_id,storage_path,alt_text,created_at"
        },
        payload={
            "post_id": str(post_id),
            "storage_path": storage_path,
            "alt_text": alt_text.strip() if alt_text else None,
        },
        extra_headers={"Prefer": "return=representation"},
    )

    if not inserted:
        raise HTTPException(
            status_code=502,
            detail="Could not register image metadata.",
        )

    image_record = inserted[0]
    encoded_path = "/".join(
        quote(segment, safe="")
        for segment in storage_path.split("/")
    )
    storage_url = (
        f"{settings.supabase_url.rstrip('/')}"
        f"/storage/v1/object/item-images/{encoded_path}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
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
        response = None

    if response is None or not response.is_success:
        # Best-effort rollback: remove the metadata if the upload failed.
        try:
            await supabase_request(
                settings,
                access_token,
                "DELETE",
                "post_images",
                params={"id": f"eq.{image_record['id']}"},
                extra_headers={"Prefer": "return=minimal"},
            )
        except HTTPException:
            pass

        if response is not None and response.status_code in (401, 403):
            raise HTTPException(
                status_code=response.status_code,
                detail="Supabase Storage rejected the upload.",
            )

        raise HTTPException(
            status_code=502,
            detail="Image upload failed. Please try again.",
        )

    return image_record


@router.get(
    "/posts/{post_id}/images",
    response_model=list[PostImageWithUrlResponse],
)
async def get_post_images(
    post_id: UUID,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user: dict = Depends(get_current_user),
):
    settings = get_settings()
    access_token = credentials.credentials

    # Verify that the post exists.
    posts = await supabase_request(
        settings,
        access_token,
        "GET",
        "posts",
        params={
            "select": "id",
            "id": f"eq.{post_id}",
            "limit": "1",
        },
    )

    if not posts:
        raise HTTPException(status_code=404, detail="Post not found.")

    # Retrieve the registered image metadata.
    images = await supabase_request(
        settings,
        access_token,
        "GET",
        "post_images",
        params={
            "select": "id,post_id,storage_path,alt_text,created_at",
            "post_id": f"eq.{post_id}",
            "order": "created_at.asc",
        },
    )

    results = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for image_record in images:
            encoded_path = "/".join(
                quote(segment, safe="")
                for segment in image_record["storage_path"].split("/")
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
                        "Authorization": f"Bearer {access_token}",
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
                    detail="Could not generate an image URL.",
                )

            data = response.json()
            signed_url = data.get("signedURL") or data.get("signedUrl")

            if not signed_url:
                raise HTTPException(
                    status_code=502,
                    detail="The image storage service returned an invalid response.",
                )

            if signed_url.startswith("http://") or signed_url.startswith("https://"):
                pass
            elif signed_url.startswith("/storage/v1/"):
                signed_url = (
                    f"{settings.supabase_url.rstrip('/')}{signed_url}"
                )
            elif signed_url.startswith("/"):
                signed_url = (
                    f"{settings.supabase_url.rstrip('/')}/storage/v1{signed_url}"
                )
            else:
                signed_url = (
                    f"{settings.supabase_url.rstrip('/')}"
                    f"/storage/v1/{signed_url}"
                )

            results.append({
                **image_record,
                "signed_url": signed_url,
            })

    return results


@router.delete("/images/{image_id}", status_code=204)
async def delete_post_image(
    image_id: UUID,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    user: dict = Depends(get_current_user),
):
    settings = get_settings()
    access_token = credentials.credentials

    # Find the registered image.
    images = await supabase_request(
        settings,
        access_token,
        "GET",
        "post_images",
        params={
            "select": "id,post_id,storage_path",
            "id": f"eq.{image_id}",
            "limit": "1",
        },
    )

    if not images:
        raise HTTPException(status_code=404, detail="Image not found.")

    image_record = images[0]

    # Verify ownership of the parent post.
    posts = await supabase_request(
        settings,
        access_token,
        "GET",
        "posts",
        params={
            "select": "id,user_id",
            "id": f"eq.{image_record['post_id']}",
            "limit": "1",
        },
    )

    if not posts:
        raise HTTPException(status_code=404, detail="Parent post not found.")

    if str(posts[0]["user_id"]) != str(user["id"]):
        raise HTTPException(
            status_code=403,
            detail="You can only delete images from your own posts.",
        )

    # Delete the Storage object while its metadata still exists.
    encoded_path = "/".join(
        quote(segment, safe="")
        for segment in image_record["storage_path"].split("/")
    )

    storage_url = (
        f"{settings.supabase_url.rstrip('/')}"
        f"/storage/v1/object/item-images/{encoded_path}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                storage_url,
                headers={
                    "apikey": settings.supabase_publishable_key,
                    "Authorization": f"Bearer {access_token}",
                },
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
                detail="Supabase Storage rejected the deletion.",
            )

        raise HTTPException(
            status_code=502,
            detail="Could not delete the image from storage.",
        )

    # Remove metadata only after Storage deletion succeeds.
    try:
        await supabase_request(
            settings,
            access_token,
            "DELETE",
            "post_images",
            params={"id": f"eq.{image_id}"},
            extra_headers={"Prefer": "return=minimal"},
        )
    except HTTPException:
        raise HTTPException(
            status_code=502,
            detail=(
                "The image file was deleted, but its metadata could not "
                "be removed. Check the post_images table."
            ),
        )

    return None

