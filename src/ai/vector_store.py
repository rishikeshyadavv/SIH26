import os
import chromadb
from chromadb.config import Settings

CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "data/chroma_db")

# Initialize persistent Chroma client
client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

# Database schema representation
SCHEMA_INFO = """
Table: floats
Columns:
- float_id (VARCHAR/TEXT): Unique ID identifying the ARGO float platform.
- lat (DOUBLE/REAL): Latitude coordinate (degrees north, range -90 to 90).
- lon (DOUBLE/REAL): Longitude coordinate (degrees east, range -180 to 180).
- date (DATE/TEXT): Date in YYYY-MM-DD format when the profile was recorded.
- depth (DOUBLE/REAL): Ocean depth in decibars / meters (values from 0 down to 500+).
- temperature (DOUBLE/REAL): Sea water temperature in degrees Celsius.
- salinity (DOUBLE/REAL): Sea water salinity in Practical Salinity Units (PSU).
- region (VARCHAR/TEXT): General geographic region name. Can be: 'Equatorial', 'Arabian Sea', 'Bay of Bengal', or 'Other'.
"""

# Initial set of few-shot examples
DEFAULT_EXAMPLES = [
    {
        "question": "Show me the temperature profile of float 2902264",
        "sql": "SELECT depth, temperature FROM floats WHERE float_id = '2902264' ORDER BY depth LIMIT 500"
    },
    {
        "question": "What's the salinity in the Arabian Sea in January 2023?",
        "sql": "SELECT float_id, lat, lon, date, depth, salinity FROM floats WHERE region = 'Arabian Sea' AND date BETWEEN '2023-01-01' AND '2023-01-31' LIMIT 500"
    },
    {
        "question": "Compare temperature in the Arabian Sea vs Bay of Bengal",
        "sql": "SELECT region, AVG(temperature) as avg_temp FROM floats WHERE region IN ('Arabian Sea', 'Bay of Bengal') GROUP BY region"
    },
    {
        "question": "Find nearest ARGO floats to latitude 12 and longitude 65",
        "sql": "SELECT float_id, lat, lon, region, MIN((lat - 12.0)*(lat - 12.0) + (lon - 65.0)*(lon - 65.0)) as distance_sq FROM floats GROUP BY float_id ORDER BY distance_sq LIMIT 5"
    },
    {
        "question": "What is the average salinity profile for Bay of Bengal in March 2023?",
        "sql": "SELECT depth, AVG(salinity) as avg_salinity FROM floats WHERE region = 'Bay of Bengal' AND date BETWEEN '2023-03-01' AND '2023-03-31' GROUP BY depth ORDER BY depth"
    },
    {
        "question": "Show all records for float 5904664",
        "sql": "SELECT * FROM floats WHERE float_id = '5904664' ORDER BY date, depth LIMIT 500"
    },
    {
        "question": "Find temperature at 50m depth in the Bay of Bengal on 2023-01-11",
        "sql": "SELECT float_id, lat, lon, date, temperature FROM floats WHERE region = 'Bay of Bengal' AND depth = 50.0 AND date = '2023-01-11' LIMIT 500"
    },
    {
        "question": "What's the maximum temperature recorded by float 2902266?",
        "sql": "SELECT MAX(temperature) as max_temp FROM floats WHERE float_id = '2902266'"
    },
    {
        "question": "Give me a list of all unique float IDs",
        "sql": "SELECT DISTINCT float_id FROM floats ORDER BY float_id"
    },
    {
        "question": "What is the average temperature in Equatorial region in March 2023?",
        "sql": "SELECT AVG(temperature) as avg_temp FROM floats WHERE region = 'Equatorial' AND date BETWEEN '2023-03-01' AND '2023-03-31'"
    }
]

def init_vector_store():
    """Initializes and seeds the collections in ChromaDB if not already present."""
    # 1. Setup Schema Collection
    schema_coll = client.get_or_create_collection(name="schema_store")
    if schema_coll.count() == 0:
        schema_coll.add(
            documents=[SCHEMA_INFO],
            ids=["floats_schema"]
        )
        print("ChromaDB: Seeded schema metadata.")
        
    # 2. Setup Few-Shot Examples Collection
    examples_coll = client.get_or_create_collection(name="few_shot_examples")
    if examples_coll.count() == 0:
        documents = [ex["question"] for ex in DEFAULT_EXAMPLES]
        metadatas = [{"sql": ex["sql"]} for ex in DEFAULT_EXAMPLES]
        ids = [f"example_{i}" for i in range(len(DEFAULT_EXAMPLES))]
        
        examples_coll.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        print(f"ChromaDB: Seeded {len(DEFAULT_EXAMPLES)} few-shot examples.")

def get_db_schema() -> str:
    """Retrieves schema information from the vector store."""
    schema_coll = client.get_collection(name="schema_store")
    result = schema_coll.get(ids=["floats_schema"])
    if result and result["documents"]:
        return result["documents"][0]
    return SCHEMA_INFO

def get_few_shot_examples(question: str, k: int = 3) -> str:
    """Queries ChromaDB for the most similar past queries to build RAG prompt context."""
    init_vector_store()
    
    examples_coll = client.get_collection(name="few_shot_examples")
    results = examples_coll.query(
        query_texts=[question],
        n_results=k
    )
    
    if not results or not results["documents"] or len(results["documents"][0]) == 0:
        return ""
        
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    
    prompt_chunk = "\nHere are examples of natural language questions and their corresponding SQL:\n"
    for q, meta in zip(documents, metadatas):
        prompt_chunk += f"\nQ: {q}\nSQL: {meta['sql']}\n"
        
    return prompt_chunk

# Initialize vector store on module load
try:
    init_vector_store()
except Exception as e:
    print(f"ChromaDB initialization error: {e}")
