import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DB_TYPE = os.getenv("DB_TYPE", "duckdb").lower()
DB_PATH = os.getenv("DB_PATH", "data/argo_data.db")

# Postgres config
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_DB = os.getenv("POSTGRES_DB", "floats_db")
PG_USER = os.getenv("POSTGRES_USER", "postgres")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

def get_connection():
    if DB_TYPE == "postgres":
        import psycopg2
        return psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            dbname=PG_DB,
            user=PG_USER,
            password=PG_PASSWORD
        )
    else:
        # Default to duckdb
        import duckdb
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        return duckdb.connect(DB_PATH)

def init_db():
    conn = get_connection()
    
    if DB_TYPE == "postgres":
        cur = conn.cursor()
        
        # Try to create TimescaleDB extension if available
        try:
            cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
            conn.commit()
            print("TimescaleDB extension verified/enabled.")
        except Exception as e:
            conn.rollback()
            print(f"TimescaleDB extension not available, falling back to standard PostgreSQL: {e}")
            
        # Create floats table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS floats (
                id SERIAL,
                float_id VARCHAR(50),
                lat DOUBLE PRECISION,
                lon DOUBLE PRECISION,
                date DATE,
                depth DOUBLE PRECISION,
                temperature DOUBLE PRECISION,
                salinity DOUBLE PRECISION,
                region VARCHAR(50),
                PRIMARY KEY (id, date)
            );
        """)
        
        # Create hypertable (requires table to have date partition column in PK)
        try:
            cur.execute("SELECT create_hypertable('floats', 'date', if_not_exists => TRUE);")
            conn.commit()
            print("TimescaleDB hypertable initialized.")
        except Exception as e:
            conn.rollback()
            print(f"Hypertable creation bypassed (or already exists/not TimescaleDB): {e}")
            
        # Create indexes for standard PostgreSQL optimization
        cur.execute("CREATE INDEX IF NOT EXISTS idx_float_id ON floats(float_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_region ON floats(region);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_date ON floats(date);")
        
        # Create query_logs table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS query_logs (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                question TEXT,
                generated_sql TEXT,
                success BOOLEAN,
                error TEXT,
                latency_seconds REAL,
                model_used VARCHAR(100),
                is_cached BOOLEAN,
                retry_attempts INTEGER
            );
        """)
        
        conn.commit()
        cur.close()
        
    else:
        # DuckDB
        # Floats table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS floats (
                float_id VARCHAR,
                lat DOUBLE,
                lon DOUBLE,
                date VARCHAR, -- format: YYYY-MM-DD
                depth DOUBLE,
                temperature DOUBLE,
                salinity DOUBLE,
                region VARCHAR
            );
        """)
        
        # DuckDB handles indexes automatically for columns, but we can create them if needed.
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_float_id ON floats(float_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_region ON floats(region);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON floats(date);")
        except Exception as e:
            print(f"Index creation bypassed in DuckDB: {e}")
            
        # Create query_logs table
        conn.execute("CREATE SEQUENCE IF NOT EXISTS seq_query_logs;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_logs (
                id INTEGER DEFAULT nextval('seq_query_logs') PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                question VARCHAR,
                generated_sql VARCHAR,
                success BOOLEAN,
                error VARCHAR,
                latency_seconds REAL,
                model_used VARCHAR,
                is_cached BOOLEAN,
                retry_attempts INTEGER
            );
        """)
        
    conn.close()
    print(f"Database ({DB_TYPE.upper()}) initialized successfully.")

def execute_query(sql, conn=None):
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True
        
    try:
        if DB_TYPE == "postgres":
            # For Postgres, use pandas read_sql
            df = pd.read_sql_query(sql, conn)
        else:
            # For DuckDB, fetchdf() is native and fast
            df = conn.execute(sql).fetchdf()
        return df
    finally:
        if should_close:
            conn.close()

def insert_dataframe(df, table_name, conn=None):
    if df.empty:
        return
        
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True
        
    try:
        if DB_TYPE == "postgres":
            from sqlalchemy import create_engine
            engine_url = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
            engine = create_engine(engine_url)
            df.to_sql(table_name, engine, if_exists="append", index=False)
        else:
            # DuckDB: Register and insert local dataframe fast
            cols = ", ".join(df.columns)
            conn.register("df_temp", df)
            conn.execute(f"INSERT INTO {table_name} ({cols}) SELECT * FROM df_temp")
            conn.unregister("df_temp")
    finally:
        if should_close:
            conn.close()

if __name__ == "__main__":
    init_db()
