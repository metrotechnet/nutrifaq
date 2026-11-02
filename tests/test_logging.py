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


def test_final_publish_indexing_skips_generate_questions(monkeypatch):
    captured_kwargs = {}

    def fake_run_full_indexation(**kwargs):
        captured_kwargs.update(kwargs)
        return {"status": "success"}

    monkeypatch.setattr(publish_scheduler, "run_full_indexation", fake_run_full_indexation)
    monkeypatch.setattr(publish_scheduler, "_run_publish_job", lambda model, provider: None)
    monkeypatch.setattr(publish_scheduler, "_append_schedule_log", lambda *args, **kwargs: {})

    result = publish_scheduler.run_indexation_then_publish(model="gpt-4o-mini", provider="azure")

    assert result["status"] == "ok"
    assert captured_kwargs["include_extract_docx"] is True
    assert captured_kwargs["include_extract_references"] is True
    assert captured_kwargs["include_generate_questions"] is False


def test_schedule_publish_immediate_uses_current_time():
    job_id = "test-immediate-publish"
    before = datetime.now(timezone.utc)
    result = publish_scheduler.schedule_publish(
        model="gpt-4o-mini",
        provider="azure",
        recurrence="immediate",
        timezone_name="UTC",
        job_id=job_id,
    )
    try:
        assert result["status"] == "scheduled"
        run_at = result.get("persisted", {}).get("run_at")
        assert isinstance(run_at, str) and run_at
        scheduled_at = datetime.fromisoformat(run_at)
        delay_seconds = (scheduled_at - before).total_seconds()
        assert 0 <= delay_seconds <= 5
    finally:
        publish_scheduler.cancel_scheduled_publish(job_id)


def test_schedule_publish_once_near_time_is_not_marked_immediate():
    job_id = "test-once-near-time"
    run_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    result = publish_scheduler.schedule_publish(
        model="gpt-4o-mini",
        provider="azure",
        publish_at=run_at.isoformat(),
        recurrence="once",
        timezone_name="UTC",
        job_id=job_id,
    )
    try:
        persisted = result.get("persisted", {})
        assert persisted.get("immediate") is False
        assert persisted.get("recurrence") == "one_time"
    finally:
        publish_scheduler.cancel_scheduled_publish(job_id)


def test_schedule_publish_immediate_rejected_while_processing(monkeypatch):
    monkeypatch.setattr(publish_scheduler, "get_publish_status", lambda: {"running": True})
    monkeypatch.setattr(publish_scheduler, "get_indexation_status", lambda: {"running": False})

    try:
        publish_scheduler.schedule_publish(
            model="gpt-4o-mini",
            provider="azure",
            recurrence="immediate",
            timezone_name="UTC",
            job_id="test-immediate-while-running",
        )
    except ValueError as exc:
        assert "already running" in str(exc).lower()
    else:
        raise AssertionError("Expected immediate scheduling to be rejected while processing is running.")


def test_immediate_schedule_cleared_after_workflow(monkeypatch):
    removed_job_ids = []

    monkeypatch.setattr(publish_scheduler, "run_full_indexation", lambda **kwargs: {"status": "success"})
    monkeypatch.setattr(publish_scheduler, "_run_publish_job", lambda model, provider: None)
    monkeypatch.setattr(publish_scheduler, "get_publish_status", lambda: {"status": "completed"})
    monkeypatch.setattr(publish_scheduler, "_append_schedule_log", lambda *args, **kwargs: {})
    monkeypatch.setattr(publish_scheduler, "_remove_persisted_schedule", lambda job_id: removed_job_ids.append(job_id) or [])

    result = publish_scheduler.run_indexation_then_publish(
        model="gpt-4o-mini",
        provider="azure",
        immediate=True,
        schedule_job_id="active-publish-schedule",
    )

    assert result["status"] == "ok"
    assert removed_job_ids == ["active-publish-schedule"]


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


def test_indexation_status_reads_latest_snapshot_progress(monkeypatch, tmp_path):
    snapshot_path = tmp_path / "indexing_progress.json"
    snapshot_path.write_text(json.dumps({
        "step": "index_chromadb_json",
        "kind": "tokens",
        "value": 2500,
        "total": 5000,
        "updated_at": 12345,
    }), encoding="utf-8")

    monkeypatch.setattr(regen_service, "REGEN_PROGRESS_PATH", snapshot_path)
    monkeypatch.setattr(regen_service, "_regen_state", {
        "running": True,
        "cancel_requested": False,
        "current_step": None,
        "progress_value": None,
        "progress_total": None,
        "progress_kind": None,
        "active_process": None,
    })

    status = regen_service.get_indexation_status()
    assert status["current_step"] == "index_chromadb_json"
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
