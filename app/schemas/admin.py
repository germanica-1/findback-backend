
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AdminLogResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    actor_id: UUID
    action: str
    post_id: UUID | None = None
    details: dict[str, Any] | None = None
    created_at: datetime

class AdminRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["student", "admin"]


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    full_name: str
    email: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    role: Literal["student", "admin"]
    created_at: datetime
    updated_at: datetime

