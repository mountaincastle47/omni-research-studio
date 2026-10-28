"""`.omni` project persistence: a compressed zip package holding the complete research workspace."""

from __future__ import annotations

import datetime
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.document_loader import SourceDocument

PROJECT_EXTENSION = ".omni"
FORMAT_VERSION = 1
APP_NAME = "OmniResearch Studio"

MANIFEST_NAME = "manifest.json"
AUDIO_ARCHIVE_NAME = "audio/audio_briefing.mp3"

_REPORT_FILES = {
    "synthesis_original": "reports/synthesis_en.md",
    "synthesis_translated": "reports/synthesis_ko.md",
    "perspective_original": "reports/perspectives_en.md",
    "perspective_translated": "reports/perspectives_ko.md",
    "audio_script": "reports/audio_script.txt",
}


class ProjectFormatError(Exception):
    """Raised when a file is not a valid `.omni` project package."""


@dataclass
class WorkspaceTabState:
    """State for an individual research workspace tab."""

    tab_id: str = ""
    title: str = "Research Workspace"
    topic: str = ""
    query: str = ""
    synthesis_original: str = ""
    synthesis_translated: str = ""
    synthesis_showing_translation: bool = False
    perspective_original: str = ""
    perspective_translated: str = ""
    perspective_showing_translation: bool = False
    audio_directive: str = ""
    audio_script_raw: str = ""
    audio_title: str = ""
    audio_mp3_path: Optional[str] = None
    chat_history: List[Dict[str, str]] = field(default_factory=list)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    grounding_refs: List[Dict[str, Any]] = field(default_factory=list)
    perspectives: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tab_id": self.tab_id,
            "title": self.title,
            "topic": self.topic,
            "query": self.query,
            "synthesis_original": self.synthesis_original,
            "synthesis_translated": self.synthesis_translated,
            "synthesis_showing_translation": self.synthesis_showing_translation,
            "perspective_original": self.perspective_original,
            "perspective_translated": self.perspective_translated,
            "perspective_showing_translation": self.perspective_showing_translation,
            "audio_directive": self.audio_directive,
            "audio_script_raw": self.audio_script_raw,
            "audio_title": self.audio_title,
            "audio_mp3_path": self.audio_mp3_path,
            "chat_history": self.chat_history,
            "citations": self.citations,
            "grounding_refs": self.grounding_refs,
            "perspectives": {k: dict(v) for k, v in self.perspectives.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkspaceTabState":
        return cls(
            tab_id=str(data.get("tab_id", "")),
            title=str(data.get("title", "Research Workspace")),
            topic=str(data.get("topic", "")),
            query=str(data.get("query", "")),
            synthesis_original=str(data.get("synthesis_original", "")),
            synthesis_translated=str(data.get("synthesis_translated", "")),
            synthesis_showing_translation=bool(data.get("synthesis_showing_translation", False)),
            perspective_original=str(data.get("perspective_original", "")),
            perspective_translated=str(data.get("perspective_translated", "")),
            perspective_showing_translation=bool(data.get("perspective_showing_translation", False)),
            audio_directive=str(data.get("audio_directive", "")),
            audio_script_raw=str(data.get("audio_script_raw", "")),
            audio_title=str(data.get("audio_title", "")),
            audio_mp3_path=data.get("audio_mp3_path"),
            chat_history=[dict(c) for c in data.get("chat_history", []) if isinstance(c, dict)],
            citations=list(data.get("citations", [])),
            grounding_refs=list(data.get("grounding_refs", [])),
            perspectives={k: dict(v) for k, v in data.get("perspectives", {}).items() if isinstance(v, dict)},
        )


@dataclass
class ProjectState:
    """Complete serializable workspace state."""

    documents: List[SourceDocument] = field(default_factory=list)
    active_tab_index: int = 0
    workspaces: List[WorkspaceTabState] = field(default_factory=list)

    topic: str = ""
    query: str = ""
    language: str = "en"
    discovery_model: str = ""
    synthesis_model: str = ""

    synthesis_original: str = ""
    synthesis_translated: str = ""
    synthesis_showing_translation: bool = False
    perspective_original: str = ""
    perspective_translated: str = ""
    perspective_showing_translation: bool = False

    citations: List[Dict[str, Any]] = field(default_factory=list)
    grounding_refs: List[Dict[str, Any]] = field(default_factory=list)

    # Compatibility attributes
    title: str = ""
    updated_at: str = ""
    discovery_prompt: str = ""
    selected_perspectives: List[str] = field(default_factory=list)
    synthesis_query: str = ""
    synthesis_markdown: str = ""
    synthesis_translated_markdown: str = ""
    perspective_report_markdown: str = ""
    perspective_report_translated_markdown: str = ""
    citations_used: List[Any] = field(default_factory=list)
    podcast_script: Any = None
    audio_relative_path: str = ""

    audio_title: str = ""
    audio_directive: str = ""
    audio_model: str = ""
    audio_language: str = "en"
    audio_script_raw: str = ""
    audio_mp3_path: Optional[str] = None  # filesystem path of the mp3 (source on save, extracted copy on load)

    chat_history: List[Dict[str, str]] = field(default_factory=list)
    created_at: str = ""
    saved_at: str = ""

    def __post_init__(self):
        if self.title and not self.topic:
            self.topic = self.title
        if self.synthesis_query and not self.query:
            self.query = self.synthesis_query
        if self.discovery_prompt and not self.topic:
            self.topic = self.discovery_prompt
        if self.synthesis_markdown and not self.synthesis_original:
            self.synthesis_original = self.synthesis_markdown
        if self.synthesis_translated_markdown and not self.synthesis_translated:
            self.synthesis_translated = self.synthesis_translated_markdown
        if self.perspective_report_markdown and not self.perspective_original:
            self.perspective_original = self.perspective_report_markdown
        if self.perspective_report_translated_markdown and not self.perspective_translated:
            self.perspective_translated = self.perspective_report_translated_markdown
        if self.citations_used and not self.citations:
            self.citations = [c.to_dict() if hasattr(c, "to_dict") else dict(c) for c in self.citations_used]

    def __iter__(self):
        yield self
        yield self.audio_mp3_path


def _source_filename(index: int, doc: SourceDocument) -> str:
    return f"sources/{index:03d}_{doc.cite_id}.txt"


def save_project(path_or_state: Any, state_or_path: Any = None, audio_file_path: Optional[str] = None) -> Path:
    """Write `state` into a compressed `.omni` zip archive at `path` (atomic replace)."""
    if isinstance(path_or_state, ProjectState):
        state = path_or_state
        target = Path(state_or_path)
    else:
        target = Path(path_or_state)
        state = state_or_path

    if audio_file_path and not state.audio_mp3_path:
        state.audio_mp3_path = audio_file_path

    if target.suffix.lower() != PROJECT_EXTENSION:
        target = target.with_suffix(PROJECT_EXTENSION)
    target.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state.saved_at = now
    if not state.created_at:
        state.created_at = now

    mp3_bytes: Optional[bytes] = None
    if state.audio_mp3_path:
        mp3_file = Path(state.audio_mp3_path)
        if mp3_file.exists() and mp3_file.stat().st_size > 0:
            mp3_bytes = mp3_file.read_bytes()

    # Sync primary fields from active workspace if workspaces exist
    if state.workspaces:
        active_idx = min(max(0, state.active_tab_index), len(state.workspaces) - 1)
        active_ws = state.workspaces[active_idx]
        if not state.topic and active_ws.topic:
            state.topic = active_ws.topic
        if not state.query and active_ws.query:
            state.query = active_ws.query
        if not state.synthesis_original and active_ws.synthesis_original:
            state.synthesis_original = active_ws.synthesis_original
        if not state.synthesis_translated and active_ws.synthesis_translated:
            state.synthesis_translated = active_ws.synthesis_translated
        if not state.perspective_original and active_ws.perspective_original:
            state.perspective_original = active_ws.perspective_original
        if not state.perspective_translated and active_ws.perspective_translated:
            state.perspective_translated = active_ws.perspective_translated
        if not state.audio_directive and active_ws.audio_directive:
            state.audio_directive = active_ws.audio_directive
        if not state.audio_script_raw and active_ws.audio_script_raw:
            state.audio_script_raw = active_ws.audio_script_raw
        if not state.chat_history and active_ws.chat_history:
            state.chat_history = active_ws.chat_history

    source_entries: List[Dict[str, Any]] = []
    source_payloads: List[tuple[str, str]] = []
    for index, doc in enumerate(sorted(state.documents, key=lambda d: d.cite_id), start=1):
        archive_name = _source_filename(index, doc)
        entry = doc.to_dict(include_content=False)
        entry["file"] = archive_name
        source_entries.append(entry)
        source_payloads.append((archive_name, doc.content))

    workspace_entries: List[str] = []
    workspace_payloads: List[tuple[str, str]] = []
    for idx, ws in enumerate(state.workspaces):
        ws_file = f"workspaces/workspace_{idx}.json"
        workspace_entries.append(ws_file)
        workspace_payloads.append((ws_file, json.dumps(ws.to_dict(), ensure_ascii=False, indent=2)))

    report_payloads = {
        "synthesis_original": state.synthesis_original,
        "synthesis_translated": state.synthesis_translated,
        "perspective_original": state.perspective_original,
        "perspective_translated": state.perspective_translated,
        "audio_script": state.audio_script_raw,
    }

    manifest: Dict[str, Any] = {
        "app": APP_NAME,
        "format_version": FORMAT_VERSION,
        "created_at": state.created_at,
        "saved_at": state.saved_at,
        "language": state.language,
        "models": {"discovery": state.discovery_model, "synthesis": state.synthesis_model},
        "topic": state.topic,
        "query": state.query,
        "active_tab_index": state.active_tab_index,
        "view_state": {
            "synthesis_showing_translation": state.synthesis_showing_translation,
            "perspective_showing_translation": state.perspective_showing_translation,
        },
        "sources": source_entries,
        "workspaces": workspace_entries,
        "reports": {key: _REPORT_FILES[key] for key, text in report_payloads.items() if text},
        "citations": state.citations,
        "grounding_refs": state.grounding_refs,
        "audio": {
            "title": state.audio_title,
            "directive": state.audio_directive,
            "model": state.audio_model,
            "language": state.audio_language,
            "has_script": bool(state.audio_script_raw),
            "mp3": AUDIO_ARCHIVE_NAME if mp3_bytes else "",
        },
        "chat_history": state.chat_history,
    }

    # Preserve any existing checkpoints from archive if it already exists
    existing_checkpoints_files: Dict[str, bytes] = {}
    if target.exists() and zipfile.is_zipfile(target):
        try:
            with zipfile.ZipFile(target, "r") as prev_zip:
                for item in prev_zip.namelist():
                    if item.startswith("checkpoints/"):
                        existing_checkpoints_files[item] = prev_zip.read(item)
        except Exception:
            pass

    temp_path = target.with_suffix(target.suffix + ".part")
    with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
        for archive_name, content in source_payloads:
            archive.writestr(archive_name, content)
        for ws_file, ws_content in workspace_payloads:
            archive.writestr(ws_file, ws_content)
        for key in sorted(report_payloads):
            if report_payloads[key]:
                archive.writestr(_REPORT_FILES[key], report_payloads[key])
        if mp3_bytes:
            archive.writestr(AUDIO_ARCHIVE_NAME, mp3_bytes, compress_type=zipfile.ZIP_STORED)
        for cp_file, cp_bytes in existing_checkpoints_files.items():
            archive.writestr(cp_file, cp_bytes)
    temp_path.replace(target)
    return target


def load_project(path: str | Path, audio_output_dir: Optional[str | Path] = None) -> ProjectState:
    """Deterministically unpack a `.omni` archive into a ProjectState (mp3 extracted into `audio_output_dir`)."""
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Project file not found: {source}")
    if not zipfile.is_zipfile(source):
        raise ProjectFormatError("The selected file is not a valid .omni project archive.")

    with zipfile.ZipFile(source, "r") as archive:
        names = set(archive.namelist())
        if MANIFEST_NAME not in names:
            raise ProjectFormatError("manifest.json is missing from the project archive.")
        try:
            manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProjectFormatError(f"manifest.json is corrupted: {exc}") from exc
        if manifest.get("app") != APP_NAME:
            raise ProjectFormatError("This archive was not created by OmniResearch Studio.")
        if int(manifest.get("format_version", 0)) > FORMAT_VERSION:
            raise ProjectFormatError("This project was saved by a newer version of OmniResearch Studio.")

        documents: List[SourceDocument] = []
        for entry in manifest.get("sources", []):
            archive_name = str(entry.get("file", ""))
            content = archive.read(archive_name).decode("utf-8") if archive_name in names else ""
            documents.append(SourceDocument.from_dict(entry, content=content))
        documents.sort(key=lambda d: d.cite_id)

        def _read_report(key: str) -> str:
            name = _REPORT_FILES[key]
            return archive.read(name).decode("utf-8") if name in names else ""

        audio_meta = manifest.get("audio", {}) or {}
        mp3_path: Optional[str] = None
        if audio_meta.get("mp3") and AUDIO_ARCHIVE_NAME in names:
            out_dir = Path(audio_output_dir) if audio_output_dir else source.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            mp3_file = out_dir / "audio_briefing.mp3"
            mp3_file.write_bytes(archive.read(AUDIO_ARCHIVE_NAME))
            mp3_path = str(mp3_file)

        view_state = manifest.get("view_state", {}) or {}
        models = manifest.get("models", {}) or {}

        # Load workspace tabs if present
        workspace_files = [n for n in names if n.startswith("workspaces/workspace_") and n.endswith(".json")]
        workspace_files.sort(
            key=lambda x: int(re.search(r"workspace_(\d+)\.json", x).group(1))
            if re.search(r"workspace_(\d+)\.json", x)
            else 999
        )
        workspaces: List[WorkspaceTabState] = []
        for ws_file in workspace_files:
            try:
                ws_data = json.loads(archive.read(ws_file).decode("utf-8"))
                workspaces.append(WorkspaceTabState.from_dict(ws_data))
            except Exception:
                pass

        if not workspaces:
            # Backwards compatibility: create workspace 0 from manifest / reports
            workspaces = [
                WorkspaceTabState(
                    tab_id="workspace_0",
                    title=str(manifest.get("topic", "")).strip()[:30] or "Research Workspace",
                    topic=str(manifest.get("topic", "")),
                    query=str(manifest.get("query", "")),
                    synthesis_original=_read_report("synthesis_original"),
                    synthesis_translated=_read_report("synthesis_translated"),
                    synthesis_showing_translation=bool(view_state.get("synthesis_showing_translation", False)),
                    perspective_original=_read_report("perspective_original"),
                    perspective_translated=_read_report("perspective_translated"),
                    perspective_showing_translation=bool(view_state.get("perspective_showing_translation", False)),
                    audio_directive=str(audio_meta.get("directive", "")),
                    audio_script_raw=_read_report("audio_script"),
                    audio_title=str(audio_meta.get("title", "")),
                    audio_mp3_path=mp3_path,
                    chat_history=[
                        {"role": str(m.get("role", "user")), "text": str(m.get("text", ""))}
                        for m in manifest.get("chat_history", [])
                        if isinstance(m, dict)
                    ],
                    citations=list(manifest.get("citations", [])),
                    grounding_refs=list(manifest.get("grounding_refs", [])),
                )
            ]

        return ProjectState(
            documents=documents,
            active_tab_index=int(manifest.get("active_tab_index", 0)),
            workspaces=workspaces,
            topic=str(manifest.get("topic", "")),
            query=str(manifest.get("query", "")),
            language=str(manifest.get("language", "en")),
            discovery_model=str(models.get("discovery", "")),
            synthesis_model=str(models.get("synthesis", "")),
            synthesis_original=_read_report("synthesis_original"),
            synthesis_translated=_read_report("synthesis_translated"),
            synthesis_showing_translation=bool(view_state.get("synthesis_showing_translation", False)),
            perspective_original=_read_report("perspective_original"),
            perspective_translated=_read_report("perspective_translated"),
            perspective_showing_translation=bool(view_state.get("perspective_showing_translation", False)),
            citations=list(manifest.get("citations", [])),
            grounding_refs=list(manifest.get("grounding_refs", [])),
            audio_title=str(audio_meta.get("title", "")),
            audio_directive=str(audio_meta.get("directive", "")),
            audio_model=str(audio_meta.get("model", "")),
            audio_language=str(audio_meta.get("language", "en")),
            audio_script_raw=_read_report("audio_script"),
            audio_mp3_path=mp3_path,
            chat_history=[
                {"role": str(m.get("role", "user")), "text": str(m.get("text", ""))}
                for m in manifest.get("chat_history", [])
                if isinstance(m, dict)
            ],
            created_at=str(manifest.get("created_at", "")),
            saved_at=str(manifest.get("saved_at", "")),
        )


def create_checkpoint(
    project_path: Path | str,
    name_or_state: Any = None,
    state: Optional[ProjectState] = None,
    name: str = "",
    description: str = "",
) -> str:
    """Create a delta snapshot checkpoint inside the project bundle."""
    import uuid

    if isinstance(name_or_state, ProjectState):
        actual_state = name_or_state
        actual_name = name or "Checkpoint"
    elif isinstance(name_or_state, str):
        actual_name = name_or_state
        actual_state = state
    else:
        actual_state = state
        actual_name = name or "Checkpoint"

    if actual_state is None:
        raise ValueError("ProjectState must be provided to create_checkpoint")

    target = Path(project_path)
    cp_id = f"cp_{int(datetime.datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cp_meta = {
        "id": cp_id,
        "name": actual_name,
        "description": description,
        "timestamp": now_str,
        "models": {"discovery": actual_state.discovery_model, "synthesis": actual_state.synthesis_model},
        "active_tab_index": actual_state.active_tab_index,
        "workspaces_count": len(actual_state.workspaces),
        "documents_count": len(actual_state.documents),
    }

    existing_checkpoints = list_checkpoints(target)
    existing_checkpoints.append(cp_meta)

    state_payload = {
        "manifest": {
            "topic": actual_state.topic,
            "query": actual_state.query,
            "active_tab_index": actual_state.active_tab_index,
            "models": {"discovery": actual_state.discovery_model, "synthesis": actual_state.synthesis_model},
            "language": actual_state.language,
            "synthesis_original": actual_state.synthesis_original,
            "synthesis_translated": actual_state.synthesis_translated,
            "perspective_original": actual_state.perspective_original,
            "perspective_translated": actual_state.perspective_translated,
            "citations": actual_state.citations,
            "grounding_refs": actual_state.grounding_refs,
            "audio_title": actual_state.audio_title,
            "audio_directive": actual_state.audio_directive,
            "audio_script_raw": actual_state.audio_script_raw,
            "audio_mp3_path": actual_state.audio_mp3_path,
            "chat_history": actual_state.chat_history,
        },
        "workspaces": [ws.to_dict() for ws in actual_state.workspaces],
        "documents": [d.to_dict() for d in actual_state.documents],
    }

    if target.is_file() and zipfile.is_zipfile(target):
        temp_zip = target.with_suffix(".tmp.zip")
        with zipfile.ZipFile(target, "r") as zin:
            with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename == "checkpoints/index.json" or item.filename.startswith(f"checkpoints/{cp_id}/"):
                        continue
                    zout.writestr(item, zin.read(item.filename))
                zout.writestr("checkpoints/index.json", json.dumps(existing_checkpoints, ensure_ascii=False, indent=2))
                zout.writestr(f"checkpoints/{cp_id}/manifest.json", json.dumps(state_payload, ensure_ascii=False, indent=2))
        temp_zip.replace(target)
    else:
        base_dir = target if target.is_dir() else target.parent / "checkpoints"
        base_dir.mkdir(parents=True, exist_ok=True)
        idx_file = base_dir / "index.json"
        cp_file = base_dir / f"manifest_{cp_id}.json"
        idx_file.write_text(json.dumps(existing_checkpoints, ensure_ascii=False, indent=2), encoding="utf-8")
        cp_file.write_text(json.dumps(state_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return cp_id


def restore_checkpoint(project_path: Path | str, checkpoint_id: str) -> ProjectState:
    """Restore and reconstruct a ProjectState from a checkpoint snapshot."""
    target = Path(project_path)
    state_payload = None

    if target.is_file() and zipfile.is_zipfile(target):
        with zipfile.ZipFile(target, "r") as zin:
            cp_file = f"checkpoints/{checkpoint_id}/manifest.json"
            if cp_file in zin.namelist():
                state_payload = json.loads(zin.read(cp_file).decode("utf-8"))
    else:
        base_dir = target if target.is_dir() else target.parent / "checkpoints"
        cp_file = base_dir / f"manifest_{checkpoint_id}.json"
        if cp_file.exists():
            state_payload = json.loads(cp_file.read_text(encoding="utf-8"))

    if not state_payload:
        raise ProjectFormatError(f"Checkpoint '{checkpoint_id}' not found in {project_path}")

    manifest = state_payload.get("manifest", {})
    workspaces = [WorkspaceTabState.from_dict(ws) for ws in state_payload.get("workspaces", [])]
    documents = [SourceDocument.from_dict(d) for d in state_payload.get("documents", [])]

    models = manifest.get("models", {})
    return ProjectState(
        documents=documents,
        active_tab_index=int(manifest.get("active_tab_index", 0)),
        workspaces=workspaces,
        topic=str(manifest.get("topic", "")),
        query=str(manifest.get("query", "")),
        language=str(manifest.get("language", "en")),
        discovery_model=str(models.get("discovery", "")),
        synthesis_model=str(models.get("synthesis", "")),
        synthesis_original=str(manifest.get("synthesis_original", "")),
        synthesis_translated=str(manifest.get("synthesis_translated", "")),
        perspective_original=str(manifest.get("perspective_original", "")),
        perspective_translated=str(manifest.get("perspective_translated", "")),
        citations=list(manifest.get("citations", [])),
        grounding_refs=list(manifest.get("grounding_refs", [])),
        audio_title=str(manifest.get("audio_title", "")),
        audio_directive=str(manifest.get("audio_directive", "")),
        audio_script_raw=str(manifest.get("audio_script_raw", "")),
        audio_mp3_path=manifest.get("audio_mp3_path"),
        chat_history=list(manifest.get("chat_history", [])),
        created_at=str(manifest.get("created_at", "")),
        saved_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def list_checkpoints(project_path: Path | str) -> List[Dict[str, Any]]:
    """Return chronological list of checkpoints for the project."""
    target = Path(project_path)
    if target.is_file() and zipfile.is_zipfile(target):
        try:
            with zipfile.ZipFile(target, "r") as zin:
                if "checkpoints/index.json" in zin.namelist():
                    data = json.loads(zin.read("checkpoints/index.json").decode("utf-8"))
                    if isinstance(data, list):
                        return data
        except Exception:
            pass
    else:
        base_dir = target if target.is_dir() else target.parent / "checkpoints"
        idx_file = base_dir / "index.json"
        if idx_file.exists():
            try:
                data = json.loads(idx_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except Exception:
                pass
    return []
