import json
import os
import pandas as pd
from src.database.db_client import execute_query

CACHE_MAP = {
    "show me the temperature profile of float 2902264": "SELECT depth, temperature FROM floats WHERE float_id = '2902264' ORDER BY depth LIMIT 500",
    "what's the salinity in the arabian sea in january 2023?": "SELECT float_id, lat, lon, date, depth, salinity FROM floats WHERE region = 'Arabian Sea' AND date BETWEEN '2023-01-01' AND '2023-01-31' LIMIT 500",
    "compare salinity in the arabian sea vs bay of bengal": "SELECT region, AVG(salinity) as avg_salinity FROM floats WHERE region IN ('Arabian Sea', 'Bay of Bengal') GROUP BY region",
    "find nearest argo floats to lat 12, lon 65": "SELECT float_id, lat, lon, region, (lat - 12.0)*(lat - 12.0) + (lon - 65.0)*(lon - 65.0) as distance_sq FROM floats ORDER BY distance_sq LIMIT 500"
}

def generate_cache():
    print("Generating demo fallback cache...")
    cache = {}
    
    # Load existing cache if exists to prevent overwriting other entries
    cache_path = os.path.join("src", "ai", "demo_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass

    for q, sql in CACHE_MAP.items():
        print(f"Caching SQL for: '{q}' -> '{sql}'")
        try:
            df = execute_query(sql)
            records = df.to_dict(orient="records")
            cache[q] = {
                "success": True,
                "sql": sql,
                "data": records
            }
            print(f"  Cached successfully ({len(records)} records).")
        except Exception as e:
            print(f"  [ERROR] Failed to query database: {e}")
            
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
        
    print(f"Cache saved to {cache_path}")

if __name__ == "__main__":
    generate_cache()

