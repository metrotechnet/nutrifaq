import json

import api.services.logging as logging_service


def test_reset_question_log_clears_file(tmp_path, monkeypatch):
    log_path = tmp_path / "question_log.json"
    log_path.write_text(json.dumps([{"question_id": "existing", "question": "hi"}]), encoding="utf-8")

    monkeypatch.setattr(logging_service, "QUESTION_LOG_PATH", log_path)

    result = logging_service.reset_question_log()

    assert result == []
    assert json.loads(log_path.read_text(encoding="utf-8")) == []
