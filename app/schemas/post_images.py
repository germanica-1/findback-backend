from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PostImageResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    post_id: UUID
    storage_path: str
    alt_text: str | None = None
    created_at: datetime

