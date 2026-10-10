
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200


def test_assistant_requires_authentication():
    response = client.post(
        "/api/assistant",
        json={"message": "show my tasks"},
    )

    assert response.status_code == 401


def test_approvals_require_authentication():
    response = client.get("/api/approvals")

    assert response.status_code == 401
