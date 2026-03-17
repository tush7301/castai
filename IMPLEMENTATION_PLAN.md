# RAG Chatbot Implementation Plan (Scalable Vector DB Version)

## 1. Scope and Constraints

Goal: Build a browser-based RAG chatbot that answers from research papers and evaluates responses against 8 golden questions.

Updated design goals:
- Keep 4 layers: Client, RAG Pipeline, Knowledge, Evaluation.
- Replace full-context injection with vector retrieval so the system scales to many papers.
- Keep one Claude call per question (`/v1/messages`) for answer generation.
- Keep query matcher for Q1-Q8 detection and evaluation tracking.
- Keep client-side evaluation (bullet scorer + unanswerable check).

## 2. Target Repository Structure

```text
RAG Chatbot/
  data/
    papers/
      1. ...pdf
      2. ...pdf
      ...
    Golden Dataset _interview sample (1).xlsx
  scripts/
    extractPapers.mjs
    parseGoldenXlsx.mjs
    buildIndex.mjs
  db/
    chroma/                  # persisted vector collection files
  src/
    server/
      index.ts
      claudeClient.ts
      embeddingsClient.ts
      prompt.ts
      rag/
        retriever.ts
        vectorStore.ts
        citationFormatter.ts
    client/
      index.html
      styles.css
      app.ts
      tabs/
        chatTab.ts
        evalTab.ts
        papersTab.ts
      rag/
        queryMatcher.ts
      eval/
        bulletScorer.ts
        unanswerableCheck.ts
      state/
        store.ts
      types/
        models.ts
    knowledge/
      goldenDataset.ts
      refusalPhrases.ts
  outputs/
    evalResults.json
    retrievalDebug.json
  .env.example
  package.json
  tsconfig.json
  README.md
```

## 3. Layer-by-Layer Build Plan

### 3.1 Client Layer

Deliverables:
- Single-page app with 3 tabs: `Chat`, `Eval`, `Papers`.
- Quick Questions bar with Q1-Q8 chips/buttons that pre-fill input.
- Architecture-node click behavior can prefill a diagnostic question.

Implementation tasks:
1. Build tab shell and routing in `store.ts`.
2. Implement `Chat` tab:
   - question input, submit button, answer pane, citation pane.
3. Implement `Eval` tab:
   - summary cards (avg hit rate, unanswerable accuracy, citation coverage)
   - per-question result table.
4. Implement `Papers` tab:
   - list ingested papers, metadata, and indexing status.
5. Implement Quick Questions using `goldenDataset.ts`.

Acceptance criteria:
- User can ask free-form or click Q1-Q8 shortcut.
- Eval tab updates automatically after each answer.

### 3.2 RAG Pipeline Layer

Pipeline order (strict):
1. `queryMatcher` -> 2. `embed(question)` -> 3. `vectorRetriever(topK)` -> 4. `contextBuilder(from retrieved chunks)` -> 5. `systemPrompt` -> Claude API call

#### Query matcher

File: `src/client/rag/queryMatcher.ts`
- Input: `userQuestion`, `goldenDataset[]`.
- Normalize text: lowercase, punctuation removal, optional stopword filtering.
- Score with keyword overlap:
  - `score = overlap_keywords / max(1, golden_keywords)`
- Return best match and confidence.
- If `score >= 0.35`, map to `Qn`; otherwise free-form.

#### Embeddings + retrieval

Files:
- `src/server/embeddingsClient.ts`
- `src/server/rag/vectorStore.ts`
- `src/server/rag/retriever.ts`

Behavior:
- Create embedding for incoming question.
- Query vector DB for top-k chunks (default `k=8`, configurable).
- Optional metadata filter by paper IDs if user narrows scope.
- Return chunk text + metadata (paper ID/title/page/chunk ID/similarity).

#### Context builder

File: `src/server/rag/retriever.ts`
- Build final context only from retrieved chunks.
- Group by paper and include chunk headers:
  - `Paper 3 | page 12 | chunk p3_c44`

#### System prompt

File: `src/server/prompt.ts`
- Enforce:
  - Answer only from retrieved evidence.
  - Cite claims as `[Paper N, p.X]` when page known.
  - If insufficient evidence, refuse with:
    - `I cannot answer this from the provided papers.`

#### Claude call

File: `src/server/claudeClient.ts`
- Endpoint: `POST https://api.anthropic.com/v1/messages`
- Model: `claude-sonnet-4`
- One call per question.

Acceptance criteria:
- Exactly one Claude call per user question.
- Answers contain grounded citations or explicit refusal.

### 3.3 Knowledge Layer

Deliverables:
- Golden set in code (`goldenDataset.ts`).
- Papers indexed in vector DB with rich metadata.

Implementation tasks:
1. `extractPapers.mjs`
   - Parse each PDF into page-aware text blocks.
2. Chunking policy:
   - chunk size 700-1000 chars/tokens (configurable)
   - overlap 100-150
3. `buildIndex.mjs`
   - generate embeddings for each chunk
   - upsert into vector DB with metadata:
     - `paperId`, `paperTitle`, `page`, `chunkId`, `year`, `authors`
