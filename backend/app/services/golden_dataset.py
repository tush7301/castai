from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.config import settings


@dataclass
class GoldenQuestion:
    id: str
    question: str
    keywords: list[str]
    bullet_keys: list[str]
    is_unanswerable: bool


def load_golden_questions() -> list[dict]:
    xlsx_path = settings.golden_dataset_path_abs
    if not xlsx_path.exists():
        return []

    df = pd.read_excel(xlsx_path)
    if df.empty:
        return []

    cols = {str(c).strip().lower(): c for c in df.columns}

    question_col = _find_col(cols, ["question", "questions", "prompt"])
    bullets_col = _find_col(cols, ["bullet", "key", "answer", "reference", "golden"])
    unanswerable_col = _find_col(cols, ["unanswerable", "abstain", "refusal"])

    if not question_col:
        question_col = df.columns[0]
    if not bullets_col:
        bullets_col = df.columns[min(1, len(df.columns) - 1)]

    rows: list[GoldenQuestion] = []
    for _, row in df.iterrows():
        question = str(row.get(question_col, "")).strip()
        if not question or question.lower() == "nan":
            continue

        raw_bullets = str(row.get(bullets_col, "")).strip()
        bullet_keys = _split_bullets(raw_bullets)

        is_unanswerable = False
        if unanswerable_col:
            marker = str(row.get(unanswerable_col, "")).strip().lower()
            is_unanswerable = marker in {"1", "true", "yes", "y"}

        if not is_unanswerable:
            lowered = question.lower()
            if "unanswerable" in lowered or "not answerable" in lowered:
                is_unanswerable = True

        rows.append(
            GoldenQuestion(
                id=f"Q{len(rows) + 1}",
                question=question,
                keywords=_keywords_from_question(question),
                bullet_keys=bullet_keys,
                is_unanswerable=is_unanswerable,
            )
        )

    # If none are explicitly marked unanswerable, treat the final two as such.
    if len(rows) >= 8 and not any(r.is_unanswerable for r in rows):
        rows[-1].is_unanswerable = True
        rows[-2].is_unanswerable = True

    return [r.__dict__ for r in rows[:8]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_col(cols: dict[str, object], candidates: list[str]):
    for key_lower, original in cols.items():
        if any(token in key_lower for token in candidates):
            return original
    return None


def _split_bullets(value: str) -> list[str]:
    text = value.replace("\r", "\n")
    parts = [line.strip(" -\t") for line in text.split("\n")]
    parts = [p for p in parts if p and p.lower() != "nan"]
    if not parts and value and value.lower() != "nan":
        parts = [p.strip() for p in value.split(";") if p.strip()]
    return parts


def _keywords_from_question(question: str) -> list[str]:
    stop = {
        "what", "which", "where", "when", "who", "how", "why",
        "is", "are", "the", "a", "an", "of", "in", "to", "for",
        "and", "on", "from", "with", "does", "do", "did", "its",
        "this", "that", "these", "those", "can", "could", "would",
    }
    words: list[str] = []
    for token in question.lower().replace("?", " ").replace(",", " ").split():
        token = token.strip("'\".")
        if len(token) > 2 and token not in stop:
            words.append(token)
    return list(dict.fromkeys(words))
