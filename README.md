# CAST AI - Research Assistant for Disasters

A Retrieval-Augmented Generation (RAG) chatbot that answers wildfire and disaster governance questions using evidence from indexed research papers. Every answer is grounded in the source material and cited with `[Paper N]` references.

**Live App:** https://rag-frontend-598315421142.us-central1.run.app

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User's Browser                           │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              React Frontend (Vite)                        │  │
│  │  Landing Page  ──►  Chat Interface  ──►  Cited Answers    │  │
│  └──────────────────────────┬────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────┘
                              │ HTTPS
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (Cloud Run)                    │
│                                                                 │
│  ┌──────────┐   ┌──────────────┐   ┌─────────────────────────┐ │
│  │ /api/ask │──►│  RAG Service  │──►│    Claude Sonnet 4.6    │ │
│  └──────────┘   │              │   │   (Answer Generation)    │ │
│                 │  1. Expand   │   └─────────────────────────┘ │
│                 │     query    │                                │
│                 │  2. Retrieve │   ┌─────────────────────────┐ │
│                 │     chunks   │◄──│  ChromaDB Vector Store   │ │
│                 │  3. Diversify│   │  (all-mpnet-base-v2)     │ │
│                 │  4. Generate │   │  6 PDFs → 316 chunks     │ │
│                 │  5. Validate │   └─────────────────────────┘ │
│                 │     citations│                                │
│                 └──────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

### How a Question Gets Answered

1. **Query Expansion** — The user's question is analyzed for key topics (governance, evacuation, community, etc.). Targeted sub-queries are generated to cast a wider retrieval net.
2. **Vector Retrieval** — ChromaDB searches the 316 pre-indexed chunks using `all-mpnet-base-v2` embeddings. Returns the top 16 candidates.
3. **Deduplication & Diversity** — Duplicate chunks from the same page are removed. A round-robin ensures multiple papers are represented, not just the top-scoring one.
4. **Answer Generation** — The top 8 chunks are sent to Claude Sonnet 4.6 with a strict prompt: respond in 2-5 short bullet points, each ending with `[Paper N]`.
5. **Citation Validation** — The response is post-processed to normalize citations and flag any that reference papers not in the retrieved context.

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 19, Vite 8 | Chat UI with landing page |
| **Styling** | Custom CSS | Warm cream/terracotta theme |
| **Backend** | FastAPI 0.115, Uvicorn | REST API with rate limiting |
| **Vector DB** | ChromaDB 0.6.3 | Persistent vector storage |
| **Embeddings** | all-mpnet-base-v2 | Sentence embeddings (local, free) |
| **LLM** | Claude Sonnet 4.6 (Anthropic) | Answer generation |
| **PDF Parsing** | pypdf | Text extraction from research papers |
| **Evaluation** | pandas, openpyxl | Golden dataset comparison |
| **Deployment** | Google Cloud Run | Serverless containers |
| **Secrets** | GCP Secret Manager | API key storage |

---

## Project Structure

```
RAG Chatbot/
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Landing page + chat routing
│   │   ├── components/
│   │   │   └── Chat.jsx         # Chat interface, message handling, citations
│   │   └── index.css            # Custom theme (terracotta, sage, cream)
│   ├── Dockerfile               # Multi-stage: Node build → Nginx serve
│   ├── nginx.conf               # SPA routing + static asset caching
│   └── package.json
│
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, routes, CORS, rate limiting
│   │   ├── config.py            # All settings via environment variables
│   │   ├── models.py            # Request/response schemas
│   │   └── services/
│   │       ├── rag_service.py   # Query expansion, retrieval, caching, citations
│   │       ├── vector_store.py  # PDF chunking, ChromaDB indexing, embeddings
│   │       ├── llm_client.py    # Claude API wrapper with error handling
│   │       └── golden_dataset.py # Test question loader from Excel
│   ├── Dockerfile               # Python + pre-built ChromaDB index
│   ├── requirements.txt
│   └── .env                     # API keys and settings (not committed)
│
├── data/                        # 6 wildfire research PDFs
│   ├── 1. Governing wildfires...pdf
│   ├── 2. Evacuation Decision making...pdf
│   ├── 3. Social vulnerabilities...pdf
│   ├── 4. Integrated fire management...pdf
│   ├── 5. Building a whole-of-government...pdf
│   └── 6. Effect of Recent Prescribed Burning...pdf
│
├── outputs/                     # Generated at runtime
│   ├── retrievalDebug.jsonl     # Retrieval audit log
│   └── evalResults.json         # Evaluation scores
│
├── Golden Dataset...xlsx        # 8 test questions with ideal answers
└── Dockerfile                   # Backend deployment Dockerfile
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check — returns model name and chunk count |
| `/api/ask` | POST | Submit a question, get bullet-point answer with citations |
| `/api/papers` | GET | List all indexed papers |
| `/api/index` | POST | Re-index all PDFs (rebuilds vector store) |
| `/api/golden` | GET | Load golden test questions from Excel |
| `/api/eval-results` | POST | Save evaluation results to JSON |

### Example Request

```bash
curl -X POST https://rag-backend-598315421142.us-central1.run.app/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What challenges threaten integrated fire management?"}'
```

### Example Response

```json
{
  "answer": "- Budget cuts [Paper 4]\n- Changing governmental priorities [Paper 4]\n- Crisis of rule of law [Paper 4]\n- Fire bans eroding community trust [Paper 4]",
  "citations": ["[Paper 4]"],
  "citation_warnings": [],
  "retrieved_chunks": [...]
}
```

---

## Running Locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- An Anthropic API key

### Backend

```bash
cd backend
python -m venv ../.venv
source ../.venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```dotenv
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-sonnet-4-6
CHROMA_PERSIST_DIR=./db/chroma
PAPER_DATA_DIR=../data
GOLDEN_DATASET_PATH=../Golden Dataset _interview sample (1).xlsx
MAX_CONTEXT_CHUNKS=8
CHUNK_SIZE=800
CHUNK_OVERLAP=150
MAX_TOKENS=500
```

