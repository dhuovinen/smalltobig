"""Runtime configuration.

`STB_*` environment variables, with `.env` auto-loaded. Explicit environment
variables still override the file — see docs/DECISIONS.md #9 for why loading
is automatic rather than left to the caller to `source` by hand.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LlmOptions(TypedDict):
    """Keyword arguments for OpenAICompatClient (see Settings.llm_options)."""

    model: str
    api_key: str
    enable_thinking: bool | None
    timeout: float


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
    # Bearer key for servers that require one, even locally (omlx-serve, LM Studio
    # with auth). Kept as a secret: never logged, printed or rendered. Empty = none.
    llm_api_key: SecretStr = SecretStr("")
    # Thinking models spend the token budget on hidden reasoning and can return an
    # empty answer (DECISIONS #25). False sends
    # chat_template_kwargs.enable_thinking=false; None sends nothing.
    llm_enable_thinking: bool | None = None
    # Seconds per chat request. Larger models may need more than the default.
    llm_timeout: float = 30.0

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

    def llm_options(self, *, timeout: float | None = None) -> LlmOptions:
        """Keyword arguments for OpenAICompatClient: the one place they are assembled."""
        return {
            "model": self.llm_model,
            "api_key": self.llm_api_key.get_secret_value(),
            "enable_thinking": self.llm_enable_thinking,
            "timeout": self.llm_timeout if timeout is None else timeout,
        }

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
