import os
import json
import time
import re
import pandas as pd
from src.ai.sql_agent import run_query_with_retry
from src.database.db_client import execute_query

def normalize_sql(sql: str) -> str:
    """Normalizes SQL syntax for basic exact match comparison."""
    if not sql:
        return ""
    # Lowercase, remove backticks, semicolons, extra spacing, and standardise quotes
    s = sql.lower().strip()
    s = s.replace("`", "").replace(";", "")
    s = s.replace("\"", "'")
    s = re.sub(r'\s+', ' ', s)
    # Standardize spaces around operators
    s = s.replace(" = ", "=").replace(" > ", ">").replace(" < ", "<")
    s = s.replace(" >= ", ">=").replace(" <= ", "<=")
    s = s.replace(" != ", "!=")
    # Standardize float representation (e.g. 12.0 to 12)
    s = re.sub(r'(\d+)\.0\b', r'\1', s)
    return s.strip()

def standardize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Standardizes a DataFrame for execution match comparisons."""
    if df is None or df.empty:
        return pd.DataFrame()
    
    df = df.copy()
    # Reset column names to standard range to ignore column header name differences
    df.columns = [str(i) for i in range(df.shape[1])]
    
    # Round all float values
    for col in df.columns:
        try:
            # Check if column is numeric
            df[col] = pd.to_numeric(df[col])
            df[col] = df[col].round(2)
        except Exception:
            pass
        
    # Convert all columns to string for sorting comparison
    for col in df.columns:
        df[col] = df[col].astype(str)
        
    # Sort rows by all columns
    df = df.sort_values(by=list(df.columns)).reset_index(drop=True)
    return df

def run_evaluation():
    os.environ["DISABLE_CACHE"] = "true"
    dataset_path = os.path.join(os.path.dirname(__file__), "eval_dataset.json")
    if not os.path.exists(dataset_path):
        print(f"Error: Dataset file not found at {dataset_path}")
        return
        
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    print(f"Starting Text-to-SQL Evaluation on {len(dataset)} queries...\n" + "="*70)
    
    em_count = 0
    ex_count = 0
    total = len(dataset)
    latencies = []
    
    failed_details = []
    
    for idx, item in enumerate(dataset, 1):
        question = item["question"]
        gold_sql = item["sql"]
        
        print(f"[{idx}/{total}] Question: '{question}'")
        
        start_t = time.time()
        agent_res = run_query_with_retry(question)
        elapsed = time.time() - start_t
        latencies.append(elapsed)
        
        generated_sql = agent_res.get("sql", "")
        success = agent_res.get("success", False)
        
        # 1. Exact Match Evaluation
        norm_gold = normalize_sql(gold_sql)
        norm_gen = normalize_sql(generated_sql)
        em = (norm_gold == norm_gen)
        if em:
            em_count += 1
            
        # 2. Execution Match Evaluation
        ex = False
        gold_df = None
        gen_df = None
        ex_error = None
        
        # Execute gold standard SQL
        try:
            gold_df = execute_query(gold_sql)
        except Exception as ge:
            print(f"  [Error running Gold SQL]: {ge}")
            
        # Compare results
        if success and gold_df is not None:
            gen_df = agent_res.get("data")
            if gen_df is not None:
                try:
                    std_gold = standardize_df(gold_df)
                    std_gen = standardize_df(gen_df)
                    if std_gold.equals(std_gen):
                        ex = True
                        ex_count += 1
                    else:
                        ex_error = "Results Mismatch (Dataframes differ)"
                except Exception as ce:
                    ex_error = f"Comparison Error: {ce}"
        else:
            ex_error = agent_res.get("error", "Agent returned failure status")
            
        print(f"  Generated SQL: {generated_sql}")
        print(f"  EM: {em} | EX: {ex} | Time: {elapsed:.2f}s")
        if not ex:
            print(f"  [EX FAIL REASON]: {ex_error}")
            failed_details.append({
                "idx": idx,
                "question": question,
                "gold_sql": gold_sql,
                "gen_sql": generated_sql,
                "error": ex_error
            })
        print("-" * 50)
        
    # Calculate stats
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    em_acc = (em_count / total) * 100
    ex_acc = (ex_count / total) * 100
    
    print("\n" + "="*70)
    print("EVALUATION SUMMARY")
    print("="*70)
    print(f"Total Queries Evaluated: {total}")
    print(f"Exact Match (EM) Accuracy:  {em_count}/{total} ({em_acc:.2f}%)")
    print(f"Execution Match (EX) Accuracy: {ex_count}/{total} ({ex_acc:.2f}%)")
    print(f"Average Latency:            {avg_latency:.2f} seconds")
    print("="*70)
    
    if failed_details:
        print(f"\nFailed Queries Log ({len(failed_details)} failures):")
        for f in failed_details:
            print(f"\n#{f['idx']} Question: {f['question']}")
            print(f"  Gold SQL: {f['gold_sql']}")
            print(f"  Gen SQL : {f['gen_sql']}")
            print(f"  Reason  : {f['error']}")
            
if __name__ == "__main__":
    run_evaluation()
