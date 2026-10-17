from datetime import datetime
from typing import Any
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

