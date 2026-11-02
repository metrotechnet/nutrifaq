from api.services import publish_service


def test_publish_status_defaults_to_idle():
    state = publish_service.get_publish_status()

    assert state["status"] == "idle"
    assert state["step"] == "idle"
    assert state["running"] is False
    assert state["progress"] == 0
    assert isinstance(state["details"], dict)
    assert isinstance(state["workflow_steps"], list)
    assert [step.get("key") for step in state["workflow_steps"]] == [
        "next_publication",
        "indexation",
        "publication",
        "finished",
    ]


def test_start_revert_is_accepted():
    result = publish_service.start_revert()

    assert result["status"] == "accepted"
    assert result["message"] == "Revert started in background."
