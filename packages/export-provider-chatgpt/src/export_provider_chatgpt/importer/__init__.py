"""ChatGPT browser-bundle import API."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Callable

from gpt_exporter.providers.gpt.assets import migrate_gpt_asset_layout


_import_capture = io.StringIO()
with contextlib.redirect_stdout(_import_capture):
    from . import _bundle_importer

ProgressCallback = Callable[[str], None]
ImportBundleResult = _bundle_importer.ImportBundleResult


class _ProgressStream(io.TextIOBase):
    def __init__(self, progress: ProgressCallback | None) -> None:
        super().__init__()
        self.progress = progress
        self._buffer = ""

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        self._buffer += value
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if self.progress is not None:
                self.progress(line)
        return len(value)

    def flush(self) -> None:
        if self._buffer and self.progress is not None:
            self.progress(self._buffer)
        self._buffer = ""


def _docx_name_for_conversation(path: Path) -> str:
    name = path.name
    if name.lower().endswith(".json.xz"):
        return name[:-8] + ".docx"
    if name.lower().endswith(".json"):
        return name[:-5] + ".docx"
    return path.with_suffix(".docx").name


def _augment_current_batch_with_missing_docx(
    archive_root: Path,
    *,
    force_conversations: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Schedule missing DOCX plus conversations whose archived asset paths changed."""

    downloads = archive_root / "downloads"
    reports = archive_root / "reports"
    batch_file = reports / "current-batch.json"

    if not downloads.is_dir():
        return ()

    conversations = sorted(downloads.glob("*.json.xz"))
    if not conversations:
        conversations = sorted(
            path
            for path in downloads.glob("*.json")
            if path.name != "download-index.json"
        )

    forced = set(force_conversations)
    scheduled = []
    for conversation in conversations:
        docx = archive_root / _docx_name_for_conversation(conversation)
        if (
            conversation.name in forced
            or not docx.is_file()
            or docx.stat().st_size == 0
        ):
            scheduled.append(conversation.name)

    if not scheduled:
        return ()

    if batch_file.is_file():
        data = json.loads(batch_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"invalid current batch: {batch_file}")
    else:
        data = {}

    existing = data.get("conversation_files", [])
    if not isinstance(existing, list):
        raise ValueError(f"invalid conversation_files in current batch: {batch_file}")

    merged: list[str] = []
    seen: set[str] = set()
    for name in [*existing, *scheduled]:
        if isinstance(name, str) and name not in seen:
            seen.add(name)
            merged.append(name)

    if merged != existing:
        data["conversation_files"] = merged
        reports.mkdir(parents=True, exist_ok=True)
        batch_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    existing_set = {name for name in existing if isinstance(name, str)}
    return tuple(name for name in scheduled if name not in existing_set)


def import_bundle(
    bundle_path: Path | str,
    *,
    archive_root: Path | str,
    progress: ProgressCallback | None = None,
) -> ImportBundleResult:
    """Import one ChatGPT browser collector bundle into an archive root."""
    stream = _ProgressStream(progress)
    resolved_root = Path(archive_root).expanduser().resolve()
    try:
        with contextlib.redirect_stdout(stream):
            result = _bundle_importer.import_bundle(
                bundle_path,
                archive_root=resolved_root,
            )
            migration = migrate_gpt_asset_layout(resolved_root)
            print()
            print(
                "GPT asset layout: "
                f"moved={migration.moved}, "
                f"reused={migration.reused}, "
                f"unchanged={migration.unchanged}, "
                f"missing={migration.missing}"
            )
            regenerated = _augment_current_batch_with_missing_docx(
                resolved_root,
                force_conversations=migration.affected_conversations,
            )
            if regenerated:
                print()
                print(
                    "DOCX exports scheduled for regeneration: "
                    f"{len(regenerated)}"
                )
                for name in regenerated:
                    print(f"  {name}")
            return result
    finally:
        stream.flush()


__all__ = ["ImportBundleResult", "import_bundle"]
