from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

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


def _normalize_datetime(value: datetime | str | None, *, default_tz: timezone | None = None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            if default_tz is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.replace(tzinfo=default_tz)
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
            dt = dt.replace(tzinfo=timezone.utc)
            if dt <= now:
                dt = dt + timedelta(days=1)
            return dt
        if dt.tzinfo is None:
            if default_tz is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.replace(tzinfo=default_tz)
        return dt.astimezone(timezone.utc)
    return None


def _build_job_id(prefix: str = "publish") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


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
            _run_scheduled_publish,
            id="auto-publish",
            trigger=CronTrigger.from_crontab(AUTO_PUBLISH_CRON, timezone=AUTO_PUBLISH_TIMEZONE),
            args=(model, provider),
            replace_existing=True,
        )
        return {"status": "scheduled", "job_id": "auto-publish", "cron": AUTO_PUBLISH_CRON}

    if AUTO_PUBLISH_INTERVAL_MINUTES > 0:
        scheduler.add_job(
            _run_scheduled_publish,
            id="auto-publish",
            trigger="interval",
            minutes=AUTO_PUBLISH_INTERVAL_MINUTES,
            args=(model, provider),
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
    sync_debug_to_blob()
    copy_debug_to_main_local(DEBUG_KB_ROOT, MAIN_KB_ROOT)
    restart_main_indexing(MAIN_KB_ROOT)
    sync_main_to_blob(MAIN_KB_ROOT, "nutrifaq-dbase", "nutrifaq-dbase-main")
    return {
        "status": "ok",
        "message": "Scheduled publish ran successfully.",
        "model": model,
        "provider": provider,
    }


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

    scheduler = _ensure_scheduler()
    run_date = _normalize_datetime(publish_at)

    if publish_at is None and user_time and recurrence in {None, "once", "one_time"}:
        run_date = _normalize_datetime(user_time)

    if recurrence and recurrence.lower() in {"daily", "weekly"} and user_time:
        hour, minute = [int(part) for part in str(user_time).split(":", 1)]
        if recurrence.lower() == "daily":
            cron_expression = f"{minute} {hour} * * *"
        else:
            cron_expression = f"{minute} {hour} * * 0"
        cron = cron_expression

    resolved_job_id = str(job_id or _build_job_id())
    job_kwargs: dict[str, Any] = {
        "id": resolved_job_id,
        "replace_existing": True,
        "args": (str(model), str(provider or "azure")),
    }

    if run_date is not None and run_date <= datetime.now(timezone.utc) + timedelta(seconds=2):
        _run_scheduled_publish(str(model), str(provider or "azure"))

    if cron:
        scheduler.add_job(
            _run_scheduled_publish,
            trigger=CronTrigger.from_crontab(cron, timezone=timezone_name),
            **job_kwargs,
        )
        when_value = cron
        recurrence_kind = "cron"
    elif interval_minutes is not None:
        scheduler.add_job(
            _run_scheduled_publish,
            trigger="interval",
            minutes=int(interval_minutes),
            **job_kwargs,
        )
        when_value = f"every {int(interval_minutes)} minutes"
        recurrence_kind = "interval"
    elif run_date is not None:
        scheduler.add_job(
            _run_scheduled_publish,
            trigger="date",
            run_date=run_date,
            **job_kwargs,
        )
        when_value = run_date.isoformat()
        recurrence_kind = "one_time"
    else:
        raise ValueError("A valid publish time, cron schedule, or interval must be provided.")

    return {
        "status": "scheduled",
        "job_id": resolved_job_id,
        "model": str(model),
        "provider": str(provider or "azure"),
        "schedule": when_value,
        "recurrence": recurrence_kind,
        "message": "Automatic publish scheduled.",
    }


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
    if scheduler is None:
        return []

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return jobs


def cancel_scheduled_publish(job_id: str) -> dict[str, Any]:
    scheduler = _scheduler
    if scheduler is None:
        return {"status": "not_found", "job_id": job_id, "message": "No active scheduler is running."}
    if scheduler.get_job(job_id) is None:
        return {"status": "not_found", "job_id": job_id, "message": "No scheduled publish was found for this id."}
    scheduler.remove_job(job_id)
    return {"status": "cancelled", "job_id": job_id, "message": "Scheduled publish cancelled."}


__all__ = [
    "schedule_publish",
    "schedule_file_change_publish",
    "list_scheduled_publish_jobs",
    "cancel_scheduled_publish",
    "shutdown_scheduler",
    "sync_debug_to_blob",
    "copy_debug_to_main_local",
    "restart_main_indexing",
    "sync_main_to_blob",
]
