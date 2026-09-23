import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def demo_database():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "reset_demo.py")], cwd=ROOT, check=True)


@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app) as test_client:
        yield test_client


def csrf(client: TestClient, path: str = "/login") -> str:
    response = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def login(client: TestClient, email="admin@poc.local", password="Admin123!"):
    return client.post("/login", data={"email": email, "password": password, "csrf_token": csrf(client)}, follow_redirects=False)

