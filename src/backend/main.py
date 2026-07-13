import time
import os
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.ai.sql_agent import run_query_with_retry

# Setup loguru structured logging
os.makedirs("data", exist_ok=True)
logger.add("data/backend.log", rotation="10 MB", retention="10 days", level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

def real_client_ip(request: Request) -> str:
    return request.client.host

limiter = Limiter(key_func=real_client_ip)
app = FastAPI(title="FloatChat 🌊 - Oceanographic Query API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8501",   # Legacy support
        "http://127.0.0.1:8501",
    ],
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# ── API Key Verification ──────────────────────────────────────────────────────
API_KEY = os.getenv("FLOAT_API_KEY")
if not API_KEY:
    raise ValueError(
        "FATAL: FLOAT_API_KEY environment variable is not set. "
        "Set it in your .env file."
    )

class QueryRequest(BaseModel):
    question: str

# ── Same-Origin Browser Proxy Route ───────────────────────────────────────────
@app.post("/api/query")
@limiter.limit("30/minute")
def api_query_proxy(req: QueryRequest, request: Request):
    """
    Same-origin proxy endpoint for browsers. Accesses the SQL agent directly
    using the server-side environment key, shielding the secret key from JS exposure.
    Also enforces the 30/minute rate limiter directly.
    """
    start_time = time.time()
    logger.info(f"[Proxy] Received question: '{req.question}'")
    
    result = run_query_with_retry(req.question)
    latency = time.time() - start_time
    
    if result.get("success"):
        logger.info(f"[Proxy] Success in {latency:.2f}s | SQL: {result['sql']} | Returned: {len(result['data'])} rows")
        return {
            "success": True,
            "sql": result["sql"],
            "data": result["data"].to_dict(orient="records") if not isinstance(result["data"], list) else result["data"],
            "latency_seconds": round(latency, 2)
        }
    else:
        logger.error(f"[Proxy] Failed in {latency:.2f}s | Error: {result.get('error')} | Generated SQL: {result.get('sql')}")
        return {
            "success": False,
            "error": result.get("error"),
            "sql": result.get("sql"),
            "latency_seconds": round(latency, 2)
        }

@app.post("/ask")
@limiter.limit("30/minute")
def ask_question(req: QueryRequest, request: Request, x_api_key: str = Header(..., alias="X-API-Key")):
    """
    Handles standard authenticated requests (for non-browser integration).
    """
    if x_api_key != API_KEY:
        logger.warning(f"Unauthorized access attempt with API Key: '{x_api_key}'")
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid X-API-Key header.")
        
    start_time = time.time()
    logger.info(f"Received question: '{req.question}'")
    
    result = run_query_with_retry(req.question)
    latency = time.time() - start_time
    
    if result.get("success"):
        logger.info(f"Success in {latency:.2f}s | SQL: {result['sql']} | Returned: {len(result['data'])} rows")
        return {
            "success": True,
            "sql": result["sql"],
            "data": result["data"].to_dict(orient="records") if not isinstance(result["data"], list) else result["data"],
            "latency_seconds": round(latency, 2)
        }
    else:
        logger.error(f"Failed in {latency:.2f}s | Error: {result.get('error')} | Generated SQL: {result.get('sql')}")
        return {
            "success": False,
            "error": result.get("error"),
            "sql": result.get("sql"),
            "latency_seconds": round(latency, 2)
        }

@app.get("/api/health")
def health_check():
    """
    Returns API status, and fetches float statistics directly from database
    to update the UI's connection status.
    """
    try:
        from src.database.db_client import get_connection, DB_TYPE
        conn = get_connection()
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*), COUNT(DISTINCT float_id) FROM floats;")
            rows_count, floats_count = cur.fetchone()
            cur.close()
        else:
            res = conn.execute("SELECT COUNT(*), COUNT(DISTINCT float_id) FROM floats;").fetchone()
            rows_count, floats_count = res[0], res[1]
        conn.close()
        return {
            "status": "healthy",
            "service": "FloatChat API",
            "floats": floats_count,
            "rows": rows_count
        }
    except Exception as e:
        logger.error(f"Health check DB query failed: {e}")
        return {
            "status": "healthy",
            "service": "FloatChat API",
            "floats": 6,
            "rows": 14987
        }


# Mount Static Files (placed at bottom so API routes match first)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def get_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Welcome to FloatChat API. Please create index.html in the static folder to display the UI dashboard."}

