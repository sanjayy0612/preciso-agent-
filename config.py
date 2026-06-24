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
    openbb_home: Path
    openbb_source_format: str
    default_form_types: tuple[str, ...]
    default_query_mode: str


def get_settings() -> Settings:
    workspace_root = Path(os.getenv("PRECISO_AGENT_WORKSPACE", PROJECT_ROOT / "workspace")).resolve()
    preciso_repo_root = Path(
        os.getenv("PRECISO_REPO_ROOT", PARENT_PRECIOSO_ROOT)
    ).resolve()
    openbb_home = Path(os.getenv("OPENBB_HOME", PROJECT_ROOT / ".openbb_platform")).resolve()

    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
        preciso_repo_root=preciso_repo_root,
        workspace_root=workspace_root,
        sources_dir=workspace_root / "to_be_extracted",
        extractions_dir=workspace_root / "extractions",
        manifests_dir=workspace_root / "manifests",
        openbb_home=openbb_home,
        openbb_source_format=(os.getenv("OPENBB_SOURCE_FORMAT", "raw").strip().lower() or "raw"),
        default_form_types=tuple(
            item.strip().upper()
            for item in os.getenv("OPENBB_SEC_FORM_TYPES", "10-K,10-Q,8-K").split(",")
            if item.strip()
        ),
        default_query_mode=os.getenv("PRECISO_QUERY_MODE", "mix").strip() or "mix",
    )


def ensure_workspace(settings: Settings) -> None:
    for path in (
        settings.workspace_root,
        settings.sources_dir,
        settings.extractions_dir,
        settings.manifests_dir,
        settings.openbb_home,
    ):
        path.mkdir(parents=True, exist_ok=True)