4. `parseGoldenXlsx.mjs`
   - parse 8 golden questions into:
```ts
{
  id: "Q1",
  question: string,
  keywords: string[],
  bulletKeys: string[],
  isUnanswerable: boolean
}
```

Acceptance criteria:
- Index can be rebuilt when new papers are added.
- New papers require no app code changes, only data + reindex.

### 3.4 Evaluation Layer

Runs client-side after API response.

#### Bullet scorer

File: `src/client/eval/bulletScorer.ts`
- Input: question ID, model answer, golden bullet keys.
- Output:
  - `hits`, `total`, `hitRate`, `matchedBullets[]`, `missedBullets[]`
- Formula:
  - `hitRate = hits / total`

#### Unanswerable check

File: `src/client/eval/unanswerableCheck.ts`
- Applies to Q7/Q8 or `isUnanswerable=true`.
- Detect refusal phrases:
  - `cannot answer from the provided papers`
  - `insufficient evidence`
  - `not stated in the papers`
- Output:
  - `isRefusalDetected`, `isCorrectAbstention`

#### Result store

File: `src/client/state/store.ts`
- Maintain `evalResults[]` in memory/localStorage.
- Persist snapshots to `outputs/evalResults.json` via backend endpoint.

Acceptance criteria:
- Eval metrics update automatically.
- Per-question and aggregate stats visible in Eval tab.

## 4. Data Contracts

```ts
export type GoldenQuestion = {
  id: string; // Q1..Q8
  question: string;
  keywords: string[];
  bulletKeys: string[];
  isUnanswerable: boolean;
};

export type PaperChunk = {
  chunkId: string;
  paperId: number;
  paperTitle: string;
  page?: number;
  text: string;
  embedding?: number[];
};

export type RetrievalHit = {
  chunkId: string;
  paperId: number;
  paperTitle: string;
  page?: number;
  text: string;
  score: number;
};

export type EvalResult = {
  questionId: string;
  matchedGoldenQuestionId?: string;
  matchScore: number;
  answer: string;
  citationsFound: string[];
  bulletHits: number;
  bulletTotal: number;
  bulletHitRate: number;
  isRefusalDetected: boolean;
  isCorrectAbstention?: boolean;
  timestamp: string;
};
```

## 5. API and Security Plan

- Keep Anthropic API key and embedding API key on server only.
- Client calls `/api/ask` with:
  - `question`, `matchedQuestionId`, `promptVersion`.
- Server handles retrieval and prompt assembly internally.
- Add input length caps and basic rate-limit middleware.

## 6. Verification and Quality Plan

### Functional checks
- Q1-Q8 quick buttons submit correctly.
- Query matcher maps expected questions.
- Retrieval returns relevant chunks and paper/page metadata.
- Answers include citations and refusal for unanswerables.

### Evaluation checks
- For each Q1-Q8, store:
  - answer text
  - bullet hit rate
  - abstention correctness
  - retrieved chunk IDs for traceability
- Aggregate report:
  - avg bullet hit rate over answerable questions
  - abstention accuracy over unanswerable questions
  - citation coverage rate

### Citation validation (bonus)
- Regex parse citation format: `\[Paper\s[1-9][0-9]*,\sp\.[0-9]+\]`.
- Warn if non-refusal answer has no citations.
- Validate each cited paper/page exists in retrieved hits.

### Retrieval validation (bonus)
- Track `topK`, `minScore`, and hit overlap with expected-paper heuristics.
- Log retrieval debug output to `outputs/retrievalDebug.json`.

## 7. Implementation Sequence

1. Initialize TS app (client + server) and env config.
2. Build PDF and XLSX parsing scripts.
3. Implement chunking and vector index build script.
4. Implement retriever (`embed + topK + context assembly`).
5. Implement Claude answer generation with citation/refusal prompt.
6. Build Chat/Eval/Papers UI and quick Q1-Q8 shortcuts.
7. Implement bullet scorer and unanswerable checker.
8. Run full Q1-Q8 batch, tune chunking and retrieval params.
9. Add new-paper ingestion path and verify reindex workflow.
10. Export final evaluation and retrieval diagnostics.

## 8. Risks and Mitigations

- Risk: Poor chunking hurts retrieval quality.
  - Mitigation: tune chunk size/overlap and evaluate on Q1-Q8.
- Risk: Embedding model mismatch with domain language.
  - Mitigation: test at least two embedding models and compare hit rate.
- Risk: Citation hallucination.
  - Mitigation: enforce citations from retrieved metadata only.
- Risk: Keyword scorer misses paraphrases.
  - Mitigation: add synonym lists and optional fuzzy phrase matching.

## 9. Definition of Done

- End-to-end app runs with Chat, Eval, Papers tabs.
- Papers are indexed in persistent vector DB and retrievable.
- Adding a new PDF and rerunning indexing makes it queryable.
- All 8 golden questions can be run from Quick Questions.
- Eval tab reports bullet-hit metrics and abstention correctness.
- Outputs include reproducible eval and retrieval debug artifacts.
