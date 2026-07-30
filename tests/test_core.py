from sandbox_app import health, ping, version


def test_health() -> None:
    assert health()["status"] == "ok"


def test_ping() -> None:
    assert ping()["pong"] == "true"


def test_version() -> None:
    assert version() == {"version": "0.1.0"}
