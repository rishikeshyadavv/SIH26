FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg2 and NetCDF parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and data directory
COPY src/ ./src/
COPY data/ ./data/

# Run ETL to pre-ingest data into the database during build
RUN python -m src.etl.fetch_argo

EXPOSE 8000

# FIX H5: Run as non-root user to limit blast radius of any container escape
RUN useradd --uid 1001 --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser

# FIX H5: HEALTHCHECK so orchestrators can detect unhealthy containers
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run FastAPI backend using uvicorn
CMD ["uvicorn", "src.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
