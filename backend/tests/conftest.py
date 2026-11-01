import os
import sys
from pathlib import Path

# Deterministic offline tests: no AI key, no voice service.
os.environ["LLM_PROVIDER"] = "none"
os.environ["TTS_PROVIDER"] = "none"
os.environ["RATE_LIMIT_PER_MINUTE"] = "0"          # off by default in tests
os.environ["RATE_LIMIT_GLOBAL_PER_MINUTE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from app.main import app

SAMPLES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def farmer_scheme(client):
    with open(SAMPLES / "sample_farmer_scheme.pdf", "rb") as f:
        r = client.post("/api/ingest", files={"file": ("s.pdf", f, "application/pdf")})
    assert r.status_code == 200
    return r.json()["scheme"]


FARMER = {"state": "Tamil Nadu", "occupation": "farmer", "annual_income_lakh": 1.8, "category": "obc"}
