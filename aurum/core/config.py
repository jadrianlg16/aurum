"""Configuration from the environment. Every value has a default; nothing machine-specific lives here."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_TRUE = {"1", "true", "yes", "on"}

# Workspace ids are path segments on disk: lowercase, digits and '-', 2..41 chars (shared by
# core/workspaces.py and every router that touches {DATA_DIR}/workspaces/<id>).
WS_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


class InvalidWorkspaceId(ValueError):
    """Raised before any filesystem path is built from an untrusted workspace id."""


def env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in _TRUE


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


def env_list(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Comma-separated list → tuple of stripped, non-empty items."""
    raw = env(name, "")
    if not raw:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


#: Hosts that mean "this machine" for the bind check.
LOOPBACK_BINDS = frozenset({"127.0.0.1", "::1", "localhost"})


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_host: str
    api_port: int
    mcp_port: int
    api_url: str
    llm_provider: str
    llm_model: str
    embed_model: str
    ollama_url: str
    anthropic_api_key: str
    cloud_opt_in: bool
    ocr_url: str
    llm_quickadd: bool
    api_token: str
    demo_mode: bool
    max_upload_mb: int
    rate_limit_per_min: int
    # --- security posture (docs/SECURITY.md) ---
    bind: str
    require_token: bool
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]
    forwarded_allow_ips: str
    mcp_host: str
    mcp_token: str
    ledger_cache: bool
    fetch_max_mb: int
    allow_private_fetch: bool
    zip_max_members: int
    zip_max_member_mb: int
    zip_max_total_mb: int
    # --- read-only settings for core, pf and organizer (read, never written) ---
    protected_workspaces: tuple[str, ...]
    backup_keep: int
    migrate_protected: bool
    test_clock: bool

    @property
    def db_path(self) -> Path:
        return self.data_dir / "aurum.db"

    @property
    def corpus_db_path(self) -> Path:
        return self.data_dir / "corpus.db"

    @property
    def workspaces_dir(self) -> Path:
        return self.data_dir / "workspaces"

    @property
    def vault_dir(self) -> Path:
        return self.data_dir / "vault"

    @property
    def secrets_dir(self) -> Path:
        return self.data_dir / "secrets"

    @property
    def bind_is_loopback(self) -> bool:
        return self.bind.strip().lower() in LOOPBACK_BINDS

    def workspace_dir(self, ws_id: str) -> Path:
        if not WS_ID_RE.match(ws_id or ""):
            raise InvalidWorkspaceId(ws_id)
        return self.workspaces_dir / ws_id


def settings() -> Settings:
    """Read settings fresh each call so tests can monkeypatch the environment."""
    return Settings(
        data_dir=Path(env("AURUM_DATA_DIR", "./data")).resolve(),
        api_host=env("AURUM_API_HOST", "127.0.0.1"),
        api_port=env_int("AURUM_API_PORT", 5041),
        mcp_port=env_int("AURUM_MCP_PORT", 5042),
        api_url=env("AURUM_API_URL", "http://localhost:5041"),
        llm_provider=env("AURUM_LLM_PROVIDER", "ollama"),
        llm_model=env("AURUM_LLM_MODEL", "llama3.1:8b"),
        embed_model=env("AURUM_EMBED_MODEL", "nomic-embed-text"),
        ollama_url=env("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        anthropic_api_key=env("ANTHROPIC_API_KEY", ""),
        cloud_opt_in=env_bool("AURUM_CLOUD_OPT_IN", False),
        ocr_url=env("AURUM_OCR_URL", ""),
        llm_quickadd=env_bool("AURUM_LLM_QUICKADD", False),
        api_token=env("AURUM_API_TOKEN", ""),
        demo_mode=env_bool("AURUM_DEMO_MODE", False),
        max_upload_mb=env_int("AURUM_MAX_UPLOAD_MB", 25),
        rate_limit_per_min=env_int("AURUM_RATE_LIMIT_PER_MIN", 600),
        bind=env("AURUM_BIND", "127.0.0.1"),
        require_token=env_bool("AURUM_REQUIRE_TOKEN", False),
        allowed_hosts=env_list("AURUM_ALLOWED_HOSTS"),
        allowed_origins=env_list("AURUM_ALLOWED_ORIGINS"),
        forwarded_allow_ips=env("AURUM_FORWARDED_ALLOW_IPS", "127.0.0.1"),
        mcp_host=env("AURUM_MCP_HOST", "127.0.0.1"),
        mcp_token=env("AURUM_MCP_TOKEN", ""),
        ledger_cache=env_bool("AURUM_LEDGER_CACHE", True),
        fetch_max_mb=env_int("AURUM_FETCH_MAX_MB", 10),
        allow_private_fetch=env_bool("AURUM_ALLOW_PRIVATE_FETCH", False),
        zip_max_members=env_int("AURUM_ZIP_MAX_MEMBERS", 500),
        zip_max_member_mb=env_int("AURUM_ZIP_MAX_MEMBER_MB", 10),
        zip_max_total_mb=env_int("AURUM_ZIP_MAX_TOTAL_MB", 100),
        protected_workspaces=env_list("AURUM_PROTECTED_WORKSPACES", ("personal",)),
        backup_keep=env_int("AURUM_BACKUP_KEEP", 10),
        migrate_protected=env_bool("AURUM_MIGRATE_PROTECTED", False),
        test_clock=env_bool("AURUM_TEST_CLOCK", False),
    )
