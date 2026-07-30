from sandbox_app import version


def test_version():
    assert version()["version"] == "0.1.0"
