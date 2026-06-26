from __future__ import annotations

import json
from typing import Any

from groq import Groq

from config import Settings
from models import ParsedIntent


INTENT_SYSTEM_PROMPT = """You are an orchestration assistant for a finance document graph agent.
Return only JSON.

Decide:
- company: company name or ticker from the user's request
- ticker: ticker if explicit, else null
- run_mode: one of fetch_ingest, fetch_ingest_query, query_existing
- data_source: "openbb" to pull SEC data, or "local" to use the user's own files in the inbox folder
- source_types: choose from sec_filing, management_discussion, earnings_calendar, local_document
- query_after_ingest: the follow-up graph question if the user wants one
- existing_graph_query: only for query_existing
- max_documents: choose a small integer 1-5

Rules:
- Default to SEC-focused data for finance requests (data_source "openbb").
- Use data_source "local" with source_types ["local_document"] when the user refers to their own
  files, the inbox/drop folder, "my documents", "the folder", or files they already placed locally.
- If the user asks to "ingest", "store", or "fetch and build", use fetch_ingest unless they also ask a question afterward.
- If the user asks a question after requesting fetch/ingest, use fetch_ingest_query.
- If the user only asks about already-ingested data, use query_existing.
- Prefer source_types sec_filing and management_discussion for openbb requests.
- Add earnings_calendar when earnings context or latest earnings is requested.
"""


EXTRACTION_SYSTEM_PROMPT = """You convert a single finance document into Preciso graph extraction JSON.
Return only valid JSON with this exact top-level structure:
{
  "document_id": "string",
  "entities": [
    {
      "entity_name": "string",
      "entity_type": "string",
      "description": "string",
      "source_id": "string",
      "file_path": "string"
    }
  ],
  "relationships": [
    {
      "src_id": "string",
      "tgt_id": "string",
      "description": "string",
      "keywords": "string",
      "source_id": "string",
      "file_path": "string",
      "weight": 1.0
    }
  ],
  "chunks": [
    {
      "chunk_id": "string",
      "content": "string",
      "file_path": "string"
    }
  ]
}

Rules:
- Extract only evidence-grounded entities and relationships.
- Keep entity and relationship names concise and stable.
- Each entity and relationship must reference a real chunk via source_id.
- chunks must preserve source text verbatim enough for later graph evidence.
- Prefer 4-20 entities for a typical filing excerpt.
- Never invent facts not present in the document.
"""


class GroqAgentClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = Groq(api_key=settings.groq_api_key) if settings.groq_api_key else None

    @property
    def available(self) -> bool:
        return self._client is not None

    def parse_intent(self, user_prompt: str) -> ParsedIntent:
        if not self._client:
            return _fallback_intent(user_prompt)

        raw = self._chat_json(
            system_prompt=INTENT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0,
        )
        try:
            return ParsedIntent.model_validate(json.loads(raw))
        except Exception:
            return _fallback_intent(user_prompt)

    def extract_graph_payload(
        self,
        *,
        document_id: str,
        file_path: str,
        markdown: str,
    ) -> dict[str, Any]:
        if not self._client:
            return _fallback_extraction(document_id=document_id, file_path=file_path, markdown=markdown)

        prompt = (
            f"document_id: {document_id}\n"
            f"file_path: {file_path}\n\n"
            "Document follows:\n"
            f"{markdown}"
        )
        raw = self._chat_json(
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0,
        )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return _fallback_extraction(document_id=document_id, file_path=file_path, markdown=markdown)
        parsed.setdefault("document_id", document_id)
        return parsed

    def summarize_run(self, prompt: str, run_context: dict[str, Any]) -> str:
        if not self._client:
            return _fallback_summary(prompt, run_context)
        response = self._client.chat.completions.create(
            model=self.settings.groq_model,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a concise financial workflow assistant. Summarize what was fetched, "
                        "stored, ingested, and optionally answered. Keep it grounded in the provided JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({"prompt": prompt, "run_context": run_context}, indent=2),
                },
            ],
        )
        return response.choices[0].message.content or _fallback_summary(prompt, run_context)

    def _chat_json(self, *, system_prompt: str, user_prompt: str, temperature: float) -> str:
        response = self._client.chat.completions.create(
            model=self.settings.groq_model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or "{}"


def _fallback_intent(user_prompt: str) -> ParsedIntent:
    lowered = user_prompt.lower()
    run_mode = "fetch_ingest"
    if any(token in lowered for token in ("what", "why", "how", "compare", "summarize", "tell me")):
        run_mode = "fetch_ingest_query"
    if "existing graph" in lowered or lowered.startswith("query "):
        run_mode = "query_existing"

    local_tokens = ("inbox", "my file", "my doc", "local folder", "the folder", "drop folder", "uploaded")
    data_source = "local" if any(token in lowered for token in local_tokens) else "openbb"

    if data_source == "local":
        source_types = ["local_document"]
    else:
        source_types = ["sec_filing", "management_discussion"]
        if "earnings" in lowered:
            source_types.append("earnings_calendar")

    words = [word.strip(",.?") for word in user_prompt.split()]
    ticker = next((word.upper() for word in words if 1 <= len(word) <= 5 and word.isalpha() and word.upper() == word), None)
    company = ticker or (words[0] if words else "UNKNOWN")

    return ParsedIntent(
        company=company,
        ticker=ticker,
        run_mode=run_mode,  # type: ignore[arg-type]
        data_source=data_source,  # type: ignore[arg-type]
        source_types=source_types,  # type: ignore[arg-type]
        query_after_ingest=user_prompt if run_mode == "fetch_ingest_query" else None,
        existing_graph_query=user_prompt if run_mode == "query_existing" else None,
        max_documents=3,
    )


def _fallback_extraction(*, document_id: str, file_path: str, markdown: str) -> dict[str, Any]:
    chunks = []
    entities = []
    relationships = []
    paragraphs = [block.strip() for block in markdown.split("\n\n") if block.strip()]
    for idx, block in enumerate(paragraphs[:8], start=1):
        chunk_id = f"chunk_{idx:03d}"
        chunks.append({"chunk_id": chunk_id, "content": block, "file_path": file_path})

    title = next((line.replace("#", "").strip() for line in markdown.splitlines() if line.strip().startswith("#")), document_id)
    entities.append(
        {
            "entity_name": title[:120],
            "entity_type": "DOCUMENT",
            "description": f"Source document for {document_id}",
            "source_id": chunks[0]["chunk_id"] if chunks else "chunk_001",
            "file_path": file_path,
        }
    )
    if len(chunks) > 1:
        entities.append(
            {
                "entity_name": "Management Discussion",
                "entity_type": "TOPIC",
                "description": "Management and financial discussion extracted from the source document.",
                "source_id": chunks[1]["chunk_id"],
                "file_path": file_path,
            }
        )
        relationships.append(
            {
                "src_id": title[:120],
                "tgt_id": "Management Discussion",
                "description": "Document contains management discussion and financial context.",
                "keywords": "contains,discussion,financial",
                "source_id": chunks[1]["chunk_id"],
                "file_path": file_path,
                "weight": 1.0,
            }
        )

    return {
        "document_id": document_id,
        "entities": entities,
        "relationships": relationships,
        "chunks": chunks or [{"chunk_id": "chunk_001", "content": markdown[:2000], "file_path": file_path}],
    }


def _fallback_summary(prompt: str, run_context: dict[str, Any]) -> str:
    fetched = len(run_context.get("documents", []))
    ingested = len(run_context.get("ingest_results", []))
    query = run_context.get("query_result")
    lines = [
        f"Processed request: {prompt}",
        f"Fetched and stored {fetched} source document(s).",
        f"Ingested {ingested} extraction artifact(s) into Preciso.",
    ]
    if query:
        lines.append(f"Graph query status: {query.get('status', 'unknown')}.")
    return "\n".join(lines)

