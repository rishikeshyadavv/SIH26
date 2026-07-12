import os
import json
import hashlib
import redis
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # Default 1 hour

# Global redis client variable
_redis_client = None
_redis_available = False

try:
    if REDIS_URL:
        _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        # Ping to check if connection actually works
        _redis_client.ping()
        _redis_available = True
        print(f"Connected to Redis cache at {REDIS_URL}")
except Exception as e:
    print(f"Redis is unavailable (falling back to memory cache): {e}")

# In-memory backup cache
_memory_cache = {}

# Path to static demo cache for bootstrapping / offline mode
DEMO_CACHE_PATH = os.path.join(os.path.dirname(__file__), "demo_cache.json")

def _normalize_question(question: str) -> str:
    return question.strip().lower().rstrip("?")

def get_cached_query(question: str):
    """
    Looks up a question in Redis cache, then memory cache, then falls back to demo_cache.json.
    Returns dict with "sql" and "data" (as a DataFrame) if hit, else None.
    """
    if os.getenv("DISABLE_CACHE") == "true":
        return None
        
    norm_q = _normalize_question(question)
    
    # 1. Try Redis cache
    if _redis_available and _redis_client:
        try:
            key_hash = hashlib.md5(norm_q.encode('utf-8')).hexdigest()
            redis_key = f"floatchat:cache:{key_hash}"
            cached_data = _redis_client.get(redis_key)
            if cached_data:
                res = json.loads(cached_data)
                print(f"[REDIS CACHE HIT] Serving query for: '{question}'")
                return {
                    "success": True,
                    "sql": res["sql"],
                    "data": pd.DataFrame(res["data"]),
                    "cached": True
                }
        except Exception as e:
            print(f"Redis cache read error: {e}")
            
    # 2. Try In-Memory cache
    if norm_q in _memory_cache:
        print(f"[MEMORY CACHE HIT] Serving query for: '{question}'")
        res = _memory_cache[norm_q]
        return {
            "success": True,
            "sql": res["sql"],
            "data": pd.DataFrame(res["data"]),
            "cached": True
        }
        
    # 3. Try demo_cache.json fallback (fuzzy match support)
    if os.path.exists(DEMO_CACHE_PATH):
        try:
            with open(DEMO_CACHE_PATH, "r", encoding="utf-8") as f:
                raw_cache = json.load(f)
            # Create a normalized lookup map
            cache_map = {k.strip().lower().rstrip("?"): v for k, v in raw_cache.items()}
            
            # Exact match in demo_cache
            if norm_q in cache_map:
                print(f"[DEMO CACHE HIT] Serving exact cached query for: '{question}'")
                res = cache_map[norm_q]
                return {
                    "success": True,
                    "sql": res["sql"],
                    "data": pd.DataFrame(res["data"]),
                    "cached": True,
                    "demo_cache": True
                }
                
            # Fuzzy match in demo_cache (if question matches or is contained)
            for k, v in cache_map.items():
                if k in norm_q or norm_q in k:
                    print(f"[FUZZY DEMO CACHE HIT] Serving fallback query for: '{question}' (matched: '{k}')")
                    return {
                        "success": True,
                        "sql": v["sql"],
                        "data": pd.DataFrame(v["data"]),
                        "cached": True,
                        "fuzzy": True,
                        "demo_cache": True
                    }
        except Exception as e:
            print(f"Error reading demo_cache.json: {e}")
            
    return None

def set_cached_query(question: str, sql: str, data_df: pd.DataFrame):
    """
    Stores a query and its results in Redis and In-Memory cache.
    """
    norm_q = _normalize_question(question)
    records = data_df.to_dict(orient="records")
    cache_payload = {
        "sql": sql,
        "data": records
    }
    
    # Store in Memory
    _memory_cache[norm_q] = cache_payload
    
    # Store in Redis
    if _redis_available and _redis_client:
        try:
            key_hash = hashlib.md5(norm_q.encode('utf-8')).hexdigest()
            redis_key = f"floatchat:cache:{key_hash}"
            _redis_client.setex(
                redis_key,
                CACHE_TTL,
                json.dumps(cache_payload)
            )
            print(f"[REDIS CACHE SET] Cached query for '{question}' (TTL: {CACHE_TTL}s)")
        except Exception as e:
            print(f"Redis cache write error: {e}")
