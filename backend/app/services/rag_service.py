from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone

from app.config import settings
from app.services.llm_client import LLMClient
from app.services.vector_store import VectorStore

# ---------------------------------------------------------------------------
# System prompt – matches golden dataset style: short bullets, [Paper N]
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = (
    "You are a concise research assistant for wildfire & disaster governance. "
    "Answer ONLY from the provided context passages.\n\n"
    "Rules:\n"
    "- Respond with 2-5 bullet points. Fewer is better — only include genuinely distinct points.\n"
    "- Each bullet is a VERY short phrase (3-10 words max). "
    "Use imperative verbs or noun phrases.\n"
    "- Cite ONLY the paper(s) that directly support each bullet. "
    "If one paper covers the topic well, it is fine to cite only that paper.\n"
    "- End every bullet with: [Paper N]\n"
    "- No page numbers, no prose, no headings, no markdown, no elaboration.\n"
    "- If the context has no relevant evidence, respond EXACTLY with: "
    "'I cannot answer this from the provided papers.'\n\n"
    "Good examples:\n"
    "- Budget cuts [Paper 4]\n"
    "- Changing governmental priorities [Paper 4]\n"
    "- Invest more in prevention and risk reduction [Paper 5]\n"
    "- No. Effectiveness depends on local conditions [Paper 6]"
)

_REFUSAL_LOWER = "i cannot answer this from the provided papers."

# ---------------------------------------------------------------------------
# Multi-query expansion: generate diverse sub-queries to broaden retrieval
# ---------------------------------------------------------------------------
_QUERY_FACETS: list[tuple[list[str], list[str]]] = [
    # (trigger keywords, extra sub-queries to run)
    (
        ["government", "governments", "governance", "policy"],
        [
            "government prevention risk reduction investment fire policy",
            "cross-government coordination collaboration wildfire governance",
            "governance participation adaptation stakeholder engagement",
        ],
    ),
    (
        ["community", "communities", "local"],
        [
            "community participation prevention fire management local knowledge",
            "integrated fire management community involvement tropical",
            "local participation indigenous traditional burning",
        ],
    ),
    (
        ["evacuation", "evacuate", "emergency"],
        [
            "evacuation planning vulnerable populations disabled elderly",
            "evacuation communication nonwhite impoverished communities",
            "behavioral data evacuation simulation decision sequence",
        ],
    ),
    (
        ["vulnerable", "disadvantaged", "equity"],
        [
            "social vulnerability disadvantaged populations disaster",
            "nonwhite impoverished disability evacuation assistance",
            "unemployment childcare shelter evacuation support",
        ],
    ),
    (
        ["prescribed", "burn", "burning", "fuel"],
        [
            "prescribed fire effectiveness location treatment",
            "mechanical thinning versus controlled burn",
            "CAL FIRE fuel treatment wildland urban",
        ],
    ),
    (
        ["challenge", "challenges", "threat", "barrier"],
        [
            "budget cuts governmental priorities obstacles fire management",
            "rule of law crisis fire ban community trust",
            "barriers integrated fire management implementation",
        ],
    ),
    (
        ["role", "play", "should"],
        [
            "participation involvement contribution prevention fire",
            "community role fire management knowledge sharing",
            "government role prevention risk reduction coordination",
        ],
    ),
]


