import os
import json
from datetime import datetime, timezone

def log_ingestion(wmo_id, dac, url, n_profiles_found, n_records_extracted, status, error_message=None, file_sha256=None):
    """
    Appends one ingestion event to data/ingestion_log.jsonl.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    data_dir = os.path.join(workspace_root, "data")
    
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        
    log_file_path = os.path.join(data_dir, "ingestion_log.jsonl")
    
    # Construct the entry
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "wmo_id": wmo_id,
        "dac": dac,
        "source_url": url,
        "n_profiles_found": n_profiles_found,
        "n_records_extracted": n_records_extracted,
        "status": status,
        "error_message": error_message,
        "file_sha256": file_sha256
    }
    
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
