$env:PYTHONPATH = "d:\DOCUMENTSSS\RISHIKESH\b tech\projects\SHI 2026\ver 1"
Set-Location "d:\DOCUMENTSSS\RISHIKESH\b tech\projects\SHI 2026\ver 1"
python -m uvicorn src.backend.main:app --host 127.0.0.1 --port 8000 --log-level warning
