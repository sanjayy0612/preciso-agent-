from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


RunMode = Literal["fetch_ingest", "fetch_ingest_query", "query_existing"]
SourceType = Literal[
    "sec_filing",
    "management_discussion",
    "earnings_calendar",
    "local_document",
]
DataSource = Literal["openbb", "local"]


class ProviderRequest(BaseModel):
    company: str
    ticker: str
    data_source: DataSource = "openbb"
    source_types: list[SourceType] = Field(default_factory=list)
    form_types: list[str] = Field(default_factory=list)
    max_documents: int = 3
    run_mode: RunMode = "fetch_ingest"
    query: str | None = None


class ParsedIntent(BaseModel):
    company: str
    ticker: str | None = None
    run_mode: RunMode = "fetch_ingest"
    data_source: DataSource = "openbb"
    source_types: list[SourceType] = Field(default_factory=list)
    query_after_ingest: str | None = None
    existing_graph_query: str | None = None
    max_documents: int = 3


class NormalizedSourceDocument(BaseModel):
    document_id: str
    title: str
    source_type: SourceType
    ticker: str
    source_reference: str
    event_date: str | None = None
    fetch_timestamp: str
    body_markdown: str
    output_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractionArtifact(BaseModel):
    document_id: str
    source_path: str
    extraction_path: str
    status: Literal["success", "error"]
    message: str | None = None


class PrecisoIngestResult(BaseModel):
    extraction_path: str
    ingest_status: str
    entities_added: int = 0
    relationships_added: int = 0
    chunks_stored: int = 0
    message: str | None = None


class AgentState(TypedDict, total=False):
    user_prompt: str
    messages: list[dict[str, str]]
    parsed_intent: ParsedIntent
    provider_request: ProviderRequest
    normalized_documents: list[NormalizedSourceDocument]
    source_paths: list[str]
    extraction_artifacts: list[ExtractionArtifact]
    preciso_status: dict[str, Any]
    ingest_results: list[PrecisoIngestResult]
    query_result: dict[str, Any] | None
    final_response: str
    errors: list[str]

