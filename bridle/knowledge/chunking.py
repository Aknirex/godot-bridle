from __future__ import annotations

import hashlib

from bridle.knowledge.documents import KnowledgeChunk, KnowledgeDocument

MAX_CHUNK_LINES = 80


def chunk_document(document: KnowledgeDocument) -> list[KnowledgeChunk]:
    lines = document.content.splitlines()
    if not lines:
        return []
    suffix = str(document.metadata.get("suffix", ""))
    starts = {0}
    for index, line in enumerate(lines):
        stripped = line.strip()
        is_boundary = (
            (suffix == ".md" and stripped.startswith("#"))
            or (
                suffix == ".gd"
                and (stripped.startswith("func ") or stripped.startswith("class_name "))
            )
            or (suffix in {".tscn", ".tres"} and stripped.startswith("["))
        )
        if is_boundary:
            starts.add(index)
    boundaries = sorted(starts)
    chunks: list[KnowledgeChunk] = []
    for section_index, start in enumerate(boundaries):
        stop = boundaries[section_index + 1] if section_index + 1 < len(boundaries) else len(lines)
        for part_start in range(start, stop, MAX_CHUNK_LINES):
            part_stop = min(part_start + MAX_CHUNK_LINES, stop)
            text = "\n".join(lines[part_start:part_stop]).strip()
            if not text:
                continue
            digest = hashlib.sha256(
                f"{document.source_id}:{part_start + 1}:{text}".encode()
            ).hexdigest()
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"chunk_{digest}",
                    source_id=document.source_id,
                    source_type=document.source_type,
                    text=text,
                    content_hash=hashlib.sha256(text.encode()).hexdigest(),
                    start_line=part_start + 1,
                    end_line=part_stop,
                    metadata=dict(document.metadata),
                )
            )
    return chunks
