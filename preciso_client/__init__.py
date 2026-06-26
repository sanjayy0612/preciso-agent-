from __future__ import annotations

from typing import Protocol

from config import Settings
from preciso_client.client import PrecisoClient


class PrecisoBackend(Protocol):
    def get_status(self) -> dict: ...
    def ingest_file(self, file_path: str) -> dict: ...
    def reingest_file(self, file_path: str) -> dict: ...
    def query_graph(self, query: str, mode: str) -> dict: ...


def build_preciso_client(settings: Settings) -> PrecisoBackend:
    """Return the configured Preciso backend.

    ``mcp`` (default) talks to the graphrag-mcp stdio server like any external
    agent would; ``inprocess`` imports the parent repo's tool functions directly.
    """
    if settings.preciso_client_mode == "inprocess":
        return PrecisoClient(settings)

    # Imported lazily so the in-process mode never requires the mcp client deps.
    from preciso_client.mcp_client import MCPPrecisoClient

    return MCPPrecisoClient(settings)


__all__ = ["PrecisoClient", "build_preciso_client", "PrecisoBackend"]
