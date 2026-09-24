"""Services to regenerate the local ChromaDB knowledge base.

This module wraps scripts in api/db_pipeline and exposes step-based
execution that mirrors build-database.bat.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List
import os
import json
import re
import shutil
import subprocess
import sys
import threading
import time

from api.services.blob_storage_service import (
    get_blob_container_name,
    get_blob_prefix,
    has_blob_storage_config,
    sync_blob_prefix_to_local,
    sync_local_directory_to_blob,
    upload_file_to_blob,
)
from api.services.query_chromadb import get_debug_local_kb_root_folder


REPO_ROOT = Path(__file__).resolve().parents[2]
KB_ROOT = REPO_ROOT / "nutrifaq-dbase"
DEBUG_KB_ROOT = REPO_ROOT / get_debug_local_kb_root_folder()
SCRIPTS_DIR = REPO_ROOT / "api" / "db_pipeline"
CHROMA_DB_ROOT = KB_ROOT / "chroma_db"
LOCAL_SERVER_SQLITE_COPY = DEBUG_KB_ROOT / "chroma.sqlite3"
REGEN_PROGRESS_PATH = DEBUG_KB_ROOT / "regeneration_progress.json"

STEP_ORDER: list[str] = [
    "extract_docx",
    "extract_references",
    "generate_transcripts_json",
    "index_chromadb_json",
    "generate_questions",
]

STEP_LABELS: dict[str, str] = {
    "extract_docx": "Extraction des documents",
    "extract_references": "Extraction des references",
    "generate_transcripts_json": "Generation des transcripts",
    "generate_questions": "Generation des questions",
    "index_chromadb_json": "Indexation ChromaDB",
}


def _sanitize_question_topic(text: str, *, max_words: int = 8) -> str:
    """Build a compact topic phrase from transcript text."""
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return "ce document"

    # Prefer the first sentence-like segment to keep topic readable.
    sentence = re.split(r"[\.!?\n]", normalized, maxsplit=1)[0].strip()
    source = sentence or normalized
    words = source.split()
    short = " ".join(words[:max_words]).strip(" ,;:-")
    return short if short else "ce document"


def _build_questions_for_document(topic: str, question_count: int) -> list[str]:
    """Generate deterministic question variants for one document topic."""
    templates = [
        "Quels sont les points cles de {topic} ?",
        "Quelles recommandations pratiques ressortent de {topic} ?",
        "Quels risques ou limites sont mentionnes dans {topic} ?",
        "Comment appliquer les informations de {topic} au quotidien ?",
        "Quels elements sont les plus importants a retenir sur {topic} ?",
        "Quelles questions restent ouvertes concernant {topic} ?",
    ]
    questions: list[str] = []
    for idx in range(question_count):
        tpl = templates[idx % len(templates)]
        questions.append(tpl.format(topic=topic))
    return questions


def _extract_json_array_from_text(text: str) -> list[str]:
    """Extract a JSON array of strings from raw model output."""
    if not text:
        return []

    stripped = text.strip()
    # Handle markdown fenced JSON blocks.
    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    candidate = fence_match.group(1) if fence_match else stripped

    if not fence_match:
        bracket_match = re.search(r"\[.*\]", candidate, flags=re.DOTALL)
        if bracket_match:
            candidate = bracket_match.group(0)

    try:
        payload = json.loads(candidate)
    except Exception:
        return []

    if not isinstance(payload, list):
        return []

    return [str(item).strip() for item in payload if isinstance(item, (str, int, float)) and str(item).strip()]


def _build_llm_prompt_for_questions(text_excerpt: str, topic: str, question_count: int) -> str:
    return (
        "Tu es un assistant de creation de jeux de questions en nutrition. "
        "Genere exactement {count} questions pertinentes pour un document. "
        "Retourne uniquement un tableau JSON valide de chaines, sans markdown, sans texte additionnel.\n\n"
        "Sujet detecte: {topic}\n"
        "Extrait du document:\n{text}\n\n"
        "Contraintes:\n"
        "- Questions en francais.\n"
        "- Une question par element du tableau.\n"
        "- Pas de numerotation ni prefixe.\n"
        "- Questions claires, actionnables et specifiques au contenu."
    ).format(count=question_count, topic=topic, text=text_excerpt)


def generate_questions_from_transcripts_json(
    *,
    question_count: int = 3,
    source_root_folder: str | None = None,
    target_container_name: str | None = None,
    target_root_folder: str | None = None,
    output_filename: str = "generated_questions.json",
) -> Dict[str, object]:
    """Generate N questions per document from transcripts_chromadb.json to local JSON."""
    if question_count < 1:
        return {"status": "error", "message": "question_count must be >= 1."}

    local_root_folder = (source_root_folder or get_debug_local_kb_root_folder()).strip("/")
    local_kb_root = REPO_ROOT / local_root_folder
    script_path = SCRIPTS_DIR / "generate_questions_json.py"
    if not script_path.exists():
        return {
            "status": "error",
            "message": f"Missing script: {script_path}",
        }

    command = [
        _python_executable(),
        str(script_path),
        str(local_kb_root),
        str(question_count),
    ]

    process = subprocess.run(
        command,
        cwd=str(local_kb_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if process.returncode != 0:
        return {
            "status": "error",
            "message": "Question generation script failed.",
            "command": " ".join(command),
            "stdout": process.stdout,
            "stderr": process.stderr,
            "return_code": process.returncode,
        }

    output_path = local_kb_root / output_filename
    if not output_path.exists():
        return {
            "status": "error",
            "message": f"Generated file not found: {output_path}",
            "command": " ".join(command),
            "stdout": process.stdout,
            "stderr": process.stderr,
        }

    total_documents = None
    llm_failures = None
    try:
        with open(output_path, "r", encoding="utf-8") as handle:
            output_data = json.load(handle)
        total_documents = output_data.get("total_documents")
        llm_failures = output_data.get("llm_failures")
    except Exception:
        pass

    return {
        "status": "ok",
        "message": "Questions generated successfully.",
        "question_count_per_document": question_count,
        "total_documents": total_documents,
        "llm_failures": llm_failures,
        "local_output_path": str(output_path),
        "stdout": process.stdout,
        "stderr": process.stderr,
    }


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
        _regen_state["progress_value"] = None
        _regen_state["progress_total"] = None
        _regen_state["progress_kind"] = None
        return True


def _finish_regeneration() -> None:
    with _regen_state_lock:
        _regen_state["running"] = False
        _regen_state["cancel_requested"] = False
        _regen_state["current_step"] = None
        _regen_state["active_process"] = None
        _regen_state["progress_value"] = None
        _regen_state["progress_total"] = None
        _regen_state["progress_kind"] = None


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


def _write_progress_snapshot(step_key: str, value: int, total: int, kind: str) -> None:
    target_path = REGEN_PROGRESS_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "step": step_key,
        "kind": kind,
        "value": int(value),
        "total": int(total),
        "updated_at": time.time(),
    }
    with target_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)


def _read_progress_snapshot() -> Dict[str, object]:
    if not REGEN_PROGRESS_PATH.exists():
        return {}
    try:
        with REGEN_PROGRESS_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def get_regeneration_status() -> Dict[str, object]:
    snapshot = _read_progress_snapshot()
    with _regen_state_lock:
        current_step = _regen_state.get("current_step")
        step_key = str(current_step) if current_step else None
        step_index = STEP_ORDER.index(step_key) + 1 if step_key in STEP_ORDER else None
        total_steps = len(STEP_ORDER)
        progress_percent = None
        progress_value = _regen_state.get("progress_value")
        progress_total = _regen_state.get("progress_total")
        progress_kind = _regen_state.get("progress_kind")

        if step_key in {"generate_questions", "index_chromadb_json"} and snapshot:
            if snapshot.get("step") == step_key:
                progress_value = snapshot.get("value", progress_value)
                progress_total = snapshot.get("total", progress_total)
                progress_kind = snapshot.get("kind", progress_kind or ("questions" if step_key == "generate_questions" else "tokens"))
                if isinstance(progress_total, (int, float)) and progress_total > 0 and isinstance(progress_value, (int, float)):
                    progress_percent = round((float(progress_value) / float(progress_total)) * 100, 1)

        if progress_percent is None and step_index is not None and total_steps > 0:
            progress_percent = round((step_index / total_steps) * 100, 1)

        if isinstance(progress_value, (int, float)) and isinstance(progress_total, (int, float)) and progress_total > 0:
            progress_percent = round((float(progress_value) / float(progress_total)) * 100, 1)

        if progress_total is not None:
            progress_total = int(progress_total)
        if progress_value is not None:
            progress_value = int(progress_value)

        _regen_state["progress_value"] = progress_value
        _regen_state["progress_total"] = progress_total
        _regen_state["progress_kind"] = progress_kind

        return {
            "running": bool(_regen_state.get("running")),
            "cancel_requested": bool(_regen_state.get("cancel_requested")),
            "current_step": step_key,
            "current_step_label": STEP_LABELS.get(step_key) if step_key else None,
            "step_index": step_index,
            "total_steps": total_steps,
            "progress_value": progress_value,
            "progress_total": progress_total,
            "progress_kind": progress_kind,
            "progress_percent": progress_percent,
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
        "generate_questions": StepDefinition(
            key="generate_questions",
            description="Generate per-document questions from transcripts_chromadb.json.",
            script_name="generate_questions_json.py",
            cwd=KB_ROOT,
            args=[str(KB_ROOT), "3"],
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
    listed_steps: list[dict[str, str]] = []
    for key in STEP_ORDER:
        if key in steps:
            listed_steps.append({"key": steps[key].key, "description": steps[key].description})
    return listed_steps


def _run_step(step_key: str) -> Dict[str, object]:
    return _run_step_with_env(step_key)


def _run_step_with_env(
    step_key: str,
    env_overrides: Dict[str, str] | None = None,
    step_args_override: List[str] | None = None,
    cwd_override: Path | None = None,
) -> Dict[str, object]:
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

    command_args = step_args_override if step_args_override is not None else step.args
    command = [_python_executable(), str(script_path), *command_args]
    started = time.time()
    process_env = os.environ.copy()
    if env_overrides:
        process_env.update({k: str(v) for k, v in env_overrides.items() if v is not None})

    process = subprocess.Popen(
        command,
        cwd=str(cwd_override or step.cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=process_env,
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
            "cwd": str(cwd_override or step.cwd),
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
        "cwd": str(cwd_override or step.cwd),
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


def run_generate_questions_step(
    *,
    question_count: int = 3,
    source_root_folder: str | None = None,
    target_container_name: str | None = None,
    target_root_folder: str | None = None,
) -> Dict[str, object]:
    """Generate per-document questions JSON and sync it to blob."""
    started = time.time()
    result = generate_questions_from_transcripts_json(
        question_count=question_count,
        source_root_folder=source_root_folder,
        target_container_name=target_container_name,
        target_root_folder=target_root_folder,
    )
    duration_seconds = round(time.time() - started, 2)

    return {
        "status": "ok" if result.get("status") == "ok" else "error",
        "step": "generate_questions",
        "description": "Generate per-document questions from transcripts and upload JSON to blob.",
        "duration_seconds": duration_seconds,
        "details": result,
    }


def run_regeneration_step(step_key: str) -> Dict[str, object]:
    step_services = {
        "extract_docx": run_extract_docx_step,
        "extract_references": run_extract_references_step,
        "generate_transcripts_json": run_generate_transcripts_json_step,
        "generate_questions": lambda: run_generate_questions_step(),
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
    local_kb_root: Path,
    root_folder: str | None = None,
    container_name: str | None = None,
) -> Dict[str, object]:
    local_chroma_root = local_kb_root / "chroma_db"

    if not local_chroma_root.exists():
        return {
            "status": "error",
            "message": f"ChromaDB directory not found: {local_chroma_root}",
        }

    sqlite_path = local_chroma_root / "chroma.sqlite3"
    if not sqlite_path.exists():
        return {
            "status": "error",
            "message": f"SQLite database file not found: {sqlite_path}",
        }

    blob_result: Dict[str, object]
    if has_blob_storage_config():
        resolved_root = (
            (root_folder or "").strip()
            or os.getenv("AZURE_KB_DEBUG_BLOB_PREFIX", "").strip()
            or "nutrifaq-dbase-main"
        ).strip("/")
        resolved_container = (
            (container_name or "").strip()
            or os.getenv("AZURE_KB_DEBUG_BLOB_CONTAINER")
            or os.getenv("AZURE_STORAGE_CONTAINER")
            or get_blob_container_name()
        )

        # Upload the full local KB root back to blob after indexing. This ensures local
        # debug work is preserved and the debug blob stays in sync with the regenerated data.
        root_uploads = sync_local_directory_to_blob(
            local_kb_root,
            resolved_root,
            overwrite=True,
            container_name=resolved_container,
        )

        destination_prefix = f"{resolved_root}/chroma_db"
        uploaded = sync_local_directory_to_blob(
            local_chroma_root,
            destination_prefix,
            overwrite=True,
            container_name=resolved_container,
        )

        artifact_files = [
            "generated_questions.json",
            "transcripts_chromadb.json",
            "references.json",
        ]
        artifact_uploads: list[dict[str, object]] = []
        for artifact_name in artifact_files:
            artifact_path = local_kb_root / artifact_name
            if not artifact_path.exists() or not artifact_path.is_file():
                artifact_uploads.append(
                    {
                        "file": artifact_name,
                        "status": "missing",
                    }
                )
                continue

            artifact_blob_name = f"{resolved_root}/{artifact_name}"
            upload_file_to_blob(
                blob_name=artifact_blob_name,
                source_path=artifact_path,
                overwrite=True,
                container_name=resolved_container,
            )
            artifact_uploads.append(
                {
                    "file": artifact_name,
                    "status": "ok",
                    "blob_name": artifact_blob_name,
                }
            )

        blob_result = {
            "status": "ok",
            "container": resolved_container,
            "root_folder": resolved_root,
            "destination_prefix": destination_prefix,
            "uploaded_files_count": len(root_uploads),
            "chroma_uploaded_files_count": len(uploaded),
            "artifact_uploads": artifact_uploads,
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


def _has_readable_documents(local_kb_root: Path) -> bool:
    """Return True when documents/ contains at least one readable source file."""
    documents_dir = local_kb_root / "documents"
    if not documents_dir.exists() or not documents_dir.is_dir():
        return False

    allowed_extensions = {".docx", ".json", ".txt", ".md"}

    for path in documents_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.name.startswith("~$"):
            continue
        if path.suffix.lower() not in allowed_extensions:
            continue
        return True

    return False


def run_full_regeneration(
    include_extract_docx: bool = False,
    include_extract_references: bool = False,
    root_folder: str | None = None,
    container_name: str | None = None,
) -> Dict[str, object]:
    """Run the end-to-end regeneration sequence.

    The core sequence mirrors build-database.bat with question generation:
    1) generate_transcripts_json
    2) index_chromadb_json
    3) generate_questions

    Optional preprocessing steps can be added before it.
    """

    if not _start_regeneration():
        return {
            "status": "busy",
            "message": "A regeneration is already running.",
        }

    resolved_root_folder = (
        (root_folder or "").strip()
        or os.getenv("AZURE_KB_DEBUG_BLOB_PREFIX", "").strip()
        or "nutrifaq-dbase-main"
    ).strip("/")
    resolved_container_name = (
        (container_name or "").strip()
        or os.getenv("AZURE_KB_DEBUG_BLOB_CONTAINER", "").strip()
        or "nutrifaq-knowledge-base-debug"
    )
    resolved_local_kb_root = REPO_ROOT / resolved_root_folder

    try:
        if not _has_readable_documents(resolved_local_kb_root):
            return {
                "status": "error",
                "message": "No document to read in documents/. Please upload at least one document before running regeneration.",
                "effective_target": {
                    "container": resolved_container_name,
                    "root_folder": resolved_root_folder,
                },
            }

        pipeline: List[str] = []
        if include_extract_docx:
            pipeline.append("extract_docx")
        if include_extract_references:
            pipeline.append("extract_references")
    
        pipeline.extend(["generate_transcripts_json", "index_chromadb_json", "generate_questions"])

        results: List[Dict[str, object]] = []
        regen_env = {
            "AZURE_KB_BLOB_PREFIX": resolved_root_folder,
            "AZURE_STORAGE_CONTAINER": resolved_container_name,
            "AZURE_KB_BLOB_CONTAINER": resolved_container_name,
            "NUTRIFAQ_KB_ROOT": str(resolved_local_kb_root),
        }

        step_services = {
            "extract_docx": lambda: _run_step_with_env(
                "extract_docx",
                env_overrides=regen_env,
                step_args_override=[str(resolved_local_kb_root)],
                cwd_override=resolved_local_kb_root,
            ),
            "extract_references": lambda: _run_step_with_env(
                "extract_references",
                env_overrides=regen_env,
                step_args_override=[str(resolved_local_kb_root)],
                cwd_override=resolved_local_kb_root,
            ),
            "generate_transcripts_json": lambda: _run_step_with_env(
                "generate_transcripts_json",
                env_overrides=regen_env,
                step_args_override=[str(resolved_local_kb_root)],
                cwd_override=resolved_local_kb_root,
            ),
            "generate_questions": lambda: run_generate_questions_step(
                question_count=3,
                source_root_folder=resolved_root_folder,
                target_container_name=resolved_container_name,
                target_root_folder=resolved_root_folder,
            ),
            "index_chromadb_json": lambda: _run_step_with_env(
                "index_chromadb_json",
                env_overrides=regen_env,
                step_args_override=[str(resolved_local_kb_root)],
                cwd_override=resolved_local_kb_root,
            ),
        }

        for step_key in pipeline:
            _set_current_step(step_key)
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
                "message": "Regeneration cancelled.",
                "steps": results,
            }

        return {
            "status": "success",
            "message": "Database regeneration pipeline completed.",
            "effective_target": {
                "container": resolved_container_name,
                "root_folder": resolved_root_folder,
            },
            "steps": results,
        }
    finally:
        _finish_regeneration()
