from api.services import publish_service


def test_publish_status_defaults_to_idle():
    state = publish_service.get_publish_status()

    assert state["status"] == "idle"
    assert state["running"] is False
    assert state["progress"] == 0


def test_start_revert_is_accepted():
    result = publish_service.start_revert()

    assert result["status"] == "accepted"
    assert result["message"] == "Revert started in background."
