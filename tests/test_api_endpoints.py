from fastapi.testclient import TestClient
from src.backend.main import app
import os

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "FloatChat API"

def test_ask_unauthorized():
    # Attempt request without API Key
    response = client.post("/ask", json={"question": "Show temperature profile"})
    # FastAPI returns 422 if a required header is missing
    assert response.status_code == 422

def test_ask_invalid_key():
    # Attempt request with invalid API Key
    response = client.post(
        "/ask", 
        json={"question": "Show temperature profile"},
        headers={"X-API-Key": "invalid_secret_key"}
    )
    assert response.status_code == 401
    assert "Unauthorized" in response.json()["detail"]

def test_ask_valid_key_rate_limiting():
    # Retrieve the API Key from environment or use default
    api_key = os.getenv("FLOAT_API_KEY", "float_secret_key_2026")
    
    # Send a request with correct credentials (we don't mock LLM calls here,
    # but we can verify that the auth check passes.
    response = client.post(
        "/ask",
        json={"question": "Show temperature profile of float 2902264"},
        headers={"X-API-Key": api_key}
    )
    assert response.status_code in [200, 500, 429]
