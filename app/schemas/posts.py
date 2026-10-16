from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CategoryResponse(BaseModel):
    id: int
    name: str


class PostCreate(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=1, max_length=5000)
    location: str = Field(min_length=1, max_length=255)
    item_date: date
    category_id: int
    post_type: Literal["missing", "found"]


class PostResponse(BaseModel):
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

