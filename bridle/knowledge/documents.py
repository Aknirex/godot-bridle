from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from bridle.domain.events import JsonValue


class KnowledgeSourceType(StrEnum):
    GODOT_PROJECT = "godot_project"
    BRIDLE_DOC = "bridle_doc"
    BRIDLE_JOB = "bridle_job"
    ASSET_REPORT = "asset_report"
    EXTERNAL_DOC = "external_doc"


class KnowledgeDocument(BaseModel):
    source_id: str
    source_type: KnowledgeSourceType
    project_root: Path | None = None
    path: Path | None = None
    title: str | None = None
    content: str
    content_hash: str
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class KnowledgeChunk(BaseModel):
    chunk_id: str
    source_id: str
    source_type: KnowledgeSourceType
    text: str
    content_hash: str
    start_line: int | None = None
    end_line: int | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class KnowledgeIndexSummary(BaseModel):
    project_root: Path
    documents_scanned: int = 0
    documents_added: int = 0
    documents_updated: int = 0
    documents_unchanged: int = 0
    documents_deleted: int = 0
    chunks_written: int = 0
    files_skipped: int = 0
    warnings: list[str] = Field(default_factory=list)


class KnowledgeIndexStatus(BaseModel):
    project_root: Path
    indexed: bool = False
    documents_indexed: int = 0
    chunks_indexed: int = 0
    last_indexed_at: str | None = None


class RetrievalHit(BaseModel):
    chunk_id: str
    source_id: str
    source_type: KnowledgeSourceType
    text: str
    score: float
    citation: str
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class KnowledgeCitation(BaseModel):
    label: str
    chunk_id: str
    source_id: str
    citation: str
    score: float


class KnowledgeAnswer(BaseModel):
    question: str
    answer: str
    citations: list[KnowledgeCitation] = Field(default_factory=list)
    retrieval_hits: list[RetrievalHit] = Field(default_factory=list)
    latency_ms: int = 0
    warnings: list[str] = Field(default_factory=list)
