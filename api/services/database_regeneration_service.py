"""Services to regenerate the local ChromaDB knowledge base.

This module wraps scripts in api/db_pipeline and exposes step-based
execution that mirrors build-database.bat.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
import os
import shutil
import subprocess
import sys
import threading
import time

from api.services.blob_storage_service import (
    get_blob_container_name,
    get_blob_prefix,
    has_blob_storage_config,
    sync_local_directory_to_blob,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
KB_ROOT = REPO_ROOT / "nutrifaq-dbase"
SCRIPTS_DIR = REPO_ROOT / "api" / "db_pipeline"
CHROMA_DB_ROOT = KB_ROOT / "chroma_db"
LOCAL_SERVER_SQLITE_COPY = REPO_ROOT / "local-server" / "chroma.sqlite3"


_regen_state_lock = threading.Lock()
_regen_state: Dict[str, object] = {
    "running": False,
    "cancel_requested": False,
    "current_step": None,
    "active_process": None,
}


@dataclass
class StepDefinition:
    key: str
    description: str
    script_name: str
    cwd: Path
    args: List[str]


def _python_executable() -> str:
    return sys.executable or "python"


def _start_regeneration() -> bool:
    with _regen_state_lock:
        if bool(_regen_state.get("running")):
            return False
        _regen_state["running"] = True
        _regen_state["cancel_requested"] = False
        _regen_state["current_step"] = None
        _regen_state["active_process"] = None
        return True


def _finish_regeneration() -> None:
    with _regen_state_lock:
        _regen_state["running"] = False
        _regen_state["cancel_requested"] = False
        _regen_state["current_step"] = None
        _regen_state["active_process"] = None


def _set_current_step(step_key: str | None) -> None:
    with _regen_state_lock:
        _regen_state["current_step"] = step_key


def _set_active_process(process: subprocess.Popen[str] | None) -> None:
    with _regen_state_lock:
        _regen_state["active_process"] = process


def _is_cancel_requested() -> bool:
    with _regen_state_lock:
        return bool(_regen_state.get("cancel_requested"))


def request_regeneration_cancel() -> Dict[str, object]:
    with _regen_state_lock:
        if not bool(_regen_state.get("running")):
            return {
                "status": "idle",
                "message": "No regeneration is currently running.",
            }

        _regen_state["cancel_requested"] = True
        process = _regen_state.get("active_process")
        step = _regen_state.get("current_step")

    if isinstance(process, subprocess.Popen) and process.poll() is None:
        try:
            process.terminate()
        except Exception:
            pass

    return {
        "status": "cancelling",
        "message": "Cancellation requested.",
        "current_step": step,
    }


def get_regeneration_status() -> Dict[str, object]:
    with _regen_state_lock:
        return {
            "running": bool(_regen_state.get("running")),
            "cancel_requested": bool(_regen_state.get("cancel_requested")),
            "current_step": _regen_state.get("current_step"),
        }


def _step_definitions() -> Dict[str, StepDefinition]:
    return {
        "extract_docx": StepDefinition(
            key="extract_docx",
            description="Extract text from DOCX files into nutrifaq-dbase/transcripts.",
            script_name="extract_docx.py",
            cwd=KB_ROOT,
            args=[],
        ),
        "extract_references": StepDefinition(
            key="extract_references",
            description="Extract bibliography and PMID references into nutrifaq-dbase/references.json.",
            script_name="extract_references.py",
            cwd=KB_ROOT,
            args=[],
        ),
        "generate_transcripts_json": StepDefinition(
            key="generate_transcripts_json",
            description="Build transcripts_chromadb.json from transcripts/documents.",
            script_name="generate_transcripts_json.py",
            cwd=KB_ROOT,
            args=[str(KB_ROOT)],
        ),
        "index_chromadb_json": StepDefinition(
            key="index_chromadb_json",
            description="Index transcripts_chromadb.json into nutrifaq-dbase/chroma_db.",
            script_name="index_chromadb_json.py",
            cwd=KB_ROOT,
            args=[str(KB_ROOT)],
        ),
    }


def list_regeneration_steps() -> List[Dict[str, str]]:
    steps = _step_definitions()
    return [
        {"key": steps[key].key, "description": steps[key].description}
        for key in [
            "extract_docx",
            "extract_references",
            "generate_transcripts_json",
            "index_chromadb_json",
        ]
    ]


def _run_step(step_key: str) -> Dict[str, object]:
    steps = _step_definitions()
    if step_key not in steps:
        return {
            "status": "error",
            "step": step_key,
            "message": f"Unknown step '{step_key}'.",
            "available_steps": sorted(steps.keys()),
        }

    step = steps[step_key]
    script_path = SCRIPTS_DIR / step.script_name
    if not script_path.exists():
        return {
            "status": "error",
            "step": step.key,
            "message": f"Missing script: {script_path}",
        }

    command = [_python_executable(), str(script_path), *step.args]
    started = time.time()
    process = subprocess.Popen(
        command,
        cwd=str(step.cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    _set_current_step(step.key)
    _set_active_process(process)

    was_cancelled = False
    while process.poll() is None:
        if _is_cancel_requested():
            was_cancelled = True
            try:
                process.terminate()
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            except Exception:
                pass
            break
        time.sleep(0.25)

    stdout, stderr = process.communicate()
    _set_active_process(None)

    duration_seconds = round(time.time() - started, 2)

    if was_cancelled:
        return {
            "status": "cancelled",
            "step": step.key,
            "description": step.description,
            "command": " ".join(command),
            "cwd": str(step.cwd),
            "return_code": process.returncode,
            "duration_seconds": duration_seconds,
            "stdout": stdout,
            "stderr": stderr,
            "message": "Cancelled by user.",
        }

    return {
        "status": "ok" if process.returncode == 0 else "error",
        "step": step.key,
        "description": step.description,
        "command": " ".join(command),
        "cwd": str(step.cwd),
        "return_code": process.returncode,
        "duration_seconds": duration_seconds,
        "stdout": stdout,
        "stderr": stderr,
    }


def run_extract_docx_step() -> Dict[str, object]:
    """Run DOCX to transcript extraction."""
    return _run_step("extract_docx")


def run_extract_references_step() -> Dict[str, object]:
    """Run references extraction from documents."""
    return _run_step("extract_references")


def run_generate_transcripts_json_step() -> Dict[str, object]:
    """Generate transcripts_chromadb.json."""
    return _run_step("generate_transcripts_json")


def run_index_chromadb_json_step() -> Dict[str, object]:
    """Index transcripts_chromadb.json into ChromaDB."""
    return _run_step("index_chromadb_json")


def run_regeneration_step(step_key: str) -> Dict[str, object]:
    step_services = {
        "extract_docx": run_extract_docx_step,
        "extract_references": run_extract_references_step,
        "generate_transcripts_json": run_generate_transcripts_json_step,
        "index_chromadb_json": run_index_chromadb_json_step,
    }
    runner = step_services.get(step_key)
    if not runner:
        return {
            "status": "error",
            "step": step_key,
            "message": f"Unknown step '{step_key}'.",
            "available_steps": sorted(step_services.keys()),
        }
    return runner()


def _save_chromadb_to_blob_and_local_copy(
    *,
    root_folder: str | None = None,
    container_name: str | None = None,
) -> Dict[str, object]:
    if not CHROMA_DB_ROOT.exists():
        return {
            "status": "error",
            "message": f"ChromaDB directory not found: {CHROMA_DB_ROOT}",
        }

    sqlite_path = CHROMA_DB_ROOT / "chroma.sqlite3"
    if not sqlite_path.exists():
        return {
            "status": "error",
            "message": f"SQLite database file not found: {sqlite_path}",
        }

    blob_result: Dict[str, object]
    if has_blob_storage_config():
        resolved_root = (root_folder or get_blob_prefix()).strip("/")
        destination_prefix = f"{resolved_root}/chroma_db"
        resolved_container = (
            (container_name or "").strip()
            or os.getenv("AZURE_STORAGE_CONTAINER")
            or get_blob_container_name()
        )
        uploaded = sync_local_directory_to_blob(
            CHROMA_DB_ROOT,
            destination_prefix,
            overwrite=True,
            container_name=resolved_container,
        )
        blob_result = {
            "status": "ok",
            "container": resolved_container,
            "root_folder": resolved_root,
            "destination_prefix": destination_prefix,
            "uploaded_files_count": len(uploaded),
        }
    else:
        blob_result = {
            "status": "skipped",
            "message": "Azure Blob Storage not configured; upload skipped.",
        }

    LOCAL_SERVER_SQLITE_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sqlite_path, LOCAL_SERVER_SQLITE_COPY)

    return {
        "status": "ok",
        "blob_sync": blob_result,
        "local_sqlite_copy": str(LOCAL_SERVER_SQLITE_COPY),
    }


def run_full_regeneration(
    include_extract_docx: bool = False,
    include_extract_references: bool = False,
    root_folder: str | None = None,
    container_name: str | None = None,
) -> Dict[str, object]:
    """Run the end-to-end regeneration sequence.

    The core sequence mirrors build-database.bat:
    1) generate_transcripts_json
    2) index_chromadb_json

    Optional preprocessing steps can be added before it.
    """

    if not _start_regeneration():
        return {
            "status": "busy",
            "message": "A regeneration is already running.",
        }

    pipeline: List[str] = []
    if include_extract_docx:
        pipeline.append("extract_docx")
    if include_extract_references:
        pipeline.append("extract_references")

    pipeline.extend(["generate_transcripts_json", "index_chromadb_json"])

    results: List[Dict[str, object]] = []
    step_services = {
        "extract_docx": run_extract_docx_step,
        "extract_references": run_extract_references_step,
        "generate_transcripts_json": run_generate_transcripts_json_step,
        "index_chromadb_json": run_index_chromadb_json_step,
    }

    try:
        for step_key in pipeline:
            if _is_cancel_requested():
                return {
                    "status": "cancelled",
                    "message": "Regeneration cancelled by user.",
                    "steps": results,
                }

            step_result = step_services[step_key]()
            results.append(step_result)
            if step_result.get("status") == "cancelled":
                return {
                    "status": "cancelled",
                    "message": f"Pipeline cancelled at step '{step_key}'.",
                    "steps": results,
                }
            if step_result.get("status") != "ok":
                return {
                    "status": "error",
                    "message": f"Pipeline stopped at step '{step_key}'.",
                    "steps": results,
                }

        if _is_cancel_requested():
            return {
                "status": "cancelled",
                "message": "Regeneration cancelled before post-sync.",
                "steps": results,
            }

        publish_result = _save_chromadb_to_blob_and_local_copy(
            root_folder=root_folder,
            container_name=container_name,
        )
        if publish_result.get("status") != "ok":
            return {
                "status": "error",
                "message": "Pipeline completed but post-sync failed.",
                "steps": results,
                "post_sync": publish_result,
            }

        return {
            "status": "success",
            "message": "Database regeneration pipeline completed.",
            "steps": results,
            "post_sync": publish_result,
        }
    finally:
        _finish_regeneration()
