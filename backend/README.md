# Backend (Python + FastAPI)

## Setup

1. Create virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy env file:
   ```bash
   cp .env.example .env
   ```
4. Set `ANTHROPIC_API_KEY` in `.env`.

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

## Endpoints

- `GET /api/health`
- `GET /api/papers`
- `POST /api/index`
- `POST /api/ask` with JSON body:
  ```json
  {"question": "What are major wildfire governance challenges?"}
  ```
