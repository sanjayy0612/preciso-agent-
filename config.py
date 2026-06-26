from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


PROJECT_ROOT = Path(__file__).resolve().parent
PARENT_PRECIOSO_ROOT = PROJECT_ROOT.parent
_load_env_file(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    groq_model: str
    preciso_repo_root: Path
    workspace_root: Path
    sources_dir: Path
    extractions_dir: Path
    manifests_dir: Path
    inbox_dir: Path
    openbb_home: Path
    openbb_source_format: str
    default_form_types: tuple[str, ...]
    default_query_mode: str
    preciso_client_mode: str
    mcp_command: str
    mcp_args: tuple[str, ...]


def get_settings() -> Settings:
    workspace_root = Path(os.getenv("PRECISO_AGENT_WORKSPACE", PROJECT_ROOT / "workspace")).resolve()
    preciso_repo_root = Path(
        os.getenv("PRECISO_REPO_ROOT", PARENT_PRECIOSO_ROOT)
    ).resolve()
    openbb_home = Path(os.getenv("OPENBB_HOME", PROJECT_ROOT / ".openbb_platform")).resolve()
    inbox_dir = Path(os.getenv("PRECISO_AGENT_INBOX", workspace_root / "inbox")).resolve()

    # How the agent reaches the Preciso graph engine:
    #   "mcp"       -> talk to the graphrag-mcp server over stdio (same product any
    #                  external agent uses). This is the default.
    #   "inprocess" -> import the parent repo's tool functions directly (faster, but
    #                  couples the agent to the parent's Python internals).
    client_mode = (os.getenv("PRECISO_CLIENT_MODE", "mcp").strip().lower() or "mcp")

    default_launcher = preciso_repo_root / "scripts" / "mcp_launcher.sh"
    mcp_command = os.getenv("PRECISO_MCP_COMMAND", "/bin/sh").strip() or "/bin/sh"
    mcp_args_env = os.getenv("PRECISO_MCP_ARGS", "").strip()
    mcp_args = (
        tuple(part for part in mcp_args_env.split() if part)
        if mcp_args_env
        else (str(default_launcher),)
    )

    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
        preciso_repo_root=preciso_repo_root,
        workspace_root=workspace_root,
        sources_dir=workspace_root / "to_be_extracted",
        extractions_dir=workspace_root / "extractions",
        manifests_dir=workspace_root / "manifests",
        inbox_dir=inbox_dir,
        openbb_home=openbb_home,
        openbb_source_format=(os.getenv("OPENBB_SOURCE_FORMAT", "raw").strip().lower() or "raw"),
        default_form_types=tuple(
            item.strip().upper()
            for item in os.getenv("OPENBB_SEC_FORM_TYPES", "10-K,10-Q,8-K").split(",")
            if item.strip()
        ),
        default_query_mode=os.getenv("PRECISO_QUERY_MODE", "mix").strip() or "mix",
        preciso_client_mode=client_mode,
        mcp_command=mcp_command,
        mcp_args=mcp_args,
    )


def ensure_workspace(settings: Settings) -> None:
    for path in (
        settings.workspace_root,
        settings.sources_dir,
        settings.extractions_dir,
        settings.manifests_dir,
        settings.inbox_dir,
        settings.openbb_home,
    ):
        path.mkdir(parents=True, exist_ok=True)

