from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProfileResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    full_name: str
    bio: str | None = None
    avatar_url: str | None = None
    role: str
    created_at: datetime
    updated_at: datetime


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    bio: str | None = Field(
        default=None,
        max_length=500,
    )
    avatar_url: str | None = Field(
        default=None,
        max_length=2048,
    )

