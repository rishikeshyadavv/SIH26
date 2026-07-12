from src.ai.sql_agent import is_safe_sql, clean_sql

def test_is_safe_sql():
    # Safe SELECT queries
    assert is_safe_sql("SELECT * FROM floats") is True
    assert is_safe_sql("SELECT float_id, lat, lon FROM floats WHERE depth = 0") is True
    assert is_safe_sql("WITH temp AS (SELECT * FROM floats) SELECT * FROM temp") is True
    
    # Destructive SQL statements should be blocked
    assert is_safe_sql("DROP TABLE floats") is False
    assert is_safe_sql("DELETE FROM floats WHERE float_id = '2902264'") is False
    assert is_safe_sql("UPDATE floats SET temperature = 30 WHERE id = 1") is False
    assert is_safe_sql("INSERT INTO floats VALUES (1, '2902264', 15.0, 65.0, '2023-01-01', 0, 25.0, 35.0, 'Arabian Sea')") is False
    assert is_safe_sql("ALTER TABLE floats ADD COLUMN test TEXT") is False
    
    # Must start with SELECT or WITH
    assert is_safe_sql("SHOW TABLES") is False

def test_clean_sql():
    assert clean_sql("```sql\nSELECT * FROM floats;\n```") == "SELECT * FROM floats"
    assert clean_sql("SELECT * FROM floats;   ") == "SELECT * FROM floats"
    assert clean_sql("SELECT * FROM floats -- some comment") == "SELECT * FROM floats"
