import json
import os
from src.ai.sql_agent import run_query_with_retry

CACHE_QUESTIONS = [
    "show me the temperature profile of float 2902264",
    "what's the salinity in the Arabian sea in january 2023?",
    "compare salinity in the arabian sea vs bay of bengal"
]

def generate_cache():
    print("Generating demo fallback cache...")
    cache = {}
    
    for q in CACHE_QUESTIONS:
        print(f"Querying: '{q}'")
        res = run_query_with_retry(q)
        if res.get("success"):
            # Convert pandas DataFrame to list of dicts for JSON serialization
            records = res["data"].to_dict(orient="records")
            cache[q] = {
                "success": True,
                "sql": res["sql"],
                "data": records
            }
            print(f"  Cached successfully ({len(records)} records).")
        else:
            print(f"  [ERROR] Failed to query: {res.get('error')}")
            
    cache_path = os.path.join("src", "ai", "demo_cache.json")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
        
    print(f"Cache saved to {cache_path}")

if __name__ == "__main__":
    generate_cache()