Start the backend:

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

---

## Deployment (Google Cloud Run)

The app is deployed as two Cloud Run services in `us-central1`:

| Service | URL | Details |
|---------|-----|---------|
| `rag-backend` | https://rag-backend-598315421142.us-central1.run.app | 2 vCPU, 2Gi RAM, min 1 instance |
| `rag-frontend` | https://rag-frontend-598315421142.us-central1.run.app | Nginx serving static React build |

### How Deployment Works

- **Backend Docker image** pre-builds the ChromaDB index at image build time, so there is no indexing delay on startup.
- **Frontend Docker image** is a multi-stage build: Node builds the React app, then Nginx serves the static files.
- API keys are stored in **GCP Secret Manager** and injected as environment variables at runtime.
- The frontend calls the backend directly via its Cloud Run URL (no nginx proxy needed — CORS is configured on the backend).

### Redeploying

```bash
# Backend
cd "RAG Chatbot"
gcloud run deploy rag-backend --source . --region us-central1 --memory 2Gi --cpu 2

# Frontend
cd "RAG Chatbot/frontend"
gcloud run deploy rag-frontend --source . --region us-central1 --memory 256Mi
```

---

## Research Papers Indexed

| # | Paper | Topics |
|---|-------|--------|
| 1 | Governing Wildfires: A Systematic Analytical Framework | Governance frameworks, multi-level coordination |
| 2 | Evacuation Decision-Making and Behavior in Wildfires | Evacuation behavior, simulation models |
| 3 | Social Vulnerabilities and Wildfire Evacuations (Kincade Fire) | Equity, vulnerable populations, demographics |
| 4 | Integrated Fire Management in a Tropical Biosphere Reserve | Community-based fire management, challenges |
| 5 | Building a Whole-of-Government Fire Governance (Portugal) | Cross-government coordination, prevention |
| 6 | Effect of Recent Prescribed Burning and Land Management | Prescribed burns, treatment effectiveness |

---

## Design Decisions

**Retrieval-first grounding** — Every answer is generated from retrieved paper chunks, never from the LLM's training data. If no relevant evidence exists, the system responds with "I cannot answer this from the provided papers."

**Strict citation format** — Bullets end with `[Paper N]` so users can trace every claim back to a specific paper. Post-processing validates that cited papers actually appeared in the retrieved context.

**Query expansion** — Single questions often miss relevant papers. The system generates multiple sub-queries targeting different phrasings and synonyms to improve recall.

**Paper diversity** — A round-robin mechanism ensures the retrieved context includes chunks from multiple papers, preventing any single paper from dominating the answer.

**Response caching** — Identical questions are cached for 5 minutes to reduce API costs and response time.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-4-6` | LLM model to use |
| `VOYAGE_API_KEY` | No | — | Voyage AI key for better embeddings |
| `EMBEDDING_MODEL` | No | `all-mpnet-base-v2` | Embedding model name |
| `CHROMA_PERSIST_DIR` | No | `./db/chroma` | ChromaDB storage path |
| `PAPER_DATA_DIR` | No | `../data` | PDF source directory |
| `MAX_CONTEXT_CHUNKS` | No | `8` | Chunks sent to LLM |
| `CHUNK_SIZE` | No | `800` | Characters per chunk |
| `CHUNK_OVERLAP` | No | `150` | Overlap between chunks |
| `MIN_RELEVANCE_SCORE` | No | `0.20` | Minimum similarity threshold |
| `MAX_TOKENS` | No | `500` | Max LLM response tokens |
| `RATE_LIMIT_PER_MINUTE` | No | `30` | API rate limit per IP |

---

## Security

- API keys stored in GCP Secret Manager, never in source code
- Per-IP rate limiting (30 requests/minute)
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`
- Input length capped at 500 characters
- CORS restricted to known frontend origins
