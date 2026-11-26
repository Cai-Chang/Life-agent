from fastapi.testclient import TestClient

from lifeagent.main import app

client = TestClient(app)


def test_liveness_does_not_claim_dependency_readiness():
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_fails_until_real_dependencies_are_wired(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "reason": "dependencies_not_configured",
    }
