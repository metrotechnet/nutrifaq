from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from api.services.config import (
    append_publish_log_entry,
    delete_publish_schedule_entry,
    load_publish_schedule_entries,
    save_publish_schedule_entries,
    upsert_publish_schedule_entry,
)
from api.services.indexation_service import get_indexation_status, request_indexation_cancel, run_full_indexation
from api.services.publish_service import _run_publish_job, cancel_publish, get_publish_status
from api.services.workflow_events import emit_workflow_event

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]
DEBUG_KB_ROOT = REPO_ROOT / os.getenv("DEBUG_KB_LOCAL_ROOT", "nutrifaq-dbase-main")
MAIN_KB_ROOT = REPO_ROOT / os.getenv("AZURE_KB_MAIN_LOCAL_ROOT", "nutrifaq-dbase-main")

AUTO_PUBLISH_ENABLED = os.getenv("AUTO_PUBLISH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
AUTO_PUBLISH_CRON = os.getenv("AUTO_PUBLISH_CRON", "").strip()
AUTO_PUBLISH_INTERVAL_MINUTES = int(os.getenv("AUTO_PUBLISH_INTERVAL_MINUTES", "0") or 0)
AUTO_PUBLISH_TIME = os.getenv("AUTO_PUBLISH_TIME", "").strip()
AUTO_PUBLISH_RECURRENCE = os.getenv("AUTO_PUBLISH_RECURRENCE", "daily").strip() or "daily"
AUTO_PUBLISH_TIMEZONE = os.getenv("AUTO_PUBLISH_TIMEZONE", "UTC").strip() or "UTC"
AUTO_PUBLISH_DEFAULT_MODEL = os.getenv("AUTO_PUBLISH_DEFAULT_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
AUTO_PUBLISH_DEFAULT_PROVIDER = os.getenv("AUTO_PUBLISH_DEFAULT_PROVIDER", "azure").strip() or "azure"
AUTO_PUBLISH_COOLDOWN_MINUTES = int(os.getenv("AUTO_PUBLISH_COOLDOWN_MINUTES", "60") or 60)

_scheduler: BackgroundScheduler | None = None
_scheduler_lock = threading.RLock()
_schedule_transition_lock = threading.Lock()
_schedule_transition_in_progress = 0
_schedule_cancel_latch_lock = threading.Lock()
_schedule_cancel_latched_job_ids: set[str] = set()
_schedule_persist_lock = threading.Lock()
_schedule_persist_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="publish-schedule-persist")
_schedule_persist_sequence_by_job: dict[str, int] = {}
_immediate_schedule_state_lock = threading.Lock()
_immediate_schedule_cleared_at: str | None = None
_immediate_schedule_cleared_job_id: str | None = None
_FILE_CHANGE_SNAPSHOT_PATH = REPO_ROOT / ".publish_file_snapshot.json"


def _set_schedule_transition_running(is_running: bool) -> None:
    global _schedule_transition_in_progress
    with _schedule_transition_lock:
        if is_running:
            _schedule_transition_in_progress += 1
            return
        _schedule_transition_in_progress = max(0, _schedule_transition_in_progress - 1)


def _is_schedule_transition_running() -> bool:
    with _schedule_transition_lock:
        return _schedule_transition_in_progress > 0


def _mark_schedule_cancel_requested(job_id: str | None) -> None:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return
    with _schedule_cancel_latch_lock:
        _schedule_cancel_latched_job_ids.add(normalized_job_id)


def _is_schedule_cancel_requested(job_id: str | None) -> bool:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return False
    with _schedule_cancel_latch_lock:
        return normalized_job_id in _schedule_cancel_latched_job_ids


def _clear_schedule_cancel_requested(job_id: str | None) -> None:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return
    with _schedule_cancel_latch_lock:
        _schedule_cancel_latched_job_ids.discard(normalized_job_id)


def _append_schedule_log(event: str, **details: Any) -> dict[str, Any]:
    """Persist a lightweight publish scheduler journal entry."""
    nested_result = details.get("result")
    if isinstance(nested_result, dict):
        for key in ("scheduled_for", "run_at", "next_run_time", "triggered_at"):
            if key in nested_result and key not in details:
                details[key] = nested_result[key]

    if "scheduled_for" not in details and "run_at" in details:
        details["scheduled_for"] = details["run_at"]
    if "executed_at" not in details:
        details["executed_at"] = datetime.now().astimezone().isoformat()

    scheduled_for = (
        details.get("scheduled_for")
        or details.get("run_at")
        or details.get("next_run_time")
        or (isinstance(nested_result, dict) and (nested_result.get("scheduled_for") or nested_result.get("run_at") or nested_result.get("next_run_time")))
    )
    details.setdefault("status", event)
    details.setdefault("operation", "publish")
    if "model" not in details and "model_used" in details:
        details["model"] = details["model_used"]
    if "provider" not in details and "provider_used" in details:
        details["provider"] = details["provider_used"]
    if "files_count" not in details and "uploaded_files_count" in details:
        details["files_count"] = details["uploaded_files_count"]

    if scheduled_for is not None:
        details["scheduled_for"] = scheduled_for
        details["run_at"] = details.get("run_at") or scheduled_for

    entry = {
        "timestamp": scheduled_for or details.get("executed_at") or datetime.now().astimezone().isoformat(),
        "event": event,
        "details": details,
        "operation": details.get("operation", "publish"),
        "status": details.get("status", event),
        "model": details.get("model") or details.get("model_used") or None,
        "provider": details.get("provider") or details.get("provider_used") or None,
        "files_count": details.get("files_count") or details.get("uploaded_files_count") or 0,
        "scheduled_for": scheduled_for or details.get("executed_at"),
        "executed_at": details.get("executed_at") or datetime.now().astimezone().isoformat(),
    }
    try:
        return append_publish_log_entry(entry)
    except Exception:
        return entry


def _mark_immediate_schedule_cleared(job_id: str | None) -> None:
    normalized_job_id = str(job_id or "").strip() or "active-publish-schedule"
    cleared_at = datetime.now(timezone.utc).isoformat()
    with _immediate_schedule_state_lock:
        global _immediate_schedule_cleared_at, _immediate_schedule_cleared_job_id
        _immediate_schedule_cleared_at = cleared_at
        _immediate_schedule_cleared_job_id = normalized_job_id
    try:
        emit_workflow_event(
            "schedule.cleared",
            {
                "job_id": normalized_job_id,
                "immediate": True,
                "cleared_at": cleared_at,
            },
        )
    except Exception:
        pass


def _reset_immediate_schedule_cleared_state() -> None:
    with _immediate_schedule_state_lock:
        global _immediate_schedule_cleared_at, _immediate_schedule_cleared_job_id
        _immediate_schedule_cleared_at = None
        _immediate_schedule_cleared_job_id = None


def _get_immediate_schedule_cleared_state() -> tuple[str | None, str | None]:
    with _immediate_schedule_state_lock:
        return _immediate_schedule_cleared_at, _immediate_schedule_cleared_job_id


def _snapshot_kb_files(root: Path | str) -> dict[str, str]:
    """Return a compact manifest of file paths and mtimes for change detection."""
    root_path = Path(root)
    if not root_path.exists():
        return {}

    snapshot: dict[str, str] = {}
    for path in sorted(root_path.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root_path).as_posix()
        stat = path.stat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.stat().st_size > 0 else "empty"
        snapshot[relative] = f"{stat.st_mtime_ns}:{stat.st_size}:{digest}"
    return snapshot


def _load_last_snapshot() -> dict[str, str]:
    if not _FILE_CHANGE_SNAPSHOT_PATH.exists():
        return {}
    try:
        with _FILE_CHANGE_SNAPSHOT_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return {str(k): str(v) for k, v in payload.items()}
    except Exception:
        pass
    return {}


def _save_current_snapshot(root: Path | str) -> None:
    try:
        _FILE_CHANGE_SNAPSHOT_PATH.write_text(json.dumps(_snapshot_kb_files(root), ensure_ascii=False, sort_keys=True), encoding="utf-8")
    except Exception:
        pass


def has_files_changed(root: Path | str | None = None) -> bool:
    """Return True when the file set under the KB has changed since the last snapshot."""
    root_path = Path(root or MAIN_KB_ROOT)
    previous = _load_last_snapshot()
    current = _snapshot_kb_files(root_path)
    if not previous and current:
        _save_current_snapshot(root_path)
        return True
    changed = previous != current
    if changed:
        _save_current_snapshot(root_path)
    return changed


def run_indexation_then_publish(
    *,
    model: str,
    provider: str = "azure",
    scheduled_for: datetime | str | None = None,
    immediate: bool = False,
    schedule_job_id: str | None = None,
) -> dict[str, Any]:
    """Run indexation first and then trigger publish, but only when files changed."""
    _set_schedule_transition_running(True)
    try:
        debug = False
        if debug:
            planned_value = _format_report_datetime(_normalize_datetime(scheduled_for, default_tz=timezone.utc), "UTC") if scheduled_for is not None else _actual_now_iso()
            _append_schedule_log("publish_triggered", model=model, provider=provider, scheduled_for=planned_value, executed_at=_actual_now_iso())

            return {
                "status": "debug",
                "code": "publish.schedule.debug",
                "message_key": "publish.schedule.debug",
                "message": "Debug short-circuit: indexing and publication were skipped.",
                "user_message": "Debug short-circuit: indexing and publication were skipped.",
                "model": model,
                "provider": provider,
                "scheduled_for": planned_value,
            }

        planned_value = _format_report_datetime(_normalize_datetime(scheduled_for, default_tz=timezone.utc), "UTC") if scheduled_for is not None else _actual_now_iso()
        root_path = Path(MAIN_KB_ROOT)

        # if not has_files_changed(root_path):
        #     no_change = {
        #         "status": "no_changes",
        #         "code": "publish.schedule.noChanges",
        #         "message_key": "publish.schedule.noChanges",
        #         "message": "No files changed; nothing to publish.",
        #         "user_message": "No files changed; nothing to publish.",
        #         "model": model,
        #         "provider": provider,
        #         "scheduled_for": planned_value,
        #     }
        #     _append_schedule_log("publish_skipped_no_changes", model=model, provider=provider, root=str(root_path), result=no_change, scheduled_for=planned_value, executed_at=_actual_now_iso())
        #     return no_change

        indexation_result = run_full_indexation(
            include_extract_docx=True,
            include_extract_references=True,
            include_generate_questions=False,
            root_folder=root_path.name,
            container_name=os.getenv("AZURE_MAIN_KB_CONTAINER", "nutrifaq-dbase-main"),
        )
        if indexation_result.get("status") not in {"success"}:
            failure = {
                "status": indexation_result.get("status", "error"),
                "code": "publish.schedule.indexationFailed",
                "message_key": "publish.schedule.indexationFailed",
                "message": "Indexation failed.",
                "indexation": indexation_result,
                "model": model,
                "provider": provider,
                "scheduled_for": planned_value,
            }
            _append_schedule_log("publish_indexation_failed", model=model, provider=provider, root=str(root_path), result=failure, scheduled_for=planned_value, executed_at=_actual_now_iso())
            return failure

        if _is_schedule_cancel_requested(schedule_job_id):
            cancelled = {
                "status": "cancelled",
                "code": "publish.schedule.cancelled",
                "message_key": "publish.schedule.cancelled",
                "message": "Publication cancelled.",
                "indexation": indexation_result,
                "model": model,
                "provider": provider,
                "scheduled_for": planned_value,
            }
            _append_schedule_log(
                "publish_cancelled_before_start",
                model=model,
                provider=provider,
                root=str(root_path),
                indexation=indexation_result,
                result=cancelled,
                scheduled_for=planned_value,
                executed_at=_actual_now_iso(),
            )
            return cancelled

        publish_result: dict[str, Any] = {"status": "unknown"}
        try:
            _run_publish_job(model=model, provider=provider)
            publish_result = {
                "status": "completed",
                "model": model,
                "provider": provider,
            }
        except Exception as exc:
            failure = {
                "status": "error",
                "code": "publish.schedule.publishExecutionFailed",
                "message_key": "publish.schedule.publishExecutionFailed",
                "message": "Publication execution failed.",
                "error": str(exc),
                "indexation": indexation_result,
                "model": model,
                "provider": provider,
                "scheduled_for": planned_value,
            }
            _append_schedule_log(
                "publish_execution_failed",
                model=model,
                provider=provider,
                root=str(root_path),
                indexation=indexation_result,
                result=failure,
                scheduled_for=planned_value,
                executed_at=_actual_now_iso(),
            )
            return failure

        final_publish_state: dict[str, Any] = get_publish_status()

        final_status_value = str(final_publish_state.get("status", "")).strip().lower()
        if final_status_value == "cancelled":
            cancelled = {
                "status": "cancelled",
                "code": "publish.schedule.cancelled",
                "message_key": "publish.schedule.cancelled",
                "message": "Publication cancelled.",
                "publish": publish_result,
                "publish_status": final_publish_state,
                "indexation": indexation_result,
                "model": model,
                "provider": provider,
                "scheduled_for": planned_value,
            }
            _append_schedule_log(
                "publish_cancelled",
                model=model,
                provider=provider,
                root=str(root_path),
                indexation=indexation_result,
                publish=publish_result,
                result=cancelled,
                scheduled_for=planned_value,
                executed_at=_actual_now_iso(),
            )
            return cancelled

        if final_status_value == "error":
            failed = {
                "status": "error",
                "code": "publish.schedule.publishFailed",
                "message_key": "publish.schedule.publishFailed",
                "message": "Publication failed.",
                "error": final_publish_state.get("error"),
                "publish": publish_result,
                "publish_status": final_publish_state,
                "indexation": indexation_result,
                "model": model,
                "provider": provider,
                "scheduled_for": planned_value,
            }
            _append_schedule_log(
                "publish_failed",
                model=model,
                provider=provider,
                root=str(root_path),
                indexation=indexation_result,
                publish=publish_result,
                result=failed,
                scheduled_for=planned_value,
                executed_at=_actual_now_iso(),
            )
            return failed

        successful = {
            "status": "ok",
            "code": "publish.schedule.triggered",
            "message_key": "publish.schedule.triggered",
            "message": "Indexation and publication completed.",
            "user_message": "Indexation and publication completed.",
            "publish": publish_result,
            "publish_status": final_publish_state,
            "model": model,
            "provider": provider,
            "scheduled_for": planned_value,
        }
        _append_schedule_log("publish_triggered", model=model, provider=provider, root=str(root_path), indexation=indexation_result, publish=publish_result, scheduled_for=planned_value, executed_at=_actual_now_iso())
        return successful
    finally:
        if immediate:
            immediate_job_id = str(schedule_job_id or "").strip()
            if immediate_job_id:
                scheduler = _scheduler
                if scheduler is not None:
                    active_job = scheduler.get_job(immediate_job_id)
                    if active_job is not None:
                        try:
                            scheduler.remove_job(immediate_job_id)
                        except Exception:
                            pass
                _remove_persisted_schedule(immediate_job_id)
                _mark_immediate_schedule_cleared(immediate_job_id)
        _clear_schedule_cancel_requested(schedule_job_id)
        _set_schedule_transition_running(False)
        _emit_scheduler_status_event()


def sync_debug_to_blob(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Sync the debug KB to blob storage before publication."""
    return {"status": "ok", "container": os.getenv("AZURE_DEBUG_KB_CONTAINER", "nutrifaq-dbase-main")}


def copy_debug_to_main_local(source: Path | str, target: Path | str) -> dict[str, Any]:
    """Copy the debug KB to the main local KB folder for publication."""
    source_path = Path(source)
    target_path = Path(target)
    target_path.mkdir(parents=True, exist_ok=True)
    if source_path.exists():
        for child in source_path.iterdir():
            destination = target_path / child.name
            if child.is_dir():
                copy_debug_to_main_local(child, destination)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(child.read_bytes())
    return {"status": "ok", "source": str(source_path), "target": str(target_path)}


def restart_main_indexing(root: Path | str) -> dict[str, Any]:
    """Re-index the local main KB after syncing the debug documents into it."""
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    return {"status": "ok", "root": str(root_path)}


def sync_main_to_blob(root: Path | str, prefix: str, container: str) -> dict[str, Any]:
    """Sync the local main KB to blob storage."""
    return {"status": "ok", "root": str(root), "prefix": prefix, "container": container}


def _ensure_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="UTC")
        _scheduler.start()
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None:
            _scheduler.shutdown(wait=False)
            _scheduler = None


def _resolve_timezone(name: str | None) -> ZoneInfo:
    timezone_name = (name or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("UTC")


def _normalize_datetime(value: datetime | str | None, *, default_tz: timezone | None = None) -> datetime | None:
    if value is None:
        return None
    tzinfo = default_tz or timezone.utc
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tzinfo)
        return dt.astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            try:
                dt = datetime.strptime(text, "%H:%M")
            except ValueError:
                return None
            now = datetime.now(timezone.utc)
            dt = dt.replace(tzinfo=tzinfo)
            if dt.astimezone(timezone.utc) <= now:
                dt = dt + timedelta(days=1)
            return dt.astimezone(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tzinfo)
        return dt.astimezone(timezone.utc)
    return None


def _build_job_id(prefix: str = "publish") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _format_report_datetime(value: datetime | None, timezone_name: str | None = None) -> str | None:
    if value is None:
        return None
    try:
        target_tz = _resolve_timezone(timezone_name) if timezone_name else datetime.now().astimezone().tzinfo
        if target_tz is None:
            return value.astimezone().isoformat()
        return value.astimezone(target_tz).isoformat()
    except Exception:
        return value.astimezone().isoformat()


def _actual_now_iso(timezone_name: str | None = None) -> str:
    target_tz = _resolve_timezone(timezone_name) if timezone_name else datetime.now().astimezone().tzinfo
    return datetime.now(target_tz).isoformat() if target_tz is not None else datetime.now().astimezone().isoformat()


def _next_schedule_persist_sequence(job_id: str) -> int:
    normalized_job_id = str(job_id or "").strip()
    with _schedule_persist_lock:
        sequence = _schedule_persist_sequence_by_job.get(normalized_job_id, 0) + 1
        _schedule_persist_sequence_by_job[normalized_job_id] = sequence
        return sequence


def _is_latest_schedule_persist_sequence(job_id: str, sequence: int) -> bool:
    normalized_job_id = str(job_id or "").strip()
    with _schedule_persist_lock:
        return _schedule_persist_sequence_by_job.get(normalized_job_id) == sequence


def _persist_schedule_entry(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        return record
    job_id = str(record.get("job_id") or record.get("id") or "").strip()
    if not job_id:
        logger.error("Skipping async schedule persistence: missing job id in record.")
        return record

    sequence = _next_schedule_persist_sequence(job_id)

    def _run() -> None:
        if not _is_latest_schedule_persist_sequence(job_id, sequence):
            return
        try:
            upsert_publish_schedule_entry(record)
        except Exception:
            logger.exception("Async publish schedule persistence failed for job '%s'.", job_id)

    _schedule_persist_executor.submit(_run)
    return record


def _remove_persisted_schedule(job_id: str) -> list[dict[str, Any]]:
    _next_schedule_persist_sequence(job_id)
    return delete_publish_schedule_entry(job_id)


def _build_saved_schedule_record(
    *,
    job_id: str,
    model: str,
    provider: str,
    recurrence: str | None,
    schedule: str | None,
    run_at: str | None,
    cron: str | None,
    interval_minutes: int | None,
    timezone_name: str,
    immediate: bool = False,
) -> dict[str, Any]:
    return {
        "id": job_id,
        "job_id": job_id,
        "model": model,
        "provider": provider,
        "recurrence": recurrence or "one_time",
        "schedule": schedule,
        "run_at": run_at,
        "cron": cron,
        "interval_minutes": int(interval_minutes) if interval_minutes is not None else None,
        "timezone_name": timezone_name or "UTC",
        "immediate": bool(immediate),
        "enabled": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def restore_persisted_publish_schedules() -> list[dict[str, Any]]:
    """Rehydrate APScheduler jobs from the persisted schedule definitions."""
    scheduler = _ensure_scheduler()
    restored: list[dict[str, Any]] = []
    try:
        saved_entries = load_publish_schedule_entries()
    except Exception:
        return restored

    for entry in saved_entries:
        if not entry.get("enabled", True):
            continue

        job_id = str(entry.get("job_id") or entry.get("id") or "").strip()
        if not job_id or scheduler.get_job(job_id) is not None:
            continue

        model = str(entry.get("model") or "").strip() or AUTO_PUBLISH_DEFAULT_MODEL
        provider = str(entry.get("provider") or AUTO_PUBLISH_DEFAULT_PROVIDER).strip() or AUTO_PUBLISH_DEFAULT_PROVIDER
        recurrence = str(entry.get("recurrence") or "one_time").strip().lower()
        cron_expression = entry.get("cron")
        interval_minutes = entry.get("interval_minutes")
        run_at = entry.get("run_at") or entry.get("schedule")
        timezone_name = str(entry.get("timezone_name") or AUTO_PUBLISH_TIMEZONE or "UTC").strip() or "UTC"
        immediate = bool(entry.get("immediate"))

        added = False
        if cron_expression:
            scheduler.add_job(
                run_indexation_then_publish,
                id=job_id,
                trigger=CronTrigger.from_crontab(cron_expression, timezone=timezone_name),
                kwargs={"model": model, "provider": provider, "scheduled_for": run_at, "immediate": immediate, "schedule_job_id": job_id},
                replace_existing=True,
            )
            added = True
        elif isinstance(interval_minutes, int) and interval_minutes > 0:
            scheduler.add_job(
                run_indexation_then_publish,
                id=job_id,
                trigger="interval",
                minutes=int(interval_minutes),
                kwargs={"model": model, "provider": provider, "scheduled_for": run_at, "immediate": immediate, "schedule_job_id": job_id},
                replace_existing=True,
            )
            added = True
        elif run_at:
            run_date = _normalize_datetime(run_at, default_tz=_resolve_timezone(timezone_name))
            if run_date is not None:
                scheduler.add_job(
                    run_indexation_then_publish,
                    id=job_id,
                    trigger="date",
                    run_date=run_date,
                    kwargs={"model": model, "provider": provider, "scheduled_for": run_at, "immediate": immediate, "schedule_job_id": job_id},
                    replace_existing=True,
                )
                added = True

        if added:
            restored.append(entry)

    return restored


def configure_default_auto_publish() -> dict[str, Any]:
    """Create the default automatic publish job from environment settings when enabled."""
    if not AUTO_PUBLISH_ENABLED:
        return {"status": "disabled", "message": "Automatic publish is disabled."}

    scheduler = _ensure_scheduler()
    if scheduler.get_job("auto-publish") is not None:
        return {"status": "already-configured", "job_id": "auto-publish"}

    model = AUTO_PUBLISH_DEFAULT_MODEL
    provider = AUTO_PUBLISH_DEFAULT_PROVIDER
    if AUTO_PUBLISH_CRON:
        scheduler.add_job(
            run_indexation_then_publish,
            id="auto-publish",
            trigger=CronTrigger.from_crontab(AUTO_PUBLISH_CRON, timezone=AUTO_PUBLISH_TIMEZONE),
            kwargs={"model": model, "provider": provider, "schedule_job_id": "auto-publish"},
            replace_existing=True,
        )
        return {"status": "scheduled", "job_id": "auto-publish", "cron": AUTO_PUBLISH_CRON}

    if AUTO_PUBLISH_INTERVAL_MINUTES > 0:
        scheduler.add_job(
            run_indexation_then_publish,
            id="auto-publish",
            trigger="interval",
            minutes=AUTO_PUBLISH_INTERVAL_MINUTES,
            kwargs={"model": model, "provider": provider, "schedule_job_id": "auto-publish"},
            replace_existing=True,
        )
        return {"status": "scheduled", "job_id": "auto-publish", "interval_minutes": AUTO_PUBLISH_INTERVAL_MINUTES}

    if AUTO_PUBLISH_TIME:
        recurrence = (AUTO_PUBLISH_RECURRENCE or "daily").lower()
        user_time = AUTO_PUBLISH_TIME
        if recurrence in {"daily", "weekly"}:
            result = schedule_publish(
                model=model,
                provider=provider,
                user_time=user_time,
                recurrence=recurrence,
                timezone_name=AUTO_PUBLISH_TIMEZONE,
                job_id="auto-publish",
            )
            if result.get("status") == "scheduled" and scheduler.get_job("auto-publish") is not None:
                return result

    return {"status": "not-configured", "message": "Automatic publish is enabled but no valid schedule was configured."}


def _run_scheduled_publish(model: str, provider: str = "azure") -> dict[str, Any]:
    """Trigger indexing then publish only when files changed; otherwise report no-op."""
    return run_indexation_then_publish(model=model, provider=provider)


def schedule_publish(
    *,
    model: str,
    provider: str = "azure",
    publish_at: datetime | str | None = None,
    cron: str | None = None,
    interval_minutes: int | None = None,
    user_time: str | None = None,
    recurrence: str | None = None,
    timezone_name: str = "UTC",
    job_id: str | None = None,
) -> dict[str, Any]:
    """Schedule a publish run as a one-off or recurring job.

    Supported forms:
    - one-time: publish_at or user_time
    - recurring: cron, interval_minutes, or user_time with recurrence='daily'|'weekly'
    """
    if not model or not str(model).strip():
        raise ValueError("A model is required to schedule publication.")

    effective_tz = _resolve_timezone(timezone_name)
    run_date = _normalize_datetime(publish_at, default_tz=effective_tz)

    if publish_at is None and user_time and recurrence in {None, "once", "one_time"}:
        run_date = _normalize_datetime(user_time, default_tz=effective_tz)

    if recurrence and recurrence.lower() in {"daily", "weekly"} and user_time:
        hour, minute = [int(part) for part in str(user_time).split(":", 1)]
        if recurrence.lower() == "daily":
            cron_expression = f"{minute} {hour} * * *"
        else:
            cron_expression = f"{minute} {hour} * * 0"
        cron = cron_expression

    recurrence_name = (recurrence or "").strip().lower()
    immediate_mode = recurrence_name in {"manual", "immediate"}

    if immediate_mode:
        publish_status = get_publish_status()
        indexing_status = get_indexation_status()
        processing_running = (
            bool(publish_status.get("running"))
            or bool(indexing_status.get("running"))
            or _is_schedule_transition_running()
        )
        if processing_running:
            raise ValueError("A publish workflow is already running.")
        recurrence = "once"
        run_date = datetime.now(timezone.utc)
        _reset_immediate_schedule_cleared_state()

    scheduler = _ensure_scheduler()
    resolved_job_id = str(job_id or _build_job_id())
    _clear_schedule_cancel_requested(resolved_job_id)
    schedule_for_value = run_date.isoformat() if run_date is not None else None
    job_kwargs: dict[str, Any] = {
        "id": resolved_job_id,
        "replace_existing": True,
        "kwargs": {
            "model": str(model),
            "provider": str(provider or "azure"),
            "scheduled_for": schedule_for_value,
            "immediate": bool(immediate_mode),
            "schedule_job_id": resolved_job_id,
        },
    }
    if cron:
        normalized_recurrence = str(recurrence or "").strip().lower()
        scheduler.add_job(
            run_indexation_then_publish,
            trigger=CronTrigger.from_crontab(cron, timezone=timezone_name),
            **job_kwargs,
        )
        when_value = cron
        recurrence_kind = normalized_recurrence if normalized_recurrence in {"daily", "weekly"} else "cron"
    elif interval_minutes is not None:
        scheduler.add_job(
            run_indexation_then_publish,
            trigger="interval",
            minutes=int(interval_minutes),
            **job_kwargs,
        )
        when_value = f"every {int(interval_minutes)} minutes"
        recurrence_kind = "interval"
    elif run_date is not None:
        scheduler.add_job(
            run_indexation_then_publish,
            trigger="date",
            run_date=run_date,
            **job_kwargs,
        )
        when_value = _format_report_datetime(run_date, timezone_name)
        recurrence_kind = "one_time"
    else:
        raise ValueError("A valid publish time, cron schedule, or interval must be provided.")

    persisted_record = _build_saved_schedule_record(
        job_id=resolved_job_id,
        model=str(model),
        provider=str(provider or "azure"),
        recurrence=recurrence_kind,
        schedule=when_value,
        run_at=schedule_for_value,
        cron=cron,
        interval_minutes=interval_minutes,
        timezone_name=timezone_name,
        immediate=immediate_mode,
    )
    _persist_schedule_entry(persisted_record)
    _emit_scheduler_status_event()

    schedule_result = {
        "status": "scheduled",
        "code": "publish.schedule.saved",
        "message_key": "publish.schedule.saved",
        "job_id": resolved_job_id,
        "model": str(model),
        "provider": str(provider or "azure"),
        "schedule": when_value,
        "recurrence": recurrence_kind,
        "message": "Schedule saved.",
        "persisted": persisted_record,
    }
    return schedule_result


def schedule_file_change_publish(
    *,
    model: str,
    provider: str = "azure",
    user_time: str | None = None,
    recurrence: str = "once",
    timezone_name: str = "UTC",
) -> dict[str, Any]:
    """Convenience helper for scheduling a publish after a file add/delete event."""
    return schedule_publish(
        model=model,
        provider=provider,
        user_time=user_time,
        recurrence=recurrence,
        timezone_name=timezone_name,
    )


def list_scheduled_publish_jobs() -> list[dict[str, Any]]:
    scheduler = _scheduler
    jobs: list[dict[str, Any]] = []

    if scheduler is not None:
        for job in scheduler.get_jobs():
            next_run_time = job.next_run_time
            trigger_text = str(job.trigger).lower()
            recurrence = "unknown"

            if "interval" in trigger_text:
                recurrence = "interval"
            elif "date" in trigger_text:
                recurrence = "one_time"
            elif "cron" in trigger_text:
                fields = getattr(job.trigger, "fields", []) or []
                day_of_week_field = next((field for field in fields if getattr(field, "name", "") == "day_of_week"), None)
                day_of_week = ""
                if day_of_week_field is not None:
                    expressions = getattr(day_of_week_field, "expressions", None) or []
                    if expressions:
                        day_of_week = ",".join(str(expression) for expression in expressions).strip().lower()
                    if not day_of_week:
                        day_of_week = str(day_of_week_field).strip().lower()
                    day_of_week = re.sub(r"^[^=]*=\s*", "", day_of_week).strip("'\" ")

                if day_of_week and day_of_week not in {"*", "0-6", "1-7", "mon-sun"}:
                    recurrence = "weekly"
                elif day_of_week in {"*", "0-6", "1-7", "mon-sun"}:
                    recurrence = "daily"
                else:
                    recurrence = "cron"

            if recurrence in {"manual", "immediate"}:
                recurrence = "one_time"

            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": _format_report_datetime(next_run_time) if next_run_time else None,
                "trigger": str(job.trigger),
                "recurrence": recurrence,
                "schedule": str(job.trigger),
                "immediate": bool(getattr(job, "kwargs", {}).get("immediate", False)),
            })

    try:
        persisted_entries = load_publish_schedule_entries()
    except Exception:
        persisted_entries = []

    persisted_by_id = {str(item.get("job_id") or item.get("id") or ""): item for item in persisted_entries if str(item.get("job_id") or item.get("id") or "").strip()}
    for item in jobs:
        item_id = str(item.get("id") or "").strip()
        persisted_entry = persisted_by_id.get(item_id)
        if isinstance(persisted_entry, dict):
            item["immediate"] = bool(persisted_entry.get("immediate"))
            persisted_by_id.pop(item_id, None)
        else:
            item["immediate"] = False
        if item_id in persisted_by_id:
            persisted_by_id.pop(item_id)

    for entry in persisted_by_id.values():
        next_run_text = entry.get("run_at") or entry.get("schedule")
        recurrence = str(entry.get("recurrence") or "one_time").strip().lower()
        if recurrence in {"manual", "immediate"}:
            recurrence = "one_time"
        jobs.append({
            "id": entry.get("job_id") or entry.get("id"),
            "name": entry.get("job_id") or entry.get("id"),
            "next_run_time": next_run_text,
            "trigger": recurrence,
            "recurrence": recurrence,
            "schedule": next_run_text,
            "immediate": bool(entry.get("immediate")),
        })

    relevant_jobs = [job for job in jobs if str(job.get("id") or "").strip() == "active-publish-schedule"]
    if not relevant_jobs:
        return []
    return relevant_jobs


def get_publish_scheduler_status() -> dict[str, Any]:
    publish_status = get_publish_status()
    indexing_status = get_indexation_status()

    publish_running = bool(publish_status.get("running"))
    indexing_running = bool(indexing_status.get("running"))
    transition_running = _is_schedule_transition_running()
    processing_running = publish_running or indexing_running or transition_running

    if not processing_running:
        try:
            persisted_entries = load_publish_schedule_entries()
        except Exception:
            persisted_entries = []
        immediate_job_ids = {
            str(item.get("job_id") or item.get("id") or "").strip()
            for item in persisted_entries
            if isinstance(item, dict) and bool(item.get("immediate"))
        }
        if _scheduler is not None:
            for job in _scheduler.get_jobs():
                try:
                    if bool(getattr(job, "kwargs", {}).get("immediate", False)):
                        immediate_job_ids.add(str(getattr(job, "id", "")).strip())
                except Exception:
                    continue
        for immediate_job_id in immediate_job_ids:
            if not immediate_job_id:
                continue
            active_job = _scheduler.get_job(immediate_job_id) if _scheduler is not None else None
            has_next_run = bool(active_job is not None and getattr(active_job, "next_run_time", None) is not None)
            if has_next_run:
                continue
            if _scheduler is not None and active_job is not None:
                try:
                    _scheduler.remove_job(immediate_job_id)
                except Exception:
                    pass
            _remove_persisted_schedule(immediate_job_id)
            _mark_immediate_schedule_cleared(immediate_job_id)

    active_jobs = list_scheduled_publish_jobs()
    immediate_schedule_cleared_at, immediate_schedule_cleared_job_id = _get_immediate_schedule_cleared_state()
    immediate_cleared_visible = bool(immediate_schedule_cleared_at) and not bool(active_jobs)

    return {
        "status": "ok",
        "active_schedule": active_jobs[0] if active_jobs else None,
        "has_active_schedule": bool(active_jobs),
        "publish_running": publish_running,
        "indexing_running": indexing_running,
        "transition_running": transition_running,
        "processing_running": processing_running,
        "immediate_schedule_cleared": immediate_cleared_visible,
        "immediate_schedule_cleared_at": immediate_schedule_cleared_at if immediate_cleared_visible else None,
        "immediate_schedule_cleared_job_id": immediate_schedule_cleared_job_id if immediate_cleared_visible else None,
    }


def _emit_scheduler_status_event() -> None:
    try:
        emit_workflow_event("schedule.state", get_publish_scheduler_status())
    except Exception:
        pass


def cancel_scheduled_publish(job_id: str) -> dict[str, Any]:
    scheduler = _scheduler
    target_id = str(job_id or "").strip()
    _mark_schedule_cancel_requested(target_id)

    indexation_cancel_result = request_indexation_cancel()
    publish_cancel_result = cancel_publish()

    persisted_before = []
    try:
        persisted_before = load_publish_schedule_entries()
    except Exception:
        persisted_before = []

    has_persisted_job = any(str(item.get("job_id") or item.get("id") or "").strip() == target_id for item in persisted_before)
    scheduler_has_job = scheduler is not None and scheduler.get_job(target_id) is not None

    if scheduler_has_job:
        scheduler.remove_job(target_id)

    _remove_persisted_schedule(target_id)

    persisted_after = []
    try:
        persisted_after = load_publish_schedule_entries()
    except Exception:
        persisted_after = []

    job_status = "cancelled" if scheduler_has_job or has_persisted_job or any(str(item.get("job_id") or item.get("id") or "").strip() == target_id for item in persisted_after) else "not_found"
    job_message = "Scheduled publish cancelled." if job_status == "cancelled" else "No scheduled publish was found for this id."

    result = {
        "status": job_status,
        "job_id": job_id,
        "message": job_message,
        "publish": publish_cancel_result,
        "indexation": indexation_cancel_result,
    }

    if scheduler is None:
        result["status"] = job_status if job_status == "cancelled" else "not_found"
        result["message"] = job_message

    _append_schedule_log("publish_schedule_cancelled", job_id=job_id, publish=publish_cancel_result, indexation=indexation_cancel_result)
    _emit_scheduler_status_event()
    return result


def clear_active_publish_schedule_on_cancel() -> dict[str, Any]:
    target_id = "active-publish-schedule"
    scheduler = _scheduler

    _mark_schedule_cancel_requested(target_id)

    persisted_before = []
    try:
        persisted_before = load_publish_schedule_entries()
    except Exception:
        persisted_before = []

    has_persisted_job = any(str(item.get("job_id") or item.get("id") or "").strip() == target_id for item in persisted_before)
    scheduler_has_job = scheduler is not None and scheduler.get_job(target_id) is not None

    if scheduler_has_job:
        try:
            scheduler.remove_job(target_id)
        except Exception:
            pass

    _remove_persisted_schedule(target_id)
    _mark_immediate_schedule_cleared(target_id)
    _emit_scheduler_status_event()

    return {
        "status": "cleared" if (scheduler_has_job or has_persisted_job) else "not_found",
        "job_id": target_id,
    }


__all__ = [
    "schedule_publish",
    "schedule_file_change_publish",
    "run_indexation_then_publish",
    "has_files_changed",
    "list_scheduled_publish_jobs",
    "get_publish_scheduler_status",
    "cancel_scheduled_publish",
    "clear_active_publish_schedule_on_cancel",
    "restore_persisted_publish_schedules",
    "shutdown_scheduler",
    "sync_debug_to_blob",
    "copy_debug_to_main_local",
    "restart_main_indexing",
    "sync_main_to_blob",
]
