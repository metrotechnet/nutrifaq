import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import api.services.logging as logging_service
import api.services.publish_scheduler as publish_scheduler
import api.services.indexation_service as regen_service


def test_question_log_defaults_to_debug_kb_path():
    path = logging_service.QUESTION_LOG_PATH
    assert path.name == "question_log.json"
    assert path.parent.name == "nutrifaq-dbase-main"


def test_reset_question_log_clears_file(tmp_path, monkeypatch):
    log_path = tmp_path / "question_log.json"
    log_path.write_text(json.dumps([{"question_id": "existing", "question": "hi"}]), encoding="utf-8")

    monkeypatch.setattr(logging_service, "QUESTION_LOG_PATH", log_path)

    result = logging_service.reset_question_log()

    assert result == []
    assert json.loads(log_path.read_text(encoding="utf-8")) == []


def test_reset_question_log_syncs_to_azure_blob(tmp_path, monkeypatch):
    log_path = tmp_path / "question_log.json"
    monkeypatch.setattr(logging_service, "QUESTION_LOG_PATH", log_path)
    monkeypatch.setattr(logging_service, "_azure_sync_is_enabled", lambda: True)
    monkeypatch.setattr(logging_service, "has_blob_storage_config", lambda: True)

    calls = []

    def fake_upload(blob_name, source_path, overwrite=True, container_name=None):
        calls.append((blob_name, str(source_path), container_name))

    monkeypatch.setattr(logging_service, "upload_file_to_blob", fake_upload)

    result = logging_service.reset_question_log()

    assert result == []
    assert calls and calls[0][0] == "question_log.json"
    assert calls[0][2] == "nutrifaq-config"


def test_schedule_publish_executes_debug_to_main_sync_and_indexing(tmp_path, monkeypatch):
    debug_root = tmp_path / "nutrifaq-dbase-main"
    main_root = tmp_path / "nutrifaq-dbase"
    debug_root.mkdir()
    main_root.mkdir()
    (debug_root / "documents").mkdir()
    (debug_root / "documents" / "a.txt").write_text("debug doc", encoding="utf-8")

    events = []

    def fake_copy(source, target):
        events.append(("copy", str(source), str(target)))
        target.mkdir(parents=True, exist_ok=True)
        (target / "documents").mkdir(exist_ok=True)
        (target / "documents" / "copied.txt").write_text("copied", encoding="utf-8")
        return {"status": "ok"}

    def fake_index(root):
        events.append(("index", str(root)))
        return {"status": "ok"}

    def fake_sync(root, prefix, container):
        events.append(("sync", str(root), str(prefix), str(container)))
        return {"status": "ok"}

    def fake_debug_sync(*args, **kwargs):
        events.append(("debug_sync",))
        return {"status": "ok"}

    monkeypatch.setattr(publish_scheduler, "DEBUG_KB_ROOT", debug_root)
    monkeypatch.setattr(publish_scheduler, "MAIN_KB_ROOT", main_root)
    monkeypatch.setattr(publish_scheduler, "sync_debug_to_blob", fake_debug_sync)
    monkeypatch.setattr(publish_scheduler, "copy_debug_to_main_local", fake_copy)
    monkeypatch.setattr(publish_scheduler, "restart_main_indexing", fake_index)
    monkeypatch.setattr(publish_scheduler, "sync_main_to_blob", fake_sync)

    job = publish_scheduler.schedule_publish(
        model="gpt-4o-mini",
        provider="azure",
        publish_at=datetime.now(timezone.utc) + timedelta(seconds=0.2),
    )

    assert job["status"] == "scheduled"
    assert job["model"] == "gpt-4o-mini"
    assert job["provider"] == "azure"
    assert ("debug_sync",) in events

    deadline = time.time() + 3
    while time.time() < deadline and len(events) < 3:
        time.sleep(0.05)

    assert ("copy", str(debug_root), str(main_root)) in events
    assert ("index", str(main_root)) in events
    assert ("sync", str(main_root), "nutrifaq-dbase", "nutrifaq-dbase-main") in events


def test_indexation_progress_uses_question_and_token_totals(monkeypatch):
    monkeypatch.setattr(regen_service, "_regen_state", {
        "running": True,
        "cancel_requested": False,
        "current_step": "generate_questions",
        "progress_value": 40,
        "progress_total": 100,
        "progress_kind": "questions",
        "active_process": None,
    })

    status = regen_service.get_indexation_status()
    assert status["progress_kind"] == "questions"
    assert status["progress_total"] == 100
    assert status["progress_percent"] == 40.0

    monkeypatch.setattr(regen_service, "_regen_state", {
        "running": True,
        "cancel_requested": False,
        "current_step": "index_chromadb_json",
        "progress_value": 2500,
        "progress_total": 5000,
        "progress_kind": "tokens",
        "active_process": None,
    })

    status = regen_service.get_indexation_status()
    assert status["progress_kind"] == "tokens"
    assert status["progress_total"] == 5000
    assert status["progress_percent"] == 50.0


def test_indexation_cancel_terminates_running_process():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    try:
        regen_service._regen_state["running"] = True
        regen_service._regen_state["cancel_requested"] = False
        regen_service._regen_state["current_step"] = "extract_references"
        regen_service._regen_state["active_process"] = proc

        result = regen_service.request_indexation_cancel()

        assert result["status"] == "cancelling"
        deadline = time.time() + 5
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.05)

        assert proc.poll() is not None
        assert regen_service._regen_state["active_process"] is None
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
