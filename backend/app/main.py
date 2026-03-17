from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.models import AskRequest, AskResponse, EvalResultsPayload, PapersResponse, RetrievedChunk
from app.services.golden_dataset import load_golden_questions
from app.services.rag_service import RAGService

# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

rag_service = RAGService()
# Per-IP sliding-window rate-limit log: ip -> deque of timestamps
_request_log: dict[str, deque[float]] = defaultdict(deque)


# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Index papers in a background thread so health checks pass immediately."""
    import threading

    def _index():
        try:
            result = rag_service.ensure_index()
            print(f"[startup] Indexing complete: {result}", flush=True)
        except Exception as exc:
            print(f"[startup] Indexing failed: {exc}", flush=True)

    t = threading.Thread(target=_index, daemon=True)
    t.start()
    print("[startup] Server ready, indexing in background thread...", flush=True)
    yield


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Wildfire RAG API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)

_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://0.0.0.0:5173",
    "http://0.0.0.0:5174",
]

# Allow Cloud Run origins (set ALLOWED_ORIGINS env var to comma-separated URLs)
import os
_extra = os.environ.get("ALLOWED_ORIGINS", "")
if _extra:
    _CORS_ORIGINS.extend(o.strip() for o in _extra.split(",") if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)


# ---------------------------------------------------------------------------
# Middleware: security headers + per-IP rate limiting
# ---------------------------------------------------------------------------

@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next):
    # ---- Rate limiting for /api/* endpoints --------------------------------
    if request.url.path.startswith("/api/"):
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        bucket = _request_log[client_ip]
        cutoff = now - 60.0

        # Evict timestamps older than the window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        # Prevent unbounded memory growth: purge stale IP entries periodically
        if len(_request_log) > 5_000:
            stale = [
                ip for ip, q in list(_request_log.items())
                if not q or q[-1] < cutoff
            ]
            for ip in stale[:500]:
                del _request_log[ip]

        if len(bucket) >= settings.rate_limit_per_minute:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded. Please wait a minute and retry."},
                headers={"Retry-After": "60"},
            )

        bucket.append(now)

    # ---- Call the actual route handler -------------------------------------
    response: Response = await call_next(request)

    # ---- Harden HTTP responses ---------------------------------------------
    response.headers.update(
        {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
        }
    )
    return response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": settings.anthropic_model,
        "chunks_indexed": rag_service.store.collection.count(),
    }


@app.get("/api/papers", response_model=PapersResponse)
def list_papers() -> PapersResponse:
    return PapersResponse(papers=rag_service.list_papers())


@app.post("/api/index")
def reindex() -> dict[str, int]:
    """Trigger a full re-index of all PDFs in the data directory."""
    return rag_service.store.index_papers()


@app.post("/api/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    question = payload.question.strip()[: settings.max_question_chars]
    result = rag_service.ask(question)
    chunks = [RetrievedChunk(**chunk) for chunk in result["retrieved_chunks"]]
    return AskResponse(
        answer=result["answer"],
        citations=result["citations"],
        citation_warnings=result.get("citation_warnings", []),
        retrieved_chunks=chunks,
    )


@app.get("/api/golden")
def golden_questions() -> dict:
    return {"questions": load_golden_questions()}


@app.post("/api/eval-results")
def save_eval_results(payload: EvalResultsPayload) -> dict[str, int | str]:
    settings.outputs_dir_abs.mkdir(parents=True, exist_ok=True)
    settings.eval_results_path.write_text(
        json.dumps(payload.results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {"status": "saved", "count": len(payload.results)}
