FROM python:3.13-slim

# Install C++ compiler needed by chroma-hnswlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# Install dependencies first (cache-friendly layer)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt sentence-transformers

# Copy backend application code
COPY backend/app/ app/

# Copy data files (PDFs + golden dataset) to match relative path expectations
# config.py defaults: PAPER_DATA_DIR=../data, GOLDEN_DATASET_PATH=../Golden Dataset...
COPY data/ /app/data/
COPY ["Golden Dataset _interview sample (1).xlsx", "/app/Golden Dataset _interview sample (1).xlsx"]

# Pre-download embedding model AND pre-build ChromaDB index at build time
# This avoids expensive indexing on every cold start
ENV CHROMA_PERSIST_DIR=./db/chroma
ENV PAPER_DATA_DIR=../data
ENV EMBEDDING_MODEL=all-mpnet-base-v2
RUN python -c "\
from app.services.vector_store import VectorStore; \
store = VectorStore(); \
result = store.index_papers(); \
print(f'Pre-indexed: {result}') \
"

# Remove build tools to shrink final image
RUN apt-get purge -y build-essential && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
