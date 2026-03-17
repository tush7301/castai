FROM python:3.13-slim

WORKDIR /app/backend

# Install dependencies first (cache-friendly layer)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt sentence-transformers

# Copy backend application code
COPY backend/app/ app/

# Copy data files (PDFs + golden dataset) to match relative path expectations
# config.py defaults: PAPER_DATA_DIR=../data, GOLDEN_DATASET_PATH=../Golden Dataset...
COPY data/ /app/data/
COPY Golden\ Dataset\ _interview\ sample\ \(1\).xlsx /app/Golden\ Dataset\ _interview\ sample\ \(1\).xlsx

# Pre-download the embedding model at build time (avoids ~30s cold start penalty)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-mpnet-base-v2')"

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
