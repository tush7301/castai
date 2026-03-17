# Cast AI - RAG Chatbot

A lightweight Retrieval-Augmented Generation (RAG) system for disaster and wildfire research Q&A.
It combines PDF retrieval with grounded LLM responses so answers stay tied to indexed papers.

## Tech Stack

### Frontend
- React + Vite: Chat UI, fast local development, and production bundling.
- CSS (custom theme): Landing/chat presentation and responsive layout.

### Backend
- FastAPI + Uvicorn: HTTP API for retrieval, question answering, and evaluation logging.
- Pydantic Settings + python-dotenv: Typed configuration and `.env` loading.

### Retrieval and Data
- ChromaDB: Persistent vector store for paper chunks.
- pypdf: PDF text extraction during indexing.
- pandas + openpyxl: Golden dataset loading and evaluation workflows.

### AI Tools
- Anthropic SDK (`claude-sonnet-4-6`): Final answer generation from retrieved context.
- Voyage AI embeddings (optional): Higher-quality embeddings when `VOYAGE_API_KEY` is set.
- Local sentence-transformer fallback: Embeddings still work without Voyage key.

## How To Run

### 1. Prerequisites
- Python 3.11+ (project currently runs in a local `.venv`)
- Node.js 18+
- npm

### 2. Backend setup

```bash
cd backend
python -m venv ../.venv
source ../.venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env` with at least:

```dotenv
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-sonnet-4-6
CHROMA_PERSIST_DIR=./db/chroma
PAPER_DATA_DIR=../data
GOLDEN_DATASET_PATH=../Golden Dataset _interview sample (1).xlsx
```

Optional keys/settings:

```dotenv
VOYAGE_API_KEY=your_voyage_key_here
EMBEDDING_MODEL=voyage-3
```

Run backend:

```bash
cd backend
../.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```

### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Open `http://localhost:5173`.

## System Structure

- `frontend/`: React chat app and UI styles.
- `backend/app/main.py`: API routes (`/api/health`, `/api/ask`, `/api/index`, `/api/papers`, `/api/golden`, `/api/eval-results`).
- `backend/app/services/vector_store.py`: PDF parsing, chunking, indexing, and vector search.
- `backend/app/services/rag_service.py`: Query expansion, retrieval filtering/diversity, prompt construction, and citation normalization.
- `backend/app/services/llm_client.py`: Claude API wrapper and error handling.
- `data/`: Source PDFs used for retrieval.
- `outputs/`: Retrieval/evaluation artifacts.

## Approach and Design Choices (Brief)

1. Retrieval-first grounding
The backend always retrieves context chunks before generation so responses are constrained by paper evidence.

2. Deterministic citation contract
The generation prompt and post-processing enforce short bullet answers ending with `[Paper N]`, which makes outputs easy to verify.

3. Balanced recall and precision
Query expansion increases recall, then deduplication, relevance thresholds, and per-paper diversity reduce noisy or repetitive context.

4. Operational simplicity
FastAPI + Vite keeps local iteration fast, while persistent Chroma storage avoids re-indexing on every run.

## Notes

- Do not commit real API keys in `.env`.
- If CORS/front-end port changes, update allowed origins in `backend/app/main.py`.
