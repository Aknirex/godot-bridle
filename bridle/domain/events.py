from __future__ import annotations

from datetime import datetime
from typing import TypeAlias

from pydantic import BaseModel, Field

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


class JobEvent(BaseModel):
    id: str
    job_id: str
    sequence: int = Field(ge=1)
    type: str
    stage: str | None = None
    message: str
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: datetime
