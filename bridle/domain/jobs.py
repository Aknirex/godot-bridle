from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class JobState(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_PROVIDER = "waiting_provider"
    DOWNLOADING = "downloading"
    IMPORTING = "importing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class JobRef(BaseModel):
    job_id: str


class JobStatus(BaseModel):
    job_id: str
    workflow_id: str
    state: JobState
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime
    error_code: str | None = None
    safe_details: str | None = None
