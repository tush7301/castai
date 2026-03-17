from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
from pypdf import PdfReader

from app.config import settings

# Sentence-ending pattern for smarter chunk splitting
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


# ---------------------------------------------------------------------------
# Custom embedding function: Voyage-3 via voyageai SDK
# Falls back to ChromaDB's default (all-MiniLM-L6-v2) if no key configured.
# ---------------------------------------------------------------------------
class VoyageEmbeddingFunction(EmbeddingFunction[Documents]):
    """Wraps the voyageai SDK for use as a ChromaDB embedding function."""

    def __init__(self, model: str = "voyage-3", api_key: str | None = None):
        import voyageai

        self._client = voyageai.Client(api_key=api_key)
        self._model = model

    def __call__(self, input: Documents) -> Embeddings:
        # voyageai accepts a list of strings; returns objects with .embeddings
        result = self._client.embed(input, model=self._model, input_type=None)
        return result.embeddings  # list[list[float]]


def _get_embedding_fn():
    """Return the best available embedding function."""
    model = settings.embedding_model

    # Try Voyage if configured AND the model is a voyage model
    if settings.voyage_api_key and model.startswith("voyage"):
        try:
            fn = VoyageEmbeddingFunction(model=model, api_key=settings.voyage_api_key)
            fn(["test"])  # smoke-test
            print(f"[embeddings] Using Voyage model: {model}")
            return fn
        except Exception as exc:
            import warnings
            warnings.warn(f"Voyage init failed ({exc}); falling back to local.", stacklevel=2)

    # Local sentence-transformer model (all-mpnet-base-v2 >> all-MiniLM-L6-v2)
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    local_model = model if not model.startswith("voyage") else "all-mpnet-base-v2"
    print(f"[embeddings] Using local model: {local_model}")
    return SentenceTransformerEmbeddingFunction(model_name=local_model)


class VectorStore:
    def __init__(self) -> None:
        settings.chroma_dir_abs.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(settings.chroma_dir_abs))
        self._embedding_fn = _get_embedding_fn()
        self.collection = self.client.get_or_create_collection(
            name="papers", embedding_function=self._embedding_fn
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_papers(self) -> list[dict[str, Any]]:
        files = sorted(settings.paper_data_dir_abs.glob("*.pdf"))
        return [
            {
                "paper_id": idx,
                "title": self._title_from_filename(f.name),
                "source_file": f.name,
            }
            for idx, f in enumerate(files, start=1)
        ]

    def index_papers(self) -> dict[str, int]:
        files = sorted(settings.paper_data_dir_abs.glob("*.pdf"))
        chunks_added = 0

        for paper_id, pdf_path in enumerate(files, start=1):
            paper_title = self._title_from_filename(pdf_path.name)
            pages = self._extract_pages(pdf_path)

            for page_num, page_text in pages:
                page_chunks = self._chunk_text(page_text)
                for chunk_idx, chunk in enumerate(page_chunks):
                    chunk_id = f"p{paper_id}_pg{page_num}_c{chunk_idx}"
                    self.collection.upsert(
                        ids=[chunk_id],
                        documents=[chunk],
                        metadatas=[
                            {
                                "paper_id": paper_id,
                                "paper_title": paper_title,
                                "source_file": pdf_path.name,
                                "page": page_num,
                                "chunk_index": chunk_idx,
                            }
                        ],
                    )
                    chunks_added += 1

        return {"papers_indexed": len(files), "chunks_indexed": chunks_added}

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        if self.collection.count() == 0:
            return []

        results = self.collection.query(query_texts=[query], n_results=top_k)

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        ids = results.get("ids", [[]])[0]
        dists = results.get("distances", [[]])[0]

        hits: list[dict[str, Any]] = []
        for chunk_id, text, metadata, distance in zip(ids, docs, metas, dists):
            # Convert L2 distance to a [0, 1] similarity score.
            # ChromaDB uses squared-L2; smaller distance = more similar.
            similarity = 1.0 / (1.0 + float(distance))
            hits.append(
                {
                    "chunk_id": chunk_id,
                    "paper_id": int(metadata.get("paper_id", 0)) or None,
                    "paper_title": str(metadata.get("paper_title", "Unknown")),
                    "page": int(metadata.get("page", 0)) or None,
                    "score": round(similarity, 4),
                    "text": text,
                }
            )
        return hits

    # ------------------------------------------------------------------
    # PDF extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_pages(pdf_path: Path) -> list[tuple[int, str]]:
        reader = PdfReader(str(pdf_path))
        pages: list[tuple[int, str]] = []
        for i, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            # Skip pages that are mostly whitespace or very short (e.g. cover art)
            if len(text) > 50:
                pages.append((i, text))
        return pages

    # ------------------------------------------------------------------
    # Chunking – sentence-aware to avoid cutting mid-sentence
    # ------------------------------------------------------------------

    def _chunk_text(self, text: str) -> list[str]:
        size = settings.chunk_size
        overlap = settings.chunk_overlap

        if len(text) <= size:
            return [text] if text.strip() else []

        # Split on sentence boundaries first, then merge into chunks
        sentences = _SENTENCE_END.split(text)
        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            candidate = f"{current} {sentence}".strip() if current else sentence

            if len(candidate) <= size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                # If a single sentence exceeds chunk_size, hard-split it
                if len(sentence) > size:
                    hard_chunks = self._hard_split(sentence, size, overlap)
                    chunks.extend(hard_chunks[:-1])
                    current = hard_chunks[-1] if hard_chunks else ""
                else:
                    current = sentence

        if current.strip():
            chunks.append(current.strip())

        # Apply overlap: prepend the tail of the previous chunk to the next
        if overlap > 0 and len(chunks) > 1:
            overlapped: list[str] = [chunks[0]]
            for i in range(1, len(chunks)):
                tail = chunks[i - 1][-overlap:]
                overlapped.append(f"{tail} {chunks[i]}".strip())
            return [c for c in overlapped if c]

        return [c for c in chunks if c]

    @staticmethod
    def _hard_split(text: str, size: int, overlap: int) -> list[str]:
        """Fallback character-level splitter for very long single sentences."""
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end == len(text):
                break
            start = max(end - overlap, start + 1)
        return chunks

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _title_from_filename(name: str) -> str:
        clean = name.replace(".pdf", "")
        if ". " in clean:
            clean = clean.split(". ", 1)[1]
        return clean.strip()
