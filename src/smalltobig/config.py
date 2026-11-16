"""Runtime configuration.

`STB_*` environment variables, with `.env` auto-loaded. Explicit environment
variables still override the file — see docs/DECISIONS.md #9 for why loading
is automatic rather than left to the caller to `source` by hand.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Web UI. See docs/DECISIONS.md #1.
    port: int = 8028

    # Chat, over an OpenAI-compatible HTTP endpoint. Pinned off mlx_lm.server's
    # default of 8000 — see docs/DECISIONS.md #2.
    llm_base_url: str = "http://127.0.0.1:3140/v1"
    llm_model: str = ""

    # Embeddings load in-process via mlx-embeddings, which ships no server.
    # Default is a small, fast model good for smoke-testing `stb doctor`;
    # swap in something like mlx-community/bge-m3-mlx-8bit for real use.
    embedding_model: str = "mlx-community/all-MiniLM-L6-v2-bf16"

    # All local state — inbox, sources/<id>/, the sqlite db — lives under one
    # directory outside the repo, per docs/PLAN.md §2 Stage 1 and §6.
    data_dir: Path = Path.home() / "SmallToBig"

    # Where the git checkout lives, for the git-tracked output directories
    # (rules/, lessons/, scenarios/ — docs/PLAN.md §6). Defaults to the
    # working directory `stb` is run from.
    repo_root: Path = Path.cwd()

    # The HTMSW framework YAML (docs/REQUIREMENTS.md FR-11). Resolved relative to
    # this package rather than the working directory, so `stb prep` works from
    # anywhere in an editable install.
    framework_dir: Path = Path(__file__).resolve().parents[2] / "framework"

    # DECISIONS #24. `abstracted` stores only integer step outcomes (FR-51);
    # `full` also keeps transcripts, debrief prose, verdict quotes and judge
    # request/response logs, for baseline comparison. Each profile has its own
    # database file under data_dir, so records never mix.
    privacy_profile: Literal["abstracted", "full"] = "abstracted"

    @property
    def inbox_dir(self) -> Path:
        return self.data_dir / "inbox"

    @property
    def sources_dir(self) -> Path:
        return self.data_dir / "sources"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "smalltobig.db"

    @property
    def record_db_path(self) -> Path:
        """The HTMSW session/progress store for the active privacy profile."""
        return self.data_dir / f"htmsw-{self.privacy_profile}.db"

    @property
    def rules_dir(self) -> Path:
        return self.repo_root / "rules"

    @property
    def lessons_dir(self) -> Path:
        return self.repo_root / "lessons"

    @property
    def scenarios_dir(self) -> Path:
        return self.repo_root / "scenarios"


def get_settings() -> Settings:
    return Settings()
