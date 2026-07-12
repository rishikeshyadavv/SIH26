import os
import re
import sqlite3
import pandas as pd
from dotenv import load_dotenv
from groq import Groq
import google.generativeai as genai
from src.ai.prompts import SYSTEM_PROMPT
from src.database.sqlite_client import get_connection

load_dotenv()

# Setup API keys and check configurations
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Initialize Groq client if key is provided
groq_client = None
if GROQ_API_KEY and GROQ_API_KEY != "your_groq_key_here":
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
        print("Groq client initialized.")
    except Exception as e:
        print(f"Error initializing Groq client: {e}")

# Initialize Gemini client if key is provided
gemini_configured = False
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_key_here":
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_configured = True
        print("Gemini client initialized.")
    except Exception as e:
        print(f"Error configuring Gemini client: {e}")

# Safety settings: blocked keywords to prevent destructive commands
BLOCKED_KEYWORDS = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "REPLACE", "TRUNCATE", "--", ";"]

def is_safe_sql(sql: str) -> bool:
    """Verifies that the generated SQL query is a read-only SELECT statement."""
    upper = sql.upper().strip()
    # Basic keyword validation
    if any(kw in upper for kw in BLOCKED_KEYWORDS):
        return False
    # Must start with SELECT or WITH
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return False
    return True

def clean_sql(sql_str: str) -> str:
    """Cleans markdown symbols and whitespace from generated SQL."""
    # Remove markdown code blocks if the model ignored prompt instructions
    sql_str = re.sub(r"```sql|```", "", sql_str)
    # Remove trailing semicolons or comments
    sql_str = sql_str.split(";")[0]
    return sql_str.strip()

def call_llm_groq(prompt: str, system_prompt: str) -> str:
    """Sends a completion request to Groq (Llama 3.3)."""
    if not groq_client:
        raise ValueError("Groq client not configured or key is placeholder.")
    
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        max_tokens=250
    )
    return response.choices[0].message.content.strip()

def call_llm_gemini(prompt: str, system_prompt: str) -> str:
    """Sends a completion request to Gemini (Gemini 2.5 Flash / Pro)."""
    if not gemini_configured:
        raise ValueError("Gemini client not configured or key is placeholder.")
    
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=system_prompt
    )
    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0.0, "max_output_tokens": 250}
    )
    return response.text.strip()

def ask_llm(prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    """Tries Groq first, and falls back to Gemini if Groq is unavailable, rate-limited, or fails."""
    last_err = None
    
    # Try Groq
    if groq_client:
        try:
            return call_llm_groq(prompt, system_prompt)
        except Exception as e:
            last_err = e
            print(f"Groq API call failed: {e}. Trying Gemini fallback...")
            
    # Try Gemini Fallback
    if gemini_configured:
        try:
            return call_llm_gemini(prompt, system_prompt)
        except Exception as e:
            last_err = e
            print(f"Gemini API call failed: {e}")
            
    if last_err:
        raise last_err
    else:
        raise ValueError("No LLM API keys provided or configured. Set GROQ_API_KEY or GEMINI_API_KEY in .env.")

def run_query_with_retry(question: str):
    """
    Translates a natural language question to SQL, runs it against SQLite, 
    and performs a self-correction retry if the query fails.
    Uses a static demo cache for instant hits and fallback on API errors.
    """
    import json
    
    # Normalize question
    norm_question = question.strip().lower().rstrip("?")
    cache_path = os.path.join(os.path.dirname(__file__), "demo_cache.json")
    
    # Try exact cache hit first (instant & zero API cost)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                raw_cache = json.load(f)
            # Create normalized cache map
            cache = {k.strip().lower().rstrip("?"): v for k, v in raw_cache.items()}
            if norm_question in cache:
                print(f"[CACHE HIT] Serving exact cached query for: '{norm_question}'")
                cached_res = cache[norm_question]
                return {
                    "success": True,
                    "sql": cached_res["sql"],
                    "data": pd.DataFrame(cached_res["data"]),
                    "cached": True
                }
        except Exception as e:
            print(f"Error loading demo cache: {e}")

    try:
        # Step 1: Generate SQL
        sql = ask_llm(question)
        sql = clean_sql(sql)
        
        # Step 2: Validate SQL Safety
        if not is_safe_sql(sql):
            return {
                "success": False,
                "error": "Security Block: The generated query contains unsafe or non-SELECT operations.",
                "sql": sql
            }
            
        # Step 3: Run against DB
        conn = get_connection()
        try:
            df = pd.read_sql_query(sql, conn)
            conn.close()
            return {
                "success": True,
                "sql": sql,
                "data": df
            }
        except sqlite3.Error as db_err:
            conn.close()
            print(f"First-attempt SQL execution failed: {db_err}. Retrying self-correction...")
            
            # Step 4: Self-Correction Loop (1-retry)
            retry_prompt = f"""
            The user asked: "{question}"
            Your previously generated SQL query was:
            {sql}

            Running this query against SQLite returned the following error:
            {db_err}

            Please fix the query. Ensure the columns and tables match the schema perfectly:
            - Table: floats
            - Columns: float_id, lat, lon, date, depth, temperature, salinity, region
            - Keep it read-only SELECT.
            
            Return ONLY the corrected raw SQL query. No markdown, no explanations.
            """
            
            try:
                corrected_sql = ask_llm(retry_prompt)
                corrected_sql = clean_sql(corrected_sql)
                
                if not is_safe_sql(corrected_sql):
                    return {
                        "success": False,
                        "error": "Security Block: Corrected query contains unsafe or non-SELECT operations.",
                        "sql": corrected_sql
                    }
                    
                conn = get_connection()
                df = pd.read_sql_query(corrected_sql, conn)
                conn.close()
                return {
                    "success": True,
                    "sql": corrected_sql,
                    "data": df
                }
            except Exception as retry_err:
                if 'conn' in locals() and conn:
                    conn.close()
                return {
                    "success": False,
                    "error": f"SQL Execution Error after self-correction: {retry_err}",
                    "sql": corrected_sql if 'corrected_sql' in locals() else sql
                }
                
    except Exception as e:
        # Fallback to fuzzy match on cache if API fails
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                for cached_q, cached_res in cache.items():
                    if cached_q in norm_question or norm_question in cached_q:
                        print(f"[FUZZY CACHE HIT] Serving fallback cached query for: '{norm_question}' (matched: '{cached_q}')")
                        return {
                            "success": True,
                            "sql": cached_res["sql"],
                            "data": pd.DataFrame(cached_res["data"]),
                            "cached": True,
                            "fuzzy": True
                        }
            except Exception as cache_err:
                print(f"Error checking fuzzy cache fallback: {cache_err}")
                
        return {
            "success": False,
            "error": f"AI Processing Error: {str(e)}",
            "sql": "No SQL generated"
        }

