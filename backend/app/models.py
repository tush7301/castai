from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1200)


class RetrievedChunk(BaseModel):
    chunk_id: str
    paper_id: int | None = None
    paper_title: str
    page: int | None = None
    score: float
    text: str


class AskResponse(BaseModel):
    answer: str
    citations: list[str]
    citation_warnings: list[str]
    retrieved_chunks: list[RetrievedChunk]


class PaperSummary(BaseModel):
    paper_id: int
    title: str
    source_file: str


class PapersResponse(BaseModel):
    papers: list[PaperSummary]


class EvalResultsPayload(BaseModel):
    results: list[dict]
