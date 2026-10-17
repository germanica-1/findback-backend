from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FeedAuthor(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    full_name: str | None = None
    avatar_url: str | None = None


class FeedCategory(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str


class FeedImage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    alt_text: str | None = None
    created_at: datetime
    signed_url: str


class FeedPostResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    user_id: UUID
    category_id: int
    post_type: Literal["missing", "found"]
    status: Literal["open", "resolved"]
    title: str
    description: str
    location: str
    item_date: date
    created_at: datetime
    updated_at: datetime

    author: FeedAuthor | None = None
    category: FeedCategory
    images: list[FeedImage]
    comment_count: int

