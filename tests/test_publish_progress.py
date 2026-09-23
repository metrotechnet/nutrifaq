from api.services import publish_service


def test_publish_status_defaults_to_idle():
    state = publish_service.get_publish_status()

    assert state["status"] == "idle"
    assert state["running"] is False
    assert state["progress"] == 0
