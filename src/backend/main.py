import time
import os
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.ai.sql_agent import run_query_with_retry

# Setup loguru structured logging
os.makedirs("data", exist_ok=True)
logger.add("data/backend.log", rotation="10 MB", retention="10 days", level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

# ── FIX C1: Use socket-level IP, NOT X-Forwarded-For ─────────────────────────
# slowapi's get_remote_address trusts X-Forwarded-For which any client can spoof.
# request.client.host is the actual TCP socket peer address — unforgeable by client.
# If deployed behind a trusted reverse proxy (nginx/Caddy), configure the proxy to
# set a signed/validated forwarded header and update this logic accordingly.
def real_client_ip(request: Request) -> str:
    return request.client.host

limiter = Limiter(key_func=real_client_ip)
app = FastAPI(title="FloatChat 🌊 - Oceanographic Query API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── FIX C5: Explicit CORS origins — no wildcard ───────────────────────────────
# allow_origins=["*"] + allow_credentials=True is contradictory per spec and
# signals a misconfiguration. Use an explicit allowlist. Expand for production domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",   # Streamlit frontend (local)
        "http://127.0.0.1:8501",  # Streamlit frontend (alternative local)
        # "https://yourdomain.com",  # Add production domain here
    ],
    allow_credentials=False,  # No cookie-based auth; custom header used instead
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# ── FIX C3/hardcoded key: fail loudly if env var missing ─────────────────────
API_KEY = os.getenv("FLOAT_API_KEY")
if not API_KEY:
    raise ValueError(
        "FATAL: FLOAT_API_KEY environment variable is not set. "
        "Set it in your .env file. Do not use a hardcoded default."
    )

class QueryRequest(BaseModel):
    question: str

@app.post("/ask")
@limiter.limit("30/minute")
def ask_question(req: QueryRequest, request: Request, x_api_key: str = Header(..., alias="X-API-Key")):
    """
    Handles natural language queries:
    1. Authenticates request using X-API-Key header.
    2. Rate limits to 30 requests per minute per IP.
    3. Invokes text-to-SQL execution engine.
    """
    # 1. API Key Auth
    if x_api_key != API_KEY:
        logger.warning(f"Unauthorized access attempt with API Key: '{x_api_key}'")
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid X-API-Key header.")
        
    start_time = time.time()
    logger.info(f"Received question: '{req.question}'")
    
    # Process query
    result = run_query_with_retry(req.question)
    latency = time.time() - start_time
    
    if result.get("success"):
        logger.info(f"Success in {latency:.2f}s | SQL: {result['sql']} | Returned: {len(result['data'])} rows")
        return {
            "success": True,
            "sql": result["sql"],
            "data": result["data"].to_dict(orient="records"),
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

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "FloatChat API"}
