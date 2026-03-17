from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # -- Anthropic -----------------------------------------------------------
    anthropic_api_key: str | None = None

    @field_validator("anthropic_api_key", "voyage_api_key", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: str | None) -> str | None:
        """Treat empty-string env vars as unset."""
        if isinstance(v, str) and not v.strip():
            return None
        return v
    anthropic_model: str = "claude-sonnet-4-6"

    # -- Embeddings -----------------------------------------------------------
    voyage_api_key: str | None = None
    embedding_model: str = "all-mpnet-base-v2"  # local; or "voyage-3" if key + billing set

    # -- Storage paths -------------------------------------------------------
    chroma_persist_dir: str = "./db/chroma"
    paper_data_dir: str = "../data"
    golden_dataset_path: str = "../Golden Dataset _interview sample (1).xlsx"

    # -- RAG parameters ------------------------------------------------------
    max_context_chunks: int = 8       # top-k retrieved chunks per query
    chunk_size: int = 800             # characters per chunk (smaller = sharper embeddings)
    chunk_overlap: int = 150          # overlap between adjacent chunks
    min_relevance_score: float = 0.20 # discard chunks below this similarity

    # -- LLM parameters -------------------------------------------------------
    max_tokens: int = 500             # bullets are short; saves tokens
    cache_ttl_seconds: int = 300      # response cache lifetime (5 min)

    # -- API / security -------------------------------------------------------
    max_question_chars: int = 500     # hard cap on input length
    rate_limit_per_minute: int = 30   # requests per IP per 60-second window

    # -------------------------------------------------------------------------
    # Computed paths  (always derived from this file's location so relative
    # paths in .env work regardless of the working directory at runtime)
    # -------------------------------------------------------------------------

    @property
    def backend_root(self) -> Path:
        """Absolute path to the backend/ directory."""
        return Path(__file__).resolve().parents[1]

    @property
    def workspace_root(self) -> Path:
        """Absolute path to the project root (parent of backend/)."""
        return self.backend_root.parent

    @property
    def chroma_dir_abs(self) -> Path:
        return (self.backend_root / self.chroma_persist_dir).resolve()

    @property
    def paper_data_dir_abs(self) -> Path:
        return (self.backend_root / self.paper_data_dir).resolve()

    @property
    def golden_dataset_path_abs(self) -> Path:
        """Resolved absolute path to the Excel golden-dataset file."""
        return (self.backend_root / self.golden_dataset_path).resolve()

    @property
    def outputs_dir_abs(self) -> Path:
        return (self.workspace_root / "outputs").resolve()

    @property
    def retrieval_debug_path(self) -> Path:
        return self.outputs_dir_abs / "retrievalDebug.jsonl"

    @property
    def eval_results_path(self) -> Path:
        return self.outputs_dir_abs / "evalResults.json"


settings = Settings()
