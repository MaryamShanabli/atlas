"""
Tests for the Stage 0 /health endpoint.

These are intentionally simple -- /health has almost no logic, so the
tests exist to catch regressions (e.g., someone removes the DB check
in a later refactor) rather than to exercise complex behavior.
"""


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_reports_database_connected(client):
    response = client.get("/health")
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


def test_health_response_shape(client):
    """
    Locks down the exact response contract. If this test ever needs to
    change, it should be a deliberate decision, not an accidental one.
    """
    response = client.get("/health")
    body = response.json()
    assert set(body.keys()) == {"status", "database"}
