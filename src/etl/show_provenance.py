import os
import json

def show_provenance():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    log_file_path = os.path.join(workspace_root, "data", "ingestion_log.jsonl")
    
    if not os.path.exists(log_file_path):
        print(f"No provenance log file found at: {log_file_path}")
        return
        
    print("-" * 95)
    print(f"{'WMO ID':<10} | {'DAC':<10} | {'Status':<8} | {'Records':<8} | {'Timestamp':<25} | {'SHA256 (First 12)'}")
    print("-" * 95)
    
    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                wmo_id = entry.get("wmo_id", "N/A")
                dac = entry.get("dac", "N/A")
                status = entry.get("status", "N/A")
                n_records = entry.get("n_records_extracted", 0)
                timestamp = entry.get("timestamp", "N/A")
                sha256 = entry.get("file_sha256")
                sha_short = sha256[:12] if sha256 else "None"
                
                print(f"{wmo_id:<10} | {dac:<10} | {status:<8} | {n_records:<8} | {timestamp:<25} | {sha_short}")
            except Exception as e:
                print(f"Error parsing log entry: {e}")
                
    print("-" * 95)

if __name__ == "__main__":
    show_provenance()