class RAGService:
    def __init__(self) -> None:
        self.store = VectorStore()
        self.llm = LLMClient()
        # Simple in-process TTL cache: hash -> (result, monotonic_timestamp)
        self._cache: dict[str, tuple[dict, float]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_index(self) -> dict[str, int]:
        """Index all PDFs on startup if the collection is empty."""
        if self.store.collection.count() == 0:
            return self.store.index_papers()
        return {"papers_indexed": 0, "chunks_indexed": 0}

    def ask(self, question: str) -> dict:
        key = self._cache_key(question)
        now = time.monotonic()

        cached = self._cache.get(key)
        if cached is not None:
            result, ts = cached
            if now - ts < settings.cache_ttl_seconds:
                return result

        result = self._ask_uncached(question)

        # Store; evict oldest when cache exceeds 200 entries
        self._cache[key] = (result, now)
        if len(self._cache) > 200:
            oldest = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest]

        return result

    def list_papers(self) -> list[dict]:
        return self.store.list_papers()

    # ------------------------------------------------------------------
    # Internal retrieval + generation
    # ------------------------------------------------------------------

    def _ask_uncached(self, question: str) -> dict:
        # --- Strategy 5: Query expansion ---
        expanded_queries = self._expand_query(question)
        all_queries = [question] + expanded_queries

        # Retrieve with a wide net (2x top_k) to find diverse papers,
        # then narrow down via dedup + diversity logic
        retrieval_k = settings.max_context_chunks * 2
        all_hits: list[dict] = []
        seen_chunk_ids: set[str] = set()
        for q in all_queries:
            hits = self.store.search(q, top_k=retrieval_k)
            for hit in hits:
                cid = hit.get("chunk_id", "")
                if cid not in seen_chunk_ids:
                    seen_chunk_ids.add(cid)
                    all_hits.append(hit)

        # Sort all hits by score descending, then dedup, threshold, diversify
        all_hits.sort(key=lambda h: h.get("score", 0), reverse=True)
        hits = self._deduplicate_hits(all_hits)
        hits = self._apply_relevance_threshold(hits)
        hits = self._ensure_paper_diversity(hits, settings.max_context_chunks)

        context = self._build_context(hits)
        user_prompt = f"Question: {question}\n\nContext:\n{context}"
        raw_answer = self.llm.answer(system_prompt=_SYSTEM_PROMPT, user_prompt=user_prompt)

        # Enforce citation format + bullet contract
        answer = self._enforce_bullet_contract(raw_answer)

        citations = sorted(set(re.findall(r"\[Paper\s+\d+\]", answer)))
        citation_warnings = self._validate_citations(citations, hits, answer)

        self._log_retrieval_event(question=question, citations=citations, hits=hits)

        return {
            "answer": answer,
            "citations": citations,
            "citation_warnings": citation_warnings,
            "retrieved_chunks": hits,
        }

    # ------------------------------------------------------------------
    # Query expansion (faceted sub-queries, no LLM call)
    # ------------------------------------------------------------------

    @staticmethod
    def _expand_query(question: str) -> list[str]:
        """Generate targeted sub-queries based on question keywords."""
        q_lower = question.lower()
        sub_queries: list[str] = []

        for triggers, facets in _QUERY_FACETS:
            if any(t in q_lower for t in triggers):
                for facet in facets:
                    if facet not in sub_queries:
                        sub_queries.append(facet)

        # Cap at 6 sub-queries to keep latency reasonable
        return sub_queries[:6]

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate_hits(hits: list[dict]) -> list[dict]:
        """Keep only the highest-scoring chunk per (paper_id, page) pair."""
        best: dict[tuple, dict] = {}
        for hit in hits:
            key = (hit.get("paper_id"), hit.get("page"))
            if key not in best or hit["score"] > best[key]["score"]:
                best[key] = hit
        return sorted(best.values(), key=lambda h: h["score"], reverse=True)

    @staticmethod
    def _ensure_paper_diversity(hits: list[dict], top_k: int) -> list[dict]:
        """Round-robin across papers so no single paper dominates context.

        Takes the deduplicated, score-sorted hits and interleaves them so
        that each paper gets represented before any paper gets a 2nd chunk.
        """
        from collections import defaultdict

        by_paper: dict[int, list[dict]] = defaultdict(list)
        for h in hits:
            by_paper[h.get("paper_id", 0)].append(h)

        result: list[dict] = []
        seen: set[str] = set()
        round_idx = 0
        while len(result) < top_k:
            added = False
            # Sort paper IDs by best remaining score each round
            active_papers = sorted(
                by_paper.keys(),
                key=lambda pid: by_paper[pid][0]["score"] if by_paper[pid] else 0,
                reverse=True,
            )
            for pid in active_papers:
                queue = by_paper[pid]
                if round_idx < len(queue):
                    chunk = queue[round_idx]
                    cid = chunk.get("chunk_id", "")
                    if cid not in seen:
                        seen.add(cid)
                        result.append(chunk)
                        added = True
                        if len(result) >= top_k:
                            break
            round_idx += 1
            if not added:
                break
        return result

    @staticmethod
    def _apply_relevance_threshold(hits: list[dict]) -> list[dict]:
        """Drop chunks below the configured minimum relevance score."""
        threshold = settings.min_relevance_score
        return [h for h in hits if h.get("score", 0) >= threshold]

    @staticmethod
    def _build_context(hits: list[dict]) -> str:
        """Compact, token-efficient context string for the LLM."""
        blocks: list[str] = []
        for hit in hits:
            header = f"[Paper {hit.get('paper_id')}] {hit.get('paper_title', '')}"
            blocks.append(f"{header}\n{hit.get('text', '').strip()}")
        return "\n\n---\n\n".join(blocks)

    # ------------------------------------------------------------------
    # Citation validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_citations(
        citations: list[str], hits: list[dict], answer: str
    ) -> list[str]:
        warnings: list[str] = []
        if _REFUSAL_LOWER in answer.lower():
            return warnings

        if not citations:
            warnings.append("Answer contains no citations.")

        hit_papers = {h.get("paper_id") for h in hits}

        for citation in citations:
            m = re.search(r"\[Paper\s+(\d+)\]", citation)
            if not m:
                warnings.append(f"Unrecognised citation format: {citation}")
                continue
            paper_id = int(m.group(1))
            if paper_id not in hit_papers:
                warnings.append(f"Citation paper not in retrieved context: {citation}")

        return warnings

    # ------------------------------------------------------------------
    # Output normalisation (Strategy 1: citation format match)
    # ------------------------------------------------------------------

    @staticmethod
    def _enforce_bullet_contract(answer: str) -> str:
        """Normalise raw LLM output to clean cited bullet list matching [Paper N] format."""
        text = str(answer or "").strip()
        if not text or _REFUSAL_LOWER in text.lower():
            return "I cannot answer this from the provided papers."

        lines = [l.strip() for l in text.replace("\r", "\n").split("\n") if l.strip()]
        normalised: list[str] = []
        for line in lines:
            line = re.sub(r"^#{1,6}\s+", "", line)
            line = re.sub(r"^[-*\u2022]\s+", "", line)
            line = re.sub(r"^\d+\.\s+", "", line)
            line = line.strip()
            if line:
                normalised.append(line)

        # Convert any [Citations: Paper N] or [Paper N, p.X] to [Paper N]
        def _normalise_cite(text: str) -> str:
            text = re.sub(
                r"\[Citations:\s*Paper\s+(\d+)\]",
                r"[Paper \1]",
                text,
            )
            text = re.sub(
                r"\[Paper\s+(\d+)(?:,\s*p\.\d+)?\]",
                r"[Paper \1]",
                text,
            )
            return text

        cited: list[str] = []
        for line in normalised:
            line = _normalise_cite(line)
            cites = re.findall(r"\[Paper\s+\d+\]", line)
            if not cites:
                continue
            # Ensure citation is at the end
            if re.search(r"\[Paper\s+\d+\]\s*$", line):
                cited.append(f"- {line}")
            else:
                clean = re.sub(r"\[Paper\s+\d+\]", "", line).strip()
                clean = re.sub(r"[\s.,;:]+$", "", clean)
                cited.append(f"- {clean} {cites[-1]}")

        top = cited[:5]
        if not top:
            return "I cannot answer this from the provided papers."
        return "\n".join(top)

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    @staticmethod
    def _log_retrieval_event(
        question: str, citations: list[str], hits: list[dict]
    ) -> None:
        settings.outputs_dir_abs.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "citations": citations,
            "top_k": len(hits),
            "hits": [
                {
                    "chunk_id": h.get("chunk_id"),
                    "paper_id": h.get("paper_id"),
                    "page": h.get("page"),
                    "score": round(h.get("score", 0.0), 4),
                }
                for h in hits
            ],
        }
        with settings.retrieval_debug_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Cache utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(question: str) -> str:
        return hashlib.md5(question.strip().lower().encode()).hexdigest()
