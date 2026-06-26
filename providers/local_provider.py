from __future__ import annotations

from datetime import datetime
from pathlib import Path

from config import Settings
from models import NormalizedSourceDocument, ProviderRequest


# Text-like files we can ingest as-is. Everything else (binary, PDF, etc.) is
# skipped for v1 — drop pre-converted Markdown/text in the inbox instead.
SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".text"}


class LocalFolderProvider:
    """Bring-your-own-data provider.

    Reads files the user drops into the inbox folder (``PRECISO_AGENT_INBOX``,
    default ``workspace/inbox``) and normalizes them into source documents. No
    network calls are made — the document text never leaves the machine until
    you point the embedding/LLM provider at a remote service.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch_documents(self, request: ProviderRequest) -> list[NormalizedSourceDocument]:
        inbox = self.settings.inbox_dir
        if not inbox.exists():
            raise ValueError(
                f"Inbox folder {inbox} does not exist. Create it and drop source files inside."
            )

        files = sorted(
            path
            for path in inbox.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        )
        if request.max_documents:
            files = files[: request.max_documents]

        if not files:
            raise ValueError(
                f"No supported documents found in {inbox}. "
                f"Supported extensions: {', '.join(sorted(SUPPORTED_SUFFIXES))}."
            )

        fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        ticker = (request.ticker or request.company or "LOCAL").upper()

        docs: list[NormalizedSourceDocument] = []
        for path in files:
            body = path.read_text(encoding="utf-8", errors="replace").strip()
            if not body:
                continue
            stat = path.stat()
            event_date = datetime.utcfromtimestamp(stat.st_mtime).date().isoformat()
            docs.append(
                NormalizedSourceDocument(
                    document_id=f"local_{path.stem}",
                    title=path.stem.replace("_", " ").strip() or path.name,
                    source_type="local_document",
                    ticker=ticker,
                    source_reference=str(path),
                    event_date=event_date,
                    fetch_timestamp=fetched_at,
                    body_markdown=body,
                    metadata={
                        "origin": "local_inbox",
                        "relative_path": str(path.relative_to(inbox)),
                        "size_bytes": stat.st_size,
                    },
                )
            )

        if not docs:
            raise ValueError(f"All candidate files in {inbox} were empty.")
        return docs
