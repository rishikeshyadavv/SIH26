import os
import re
import time
import pandas as pd
from dotenv import load_dotenv
from groq import Groq
import google.generativeai as genai
from loguru import logger

from src.ai.prompts import build_system_prompt
from src.ai.vector_store import get_db_schema, get_few_shot_examples
from src.ai.cache import get_cached_query, set_cached_query
from src.database.db_client import get_connection, execute_query, insert_dataframe

load_dotenv()

# Setup loguru structured logging
os.makedirs("data", exist_ok=True)
logger.add("data/backend.log", rotation="10 MB", retention="10 days", level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

# Setup API keys and check configurations
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Initialize Groq client if key is provided
groq_client = None
if GROQ_API_KEY and GROQ_API_KEY != "your_groq_key_here":
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
        logger.info("Groq client initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing Groq client: {e}")

# Initialize Gemini client if key is provided
gemini_configured = False
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_key_here":
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_configured = True
        logger.info("Gemini client initialized successfully.")
    except Exception as e:
        logger.error(f"Error configuring Gemini client: {e}")

# Safety settings: blocked keywords to prevent destructive commands
BLOCKED_KEYWORDS = [
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "REPLACE", "TRUNCATE",
    # DuckDB-specific dangerous operations
    "ATTACH", "DETACH", "COPY", "EXPORT", "IMPORT", "PRAGMA", "EXEC", "EXECUTE",
]

# Tables that must never be accessible via generated SQL
# query_logs is in the same DB as floats; UNION SELECT can exfiltrate it.
RESTRICTED_TABLES = [
    "query_logs",
    "information_schema",
    "sqlite_master",
    "sqlite_temp_master",
    "duckdb_tables",
    "duckdb_columns",
    "duckdb_schemas",
    "pg_catalog",
    "pg_tables",
]

def is_safe_sql(sql: str) -> bool:
    """Verifies that the generated SQL query is a read-only SELECT against allowed tables.

    Two-layer defence:
    1. Blocklist of destructive/dangerous SQL keywords.
    2. Allowlist check: query must not reference internal/metadata tables, even
       inside UNION branches (which the keyword blocklist would miss).
    """
    upper = sql.upper().strip()
    # Layer 1: destructive keyword blocklist
    if any(kw in upper for kw in BLOCKED_KEYWORDS):
        return False
    # Must start with SELECT or WITH (no bare UPDATE/INSERT/etc.)
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return False
    # Layer 2: restricted table blocklist (catches UNION-based exfiltration)
    # Strip whitespace/newlines to catch multiline injections
    normalized = " ".join(upper.split())
    if any(tbl.upper() in normalized for tbl in RESTRICTED_TABLES):
        logger.warning(f"Blocked SQL accessing restricted table: {sql[:200]}")
        return False
    return True

def clean_sql(sql_str: str) -> str:
    """Cleans markdown symbols and whitespace from generated SQL."""
    # Remove markdown code blocks
    sql_str = re.sub(r"```sql|```", "", sql_str)
    # Remove trailing semicolons
    sql_str = sql_str.split(";")[0]
    # Remove trailing -- comments
    sql_str = sql_str.split("--")[0]
    return sql_str.strip()

def log_query_to_db(question: str, generated_sql: str, success: bool, error: str, latency: float, model: str, is_cached: bool, retries: int):
    """Saves structured query execution metadata to the query_logs DB table."""
    try:
        log_df = pd.DataFrame([{
            "question": question,
            "generated_sql": generated_sql,
            "success": success,
            "error": error if error else "",
            "latency_seconds": round(latency, 2),
            "model_used": model,
            "is_cached": is_cached,
            "retry_attempts": retries
        }])
        insert_dataframe(log_df, "query_logs")
    except Exception as e:
        logger.error(f"Failed to write query log to DB: {e}")

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
    """Sends a completion request to Gemini (Gemini 1.5/2.5 Flash)."""
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

def ask_llm(prompt: str, system_prompt: str, model_record: list) -> str:
    """Tries Groq first, and falls back to Gemini if Groq fails. Records used model."""
    last_err = None
    
    # Try Groq
    if groq_client:
        try:
            model_record[0] = "groq-llama-3.3-70b"
            return call_llm_groq(prompt, system_prompt)
        except Exception as e:
            last_err = e
            logger.warning(f"Groq API call failed: {e}. Trying Gemini fallback...")
            
    # Try Gemini Fallback
    if gemini_configured:
        try:
            model_record[0] = "gemini-1.5-flash"
            return call_llm_gemini(prompt, system_prompt)
        except Exception as e:
            last_err = e
            logger.error(f"Gemini API call failed: {e}")
            
    if last_err:
        raise last_err
    else:
        raise ValueError("No LLM API keys provided or configured. Set GROQ_API_KEY or GEMINI_API_KEY in .env.")

def run_query_with_retry(question: str):
    """
    Translates a natural language question to SQL, runs it against the database,
    and performs a self-correction retry if the query fails.
    Uses vector few-shot prompt generation and caching.
    """
    start_time = time.time()
    
    # Try cache hit first
    cached_res = get_cached_query(question)
    if cached_res:
        log_query_to_db(question, cached_res["sql"], True, None, 0.0, "cache", True, 0)
        return cached_res

    # Build dynamic prompt with RAG context
    schema = get_db_schema()
    few_shots = get_few_shot_examples(question, k=3)
    system_prompt = build_system_prompt(schema, few_shots)
    
    model_used = ["unknown"]
    sql = "No SQL generated"
    retries = 0
    
    try:
        # Step 1: Generate SQL
        sql = ask_llm(question, system_prompt, model_used)
        sql = clean_sql(sql)
        
        # Step 2: Validate SQL Safety
        if not is_safe_sql(sql):
            err_msg = "Security Block: The generated query contains unsafe or non-SELECT operations."
            logger.warning(f"Unsafe SQL generated: '{sql}' for question: '{question}'")
            log_query_to_db(question, sql, False, err_msg, time.time() - start_time, model_used[0], False, 0)
            return {
                "success": False,
                "error": err_msg,
                "sql": sql
            }
            
        # Step 3: Run against DB
        try:
            df = execute_query(sql)
            latency = time.time() - start_time
            # Cache the successful query
            set_cached_query(question, sql, df)
            log_query_to_db(question, sql, True, None, latency, model_used[0], False, 0)
            return {
                "success": True,
                "sql": sql,
                "data": df
            }
        except Exception as db_err:
            logger.warning(f"First-attempt SQL execution failed for '{sql}': {db_err}. Retrying self-correction...")
            retries = 1
            
            # Step 4: Self-Correction Loop (1-retry)
            retry_prompt = f"""
            The user asked: "{question}"
            Your previously generated SQL query was:
            {sql}

            Running this query returned the following database execution error:
            {db_err}

            Please fix the query. Ensure the columns and tables match the schema perfectly:
            - Table: floats
            - Columns: float_id, lat, lon, date, depth, temperature, salinity, region
            - Keep it read-only SELECT.
            
            Return ONLY the corrected raw SQL query. No markdown, no explanations.
            """
            
            corrected_sql = ask_llm(retry_prompt, system_prompt, model_used)
            corrected_sql = clean_sql(corrected_sql)
            
            if not is_safe_sql(corrected_sql):
                err_msg = "Security Block: Corrected query contains unsafe or non-SELECT operations."
                log_query_to_db(question, corrected_sql, False, err_msg, time.time() - start_time, model_used[0], False, 1)
                return {
                    "success": False,
                    "error": err_msg,
                    "sql": corrected_sql
                }
                
            df = execute_query(corrected_sql)
            latency = time.time() - start_time
            set_cached_query(question, corrected_sql, df)
            log_query_to_db(question, corrected_sql, True, None, latency, model_used[0], False, 1)
            return {
                "success": True,
                "sql": corrected_sql,
                "data": df
            }
            
    except Exception as final_err:
        latency = time.time() - start_time
        err_msg = str(final_err)
        logger.error(f"SQL Agent failed for '{question}': {err_msg}")
        log_query_to_db(question, sql, False, err_msg, latency, model_used[0], False, retries)
        return {
            "success": False,
            "error": f"AI Processing/SQL Execution Error: {err_msg}",
            "sql": sql
        }
