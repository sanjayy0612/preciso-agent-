from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import Future
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import Settings


class MCPPrecisoClient:
    """Preciso graph client that talks to the ``graphrag-mcp`` server over stdio.

    This is the same MCP server any external agent (Claude Code, Codex, ...)
    connects to. The agent dogfoods its own product instead of importing the
    parent repo's internals.

    The MCP protocol is async, but the agent workflow runs synchronously, so a
    single background event-loop thread owns the connection for the agent's
    lifetime. The server process is spawned once and reused across calls.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session: ClientSession | None = None
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._stop = threading.Event()
        self._wake: asyncio.Event | None = None

    # -- public sync API (mirrors PrecisoClient) -------------------------------

    def get_status(self) -> dict[str, Any]:
        return self._call_tool("get_server_status", {})

    def ingest_file(self, file_path: str) -> dict[str, Any]:
        return self._call_tool("ingest_from_file", {"file_path": file_path})

    def reingest_file(self, file_path: str) -> dict[str, Any]:
        return self._call_tool("reingest_from_file", {"file_path": file_path})

    def query_graph(self, query: str, mode: str) -> dict[str, Any]:
        return self._call_tool("query_graph_tool", {"query": query, "mode": mode})

    def close(self) -> None:
        self._stop.set()
        wake = self._wake
        if self._loop and self._loop.is_running() and wake is not None:
            self._loop.call_soon_threadsafe(wake.set)
        if self._thread:
            self._thread.join(timeout=10)

    # -- connection lifecycle --------------------------------------------------

    def _ensure_started(self) -> None:
        if self._thread is not None:
            self._ready.wait()
            if self._startup_error is not None:
                raise RuntimeError(
                    f"Failed to start graphrag-mcp server: {self._startup_error}"
                ) from self._startup_error
            return

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._startup_error is not None:
            raise RuntimeError(
                f"Failed to start graphrag-mcp server: {self._startup_error}"
            ) from self._startup_error

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except BaseException as exc:  # noqa: BLE001 - surfaced to caller thread
            if self._startup_error is None:
                self._startup_error = exc
            self._ready.set()
        finally:
            self._loop.close()

    async def _serve(self) -> None:
        self._wake = asyncio.Event()
        params = StdioServerParameters(
            command=self.settings.mcp_command,
            args=list(self.settings.mcp_args),
            cwd=str(self.settings.preciso_repo_root),
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    self._ready.set()
                    # Hold the connection open until close() is requested.
                    while not self._stop.is_set():
                        await self._wake.wait()
                        self._wake.clear()
        except BaseException as exc:  # noqa: BLE001
            if self._startup_error is None:
                self._startup_error = exc
            self._ready.set()
            raise

    # -- tool dispatch ---------------------------------------------------------

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._ensure_started()
        assert self._loop is not None
        future: Future = asyncio.run_coroutine_threadsafe(
            self._call_tool_async(name, arguments), self._loop
        )
        return future.result()

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert self._session is not None
        result = await self._session.call_tool(name, arguments)
        return _result_to_dict(result, tool_name=name)


def _result_to_dict(result: Any, *, tool_name: str) -> dict[str, Any]:
    if getattr(result, "isError", False):
        text = _first_text(result)
        return {"status": "error", "message": text or f"{tool_name} returned an error"}

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        # FastMCP wraps bare return values under a "result" key; unwrap when the
        # tool itself already returns a dict (which all graphrag-mcp tools do).
        inner = structured.get("result")
        if isinstance(inner, dict):
            return inner
        return structured

    text = _first_text(result)
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {"status": "success", "message": text}
    return {"status": "success", "message": f"{tool_name} returned no content"}


def _first_text(result: Any) -> str | None:
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            return text
    return None
