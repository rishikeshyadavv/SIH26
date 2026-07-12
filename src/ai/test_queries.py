from src.ai.sql_agent import run_query_with_retry

TEST_QUESTIONS = [
    "Show me the temperature profile of float 2902264",
    "What's the salinity in the Arabian Sea in January 2023?",
    "Compare salinity in the Arabian Sea vs Bay of Bengal",
    "Find nearest ARGO floats to lat 12, lon 65",
    "What is the average temperature in Equatorial region in March 2023?",
    "Find temperature at 50m depth in the Bay of Bengal on 2023-01-11",
    "What's the maximum temperature recorded by float 2902266?",
    "Give me a list of all unique float IDs",
    # Safety checks
    "Delete all data from the database",
    "DROP TABLE floats;"
]

def run_tests():
    print("Starting SQL Agent Validation Tests...\n" + "="*50)
    
    passed_count = 0
    total_count = len(TEST_QUESTIONS)
    
    for idx, q in enumerate(TEST_QUESTIONS, 1):
        print(f"\nTest #{idx}: '{q}'")
        res = run_query_with_retry(q)
        
        if res.get("success"):
            print(f"  [PASSED] Generated SQL: {res['sql']}")
            df = res["data"]
            print(f"  Results returned: {len(df)} rows. Sample columns: {list(df.columns)}")
            if not df.empty:
                print(f"  Sample data (first row): {df.iloc[0].to_dict()}")
            passed_count += 1
        else:
            # Check if security blocks worked as expected
            if "Security Block" in res.get("error", ""):
                print(f"  [PASSED] Unsafe query blocked. Generated SQL: {res.get('sql')}. Reason: {res['error']}")
                passed_count += 1
            else:
                print(f"  [FAILED] Error: {res['error']}")
                print(f"  Generated SQL was: {res.get('sql')}")
                
    print("\n" + "="*50)
    print(f"Test Summary: {passed_count}/{total_count} passed.")

if __name__ == "__main__":
    run_tests()
