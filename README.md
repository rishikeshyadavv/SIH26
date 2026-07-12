# FloatChat 🌊 — Conversational AI for ARGO Ocean Data

FloatChat lets anyone — a student, a policymaker, a maritime operator — ask questions about ocean data in plain English and get real answers back, charts included. No SQL knowledge needed.

It was built for **Smart India Hackathon Problem Statement SIH25040** (Ministry of Earth Sciences), and it runs on **real oceanographic sensor data**, not simulated numbers — pulled directly from the global ARGO float network.

> Ask: *"Show me the temperature profile of float 2902264"*
> Get: a working SQL query, the matching rows, and a Plotly depth-vs-temperature chart — in seconds.

---

## What problem this solves

ARGO floats are autonomous robots drifting through the world's oceans, diving every few days to measure temperature, salinity, and pressure at different depths. All of that data is public — but it's locked inside raw NetCDF binary files that only trained oceanographers know how to open.

FloatChat is the bridge: it downloads the real files, understands them, and lets you talk to the data instead of parsing scientific file formats yourself.

---

## How it works, end to end

```
You type a question
        ↓
Streamlit chat UI  (frontend/app.py)
        ↓  (authenticated HTTP request)
FastAPI backend     (src/backend/main.py)
        ↓
SQL Agent           (src/ai/sql_agent.py)
        ↓                          ↓
ChromaDB                      Redis cache
(finds similar                (instant replay
past questions                 of repeated
 for context)                   questions)
        ↓
Groq (Llama 3.3-70B) — or Gemini as fallback —
translates your question into SQL
        ↓
DuckDB / TimescaleDB   (the actual ocean data)
        ↓
Results flow back as a table + Plotly chart
```

If the AI writes SQL with a mistake, the system catches the database error, feeds it back to the AI, and lets it retry automatically — you never see the failure.

If someone tries to ask the system to delete or modify data (accidentally or on purpose), a safety layer blocks it before it ever reaches the database.

---

## Where the data actually comes from

This is not synthetic or made-up data. The ETL pipeline (`src/etl/fetch_argo.py`) downloads real profile files directly from the **Ifremer Global Data Assembly Centre (GDAC)** — the official public archive that mirrors ARGO float data from every country operating floats.

