import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "data/argo_data.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    
    # Create the floats table with columns matching the schema
    cur.execute("""
        CREATE TABLE IF NOT EXISTS floats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            float_id TEXT,
            lat REAL,
            lon REAL,
            date TEXT, -- YYYY-MM-DD
            depth REAL,
            temperature REAL,
            salinity REAL,
            region TEXT
        )
    """)
    
    # Create indexes for optimized queries (float_id, region, date)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_float_id ON floats(float_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_region ON floats(region);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_date ON floats(date);")
    
    conn.commit()
    conn.close()
    print("Database and indexes initialized successfully.")

if __name__ == "__main__":
    init_db()
