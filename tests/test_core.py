from sandbox_app import health, ping


def test_health() -> None:
    assert health()["status"] == "ok"


def test_ping() -> None:
    assert ping()["pong"] == "true"