For each float, the pipeline:
1. Downloads its `[WMO_ID]_prof.nc` file from Ifremer (trying India's, the US's, and France's data centers in turn, since floats are archived under whichever agency owns them).
2. Opens it with `xarray` and extracts temperature, salinity, pressure, position, and date for every dive.
3. Cleans and loads the readings into the database.
4. Deletes the raw file (it's no longer needed once parsed) — but first records a permanent proof-of-download entry (see below).

**Currently ingested:** 6 real ARGO floats, 14,987 individual sensor readings, spanning the Arabian Sea, Bay of Bengal, and Equatorial Indian Ocean.

### Proof it's real: the provenance log

Every successful (or failed) download is permanently logged to `data/ingestion_log.jsonl` — a tamper-evident record containing the source URL, timestamp, record count, and a SHA-256 checksum of the exact file that was downloaded. Run this to see it:

```bash
python -m src.etl.show_provenance
```

```
WMO ID     | DAC        | Status   | Records  | Timestamp                   | SHA256 (First 12)
2902264    | incois     | success  | 4200     | 2026-07-12T11:07:21.692473Z | a2ab83fe30ba
2902265    | incois     | success  | 672      | 2026-07-12T11:07:26.163559Z | 2c5538c68755
2902266    | incois     | success  | 675      | 2026-07-12T11:07:28.728309Z | 350a6499314a
5904663    | aoml       | success  | 4488     | 2026-07-12T11:07:32.682937Z | 50e6e714449f
5904664    | aoml       | success  | 4498     | 2026-07-12T11:07:38.507437Z | 3790b1601da1
6900186    | coriolis   | success  | 454      | 2026-07-12T11:07:40.976119Z | 4d6a6cccc90a
```

If the network is unavailable when the ETL runs, it falls back to generating oceanographically realistic synthetic data instead of failing outright — so the app is always demo-ready.

---

## Key features

| Feature | What it does |
|---|---|
| **Text-to-SQL translation** | Converts natural-language questions into safe, correct SQL using Groq's Llama-3.3-70B, with Gemini as an automatic fallback if Groq is unavailable. |
| **Few-shot retrieval (RAG)** | ChromaDB stores past question-to-SQL examples and pulls the most similar ones into the prompt, improving accuracy on new questions. |
| **Self-correction loop** | If the generated SQL has an error, the database's error message is fed back to the AI, which fixes and retries automatically. |
| **Two-layer SQL safety guard** | Only read-only `SELECT` statements are allowed. Destructive keywords (`DROP`, `DELETE`, `ATTACH`, `PRAGMA`, etc.) and cross-table data exfiltration attempts are blocked before execution — this has been adversarially security-tested. |
| **Redis caching** | Repeated or common questions return instantly instead of re-querying the AI, with automatic fallback to a local cache if Redis is offline. |
| **Interactive visualizations** | Vertical depth profiles (Plotly) and geographic float locations (Folium maps) render automatically based on the kind of question asked. |
| **API authentication & rate limiting** | The backend requires an API key and rate-limits requests per IP to prevent abuse. |
| **Dual database support** | Runs on DuckDB locally for fast, zero-setup development, or PostgreSQL + TimescaleDB in Docker for a production-style deployment. |
| **Automated testing & CI** | A pytest suite and a 50-question text-to-SQL evaluation harness run automatically via GitHub Actions on every push. |
| **Ingestion provenance logging** | Every real data download is permanently and verifiably logged (see above) — proof the data isn't synthetic. |

---

## Repository structure

```
├── data/
│   ├── argo_data.db          # DuckDB database — the actual ocean sensor readings
│   ├── ingestion_log.jsonl   # Proof-of-download log for every real NetCDF file fetched
│   └── chroma_db/            # ChromaDB vector store (few-shot examples for the AI)
├── frontend/
│   └── app.py                 # Streamlit chat dashboard
├── src/
│   ├── ai/
│   │   ├── sql_agent.py       # Core AI logic: prompt building, safety checks, retries
│   │   ├── vector_store.py    # ChromaDB wrapper for few-shot example retrieval
│   │   ├── cache.py           # Redis caching layer with local fallback
│   │   ├── prompts.py         # System prompts fed to the LLM
│   │   ├── eval_harness.py    # Automated accuracy grading against 50 test questions
│   │   └── eval_dataset.json  # The 50 question/answer pairs used for grading
│   ├── backend/
│   │   └── main.py            # FastAPI server — auth, rate limiting, the /ask endpoint
│   ├── database/
│   │   └── db_client.py       # Unified DuckDB / TimescaleDB connection layer
│   └── etl/
│       ├── fetch_argo.py      # Downloads and parses real ARGO NetCDF files
│       ├── provenance.py      # Writes the tamper-evident ingestion log
│       └── show_provenance.py # CLI tool to view the ingestion log as a table
├── tests/                     # pytest suite (safety checks, API auth, data cleaning)
├── .github/workflows/ci.yml   # Runs lint + tests automatically on every push
├── Dockerfile / Dockerfile.frontend / docker-compose.yml
├── requirements.txt
└── .env                       # Your local API keys (never commit this — see below)
```

---

## Getting started

### 1. Prerequisites

- Python 3.10 or newer
- A free [Groq API key](https://console.groq.com) (and optionally a Gemini key as backup)

### 2. Install dependencies

```bash
git clone https://github.com/rishikeshyadavv/SIH26.git
cd SIH26
pip install -r requirements.txt
```

### 3. Set up your environment variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
DB_TYPE=duckdb
DB_PATH=data/argo_data.db
FLOAT_API_KEY=choose_your_own_backend_api_key
REDIS_URL=redis://localhost:6379
```

**Never commit this file.** It's already listed in `.gitignore` — double check with `git status` before your first push.

### 4. Pull real ocean data

```bash
python -m src.etl.fetch_argo
```

This downloads and parses live NetCDF files from Ifremer's GDAC. It typically takes 1–2 minutes and ends with something like:

```
Ingesting 14987 rows of REAL oceanographic data...
ETL Complete. Total rows in floats database: 14987
```

### 5. Start the backend

```bash
uvicorn src.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### 6. Start the frontend

In a separate terminal:

```bash
streamlit run frontend/app.py
```

Then open **http://localhost:8501** in your browser.

### Alternative: run everything with Docker

```bash
docker-compose up --build
```

This spins up the backend, frontend, TimescaleDB, and Redis together — no manual setup required.

---

## Try these questions

Once the app is running, try asking:

- *"Show me the temperature profile of float 2902264"* → depth-vs-temperature chart
- *"What's the salinity in the Arabian Sea in January 2023?"* → map view with markers
- *"Compare salinity in the Arabian Sea vs Bay of Bengal"* → comparison chart
- *"Find nearest ARGO floats to lat 12, lon 65"* → distance-based lookup
- *"Delete all data from the database"* → watch the safety guard block it

---

## Running the test suite

```bash
pytest
```

To grade the AI's text-to-SQL accuracy against 50 hand-written questions:

```bash
python -m src.ai.eval_harness
```

Latest results: **82% execution-match accuracy**, ~2 second average response time.

---

## Security notes

This project has been through an adversarial security audit covering authentication bypass, SQL injection, prompt injection, input fuzzing, and dependency CVE checks. Key protections currently in place:

- API key required on all data-returning endpoints
- Per-IP rate limiting
- SQL safety guard blocking destructive statements and restricted-table access
- No hardcoded credentials or default fallback keys
- Non-root Docker containers with health checks

If you're extending this project, rotate your API keys immediately if you ever suspect `.env` was exposed, and never commit it to git.

---

## Tech stack

**Backend:** FastAPI, slowapi (rate limiting), loguru (logging)
**AI:** Groq (Llama 3.3-70B), Gemini (fallback), ChromaDB (RAG), Redis (caching)
**Data:** DuckDB / PostgreSQL + TimescaleDB, xarray + netCDF4 (NetCDF parsing)
**Frontend:** Streamlit, Plotly, Folium
**Infra:** Docker, Docker Compose, GitHub Actions (CI)
**Testing:** pytest, ruff

---

## About

Built for Smart India Hackathon 2026 — Problem Statement SIH25040, Ministry of Earth Sciences.
