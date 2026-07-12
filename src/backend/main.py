import time
import logging
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.ai.sql_agent import run_query_with_retry

# Create data directory for logs
os.makedirs("data", exist_ok=True)

# Configure logging to both file and console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("data/backend.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("FloatChatBackend")

app = FastAPI(title="FloatChat 🌊 - Oceanographic Query API")

# Enable CORS for frontend connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    question: str

@app.post("/ask")
def ask_question(req: QueryRequest):
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
