import requests
import json

URL = "http://127.0.0.1:8000/ask"

payload = {
    "question": "Show me the temperature profile of float 2902264"
}

print(f"Sending POST request to {URL}...")
try:
    response = requests.post(URL, json=payload)
    print("Status Code:", response.status_code)
    
    if response.status_code == 200:
        data = response.json()
        print("Response JSON keys:", list(data.keys()))
        print("Success Status:", data.get("success"))
        print("Generated SQL:", data.get("sql"))
        print("Data row count:", len(data.get("data", [])))
        print("Latency (seconds):", data.get("latency_seconds"))
        if data.get("data"):
            print("First row sample:", data["data"][0])
    else:
        print("Failed. Response text:", response.text)
except Exception as e:
    print("Request failed:", e)
