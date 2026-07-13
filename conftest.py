"""
Root conftest.py — automatically used by pytest for all test sessions.

Creates an in-memory DuckDB database seeded with sample ARGO float data and
patches `src.database.db_client.get_connection` to return it. This makes every
unit test and API test fully self-contained — no real argo_data.db needed.
"""
import os
import pytest
import duckdb
import pandas as pd
from unittest.mock import patch

# ── Ensure required env vars are present before any test imports ──────────────
os.environ.setdefault("FLOAT_API_KEY", "float_secret_key_2026")
os.environ.setdefault("DB_TYPE", "duckdb")
os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("DISABLE_CACHE", "true")

# ── Sample ARGO data that lives in memory during tests ────────────────────────
SAMPLE_FLOATS = [
    ("2902264", 12.5, 65.1, "2023-01-10", 0.0,  28.3, 35.1, "Arabian Sea"),
    ("2902264", 12.5, 65.1, "2023-01-10", 50.0, 26.1, 35.4, "Arabian Sea"),
    ("2902264", 12.5, 65.1, "2023-01-10", 100.0, 22.0, 35.6, "Arabian Sea"),
    ("2902264", 12.5, 65.1, "2023-01-10", 200.0, 18.5, 35.2, "Arabian Sea"),
    ("2902265", 13.1, 66.2, "2023-02-15", 0.0,  29.0, 34.8, "Arabian Sea"),
    ("2902265", 13.1, 66.2, "2023-02-15", 50.0, 25.5, 35.0, "Arabian Sea"),
    ("2902266", 14.2, 67.3, "2020-11-26", 0.0,  27.8, 34.9, "Arabian Sea"),
    ("2902266", 14.2, 67.3, "2020-11-26", 50.0, 24.2, 35.2, "Arabian Sea"),
    ("5904663", 8.0,  80.5, "2023-03-01", 0.0,  30.1, 34.5, "Bay of Bengal"),
    ("5904663", 8.0,  80.5, "2023-03-01", 50.0, 27.3, 34.8, "Bay of Bengal"),
    ("5904664", 7.5,  79.0, "2023-03-05", 0.0,  29.8, 34.6, "Bay of Bengal"),
    ("6900186", 0.5,  72.0, "2023-04-10", 0.0,  28.5, 35.0, "Equatorial Indian Ocean"),
]

SAMPLE_QUERY_LOGS: list[dict] = []


def _build_in_memory_db() -> duckdb.DuckDBPyConnection:
    """Creates and seeds a fresh in-memory DuckDB with the test schema."""
    conn = duckdb.connect(":memory:")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS floats (
            float_id VARCHAR,
            lat      DOUBLE,
            lon      DOUBLE,
            date     VARCHAR,
            depth    DOUBLE,
            temperature DOUBLE,
            salinity DOUBLE,
            region   VARCHAR
        )
    """)

    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS seq_query_logs;
        CREATE TABLE IF NOT EXISTS query_logs (
            id              INTEGER DEFAULT nextval('seq_query_logs') PRIMARY KEY,
            timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            question        VARCHAR,
            generated_sql   VARCHAR,
            success         BOOLEAN,
            error           VARCHAR,
            latency_seconds REAL,
            model_used      VARCHAR,
            is_cached       BOOLEAN,
            retry_attempts  INTEGER
        )
    """)

    df = pd.DataFrame(
        SAMPLE_FLOATS,
        columns=["float_id", "lat", "lon", "date", "depth", "temperature", "salinity", "region"],
    )
    conn.register("_seed", df)
    conn.execute("INSERT INTO floats SELECT * FROM _seed")
    conn.unregister("_seed")

    return conn


# Shared persistent connection for the whole test session
_DB_CONN: duckdb.DuckDBPyConnection | None = None


def _get_test_connection() -> duckdb.DuckDBPyConnection:
    """Returns the shared in-memory connection (creates it once per session)."""
    global _DB_CONN
    if _DB_CONN is None:
        _DB_CONN = _build_in_memory_db()
    return _DB_CONN


@pytest.fixture(scope="session", autouse=True)
def patch_db_connection():
    """
    Session-scoped fixture — patches db_client.get_connection for the entire
    test session so all tests hit the in-memory DB, not the real .db file.
    """
    with patch("src.database.db_client.get_connection", side_effect=_get_test_connection):
        yield
