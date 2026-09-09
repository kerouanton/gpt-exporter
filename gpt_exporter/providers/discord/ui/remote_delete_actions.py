"""Discord implementation of the shared remote deletion safety workflow."""

from __future__ import annotations

import json
import sqlite3
import time
from importlib.resources import files
from pathlib import Path
from tkinter import messagebox
from typing import Any

from gpt_exporter.core.serialization import read_canonical_conversation
from gpt_exporter.providers.discord.archive import archive_collector_export
from gpt_exporter.providers.discord.collector import (
    EXPORT_GLOB,
    collector_javascript,
    snapshot_exports,
    validate_collector_export,
)
from gpt_exporter.providers.discord.naming import dm_artifact_stem
from gpt_exporter.providers.discord.raw_archive import iter_raw_files, read_raw_json
from gpt_exporter.ui.archive_workflow import (
    ArchiveProcessingDialog,
    ArchiveWorkflowSpec,
)
from gpt_exporter.ui.remote_delete import RemoteDeletionPlan

from .workspace_actions import DiscordWorkspaceActions


class _DiscordRegenerationBacklogActions:
    """Run missing-DOCX regeneration through the shared processing backlog."""

    archive_workflow_spec = ArchiveWorkflowSpec(
        service_label="Discord DOCX regeneration",
        open_instructions="",
        collector_instructions="",
        download_instructions="",
        waiting_text="",
    )

    def __init__(self, owner: "DiscordRemoteDeleteActions", missing: list[Path]) -> None:
        self.owner = owner
        self.app = owner.app
        self.workspace = owner.workspace
        self.missing = tuple(Path(path) for path in missing)

    @property
    def workflow_log_directory(self) -> Path:
        return self.owner.workflow_log_directory

    def run_export(self, _path: Path, progress):
        started = time.monotonic()

        def timed_progress(message: str) -> None:
            elapsed = max(0, int(time.monotonic() - started))
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)
            progress(f"[+{hours:02d}:{minutes:02d}:{seconds:02d}] {message}")

        total = len(self.missing)
        failures: list[str] = []
        created = 0
        timed_progress(f"Starting missing-DOCX regeneration for {total} conversation(s)…")

        for index, raw_path in enumerate(self.missing, start=1):
            timed_progress("")
            timed_progress(f"[{index}/{total}] {raw_path.name}")
            try:
                result = archive_collector_export(
                    raw_path,
                    archive_root=self.workspace.root_path,
                    progress=lambda message: timed_progress(f"  {message}"),
                )
            except Exception as error:
                failure = f"{raw_path.name}: {type(error).__name__}: {error}"
                failures.append(failure)
                timed_progress(f"FAILED: {failure}")
                continue

            created += 1
            try:
                size = result.docx_path.stat().st_size
            except OSError:
                size = 0
            timed_progress(
                f"Completed [{index}/{total}]: {result.docx_path.name} ({size} bytes)."
            )

        timed_progress("")
        timed_progress(f"DOCX regeneration complete: {created} created, {len(failures)} failed.")
        return {
            "created": created,
            "total": total,
            "failures": tuple(failures),
        }

    def finish_export(self, result) -> bool:
        created = int(result.get("created", 0))
        failures = tuple(result.get("failures", ()))
        self.app.provider_content_changed(
            f"Discord DOCX regeneration complete — {created} created, {len(failures)} failed."
        )
        if failures:
            messagebox.showwarning(
                "Regenerate Missing DOCX",
                "Some conversations could not be regenerated:\n\n" + "\n".join(failures[:12]),
                parent=self.app,
            )
        return not failures


class DiscordRemoteDeleteActions(DiscordWorkspaceActions):
    """Add own-message remote cleanup without teaching the shared shell Discord DOM details."""

    remote_delete_label = "Delete My Archived Messages from Discord…"

    def regenerate_missing(self) -> bool:
        raw_dir = self.workspace.root_path / "raw"
        if not raw_dir.is_dir():
            messagebox.showinfo(
                "Regenerate Missing DOCX",
                "No Discord raw archive directory exists in this workspace.",
                parent=self.app,
            )
            return False

        raw_files = list(iter_raw_files(raw_dir))
        if not raw_files:
            messagebox.showinfo(
                "Regenerate Missing DOCX",
                "No Discord raw archive files exist in this workspace.",
                parent=self.app,
            )
            return False

        missing: list[Path] = []
        for raw_path in raw_files:
            try:
                payload = read_raw_json(raw_path)
                conversation = payload.get("conversation") if isinstance(payload, dict) else None
                channel_id = str(conversation.get("channel_id") or "") if isinstance(conversation, dict) else ""
                if not channel_id:
                    continue
                metadata = {
                    "participants": conversation.get("participants"),
                    "current_user": payload.get("current_user"),
                }
                docx_path = self.workspace.root_path / f"{dm_artifact_stem(metadata, channel_id)}.docx"
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if not docx_path.is_file() or docx_path.stat().st_size == 0:
                missing.append(raw_path)

        if not missing:
            messagebox.showinfo(
                "Regenerate Missing DOCX",
                "All archived Discord conversations already have a non-empty DOCX export.",
                parent=self.app,
            )
            return False

        self.app.status_var.set(
            f"Regenerating {len(missing)} missing Discord DOCX file(s)…"
        )
        actions = _DiscordRegenerationBacklogActions(self, missing)
        ArchiveProcessingDialog(
            self.app,
            actions=actions,
            export_path=raw_dir,
        )
        return True

    def _canonical_path_for_row(self, row: dict[str, Any]) -> Path | None:
        value = str(row.get("source_json_path") or "").strip()
        if not value:
            try:
                with sqlite3.connect(self.workspace.database_path) as connection:
                    record = connection.execute(
                        "SELECT source_json_path FROM conversations WHERE conversation_id = ?",
                        (str(row.get("conversation_id") or ""),),
                    ).fetchone()
                value = str(record[0] or "").strip() if record else ""
            except sqlite3.Error:
                return None
        if not value:
            return None
        path = Path(value).expanduser()
        return path if path.is_file() and path.stat().st_size > 0 else None

    def remote_delete_supported(self, row: dict[str, Any]) -> bool:
        conversation_id = str(row.get("conversation_id") or "")
        return conversation_id.startswith("discord:") and self._canonical_path_for_row(row) is not None

    def snapshot_remote_delete_dry_runs(self):
        return snapshot_exports(self.download_directory)

    def copy_remote_delete_dry_run(self, row: dict[str, Any]) -> bool:
        if not self.remote_delete_supported(row):
            return False
        source = collector_javascript()
        self.app.clipboard_clear()
        self.app.clipboard_append(source)
        self.app.update_idletasks()
        self.app.status_var.set(
            "Discord deletion dry run copied — run it in the archived DM's DevTools console."
        )
        return True

    def find_remote_delete_dry_run(self, snapshot, row: dict[str, Any]) -> Path | None:
        conversation_id = str(row.get("conversation_id") or "")
        expected_channel = conversation_id.removeprefix("discord:")
        known = {Path(path).resolve() for path in (snapshot or set())}
        try:
            candidates = sorted(
                (
                    path
                    for path in self.download_directory.glob(EXPORT_GLOB)
                    if path.resolve() not in known
                ),
                key=lambda item: item.stat().st_mtime_ns,
                reverse=True,
            )
        except OSError:
            return None

        for candidate in candidates:
            try:
                summary = validate_collector_export(candidate)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                continue
            if summary.channel_id == expected_channel:
                return summary.path
        return None

    def prepare_remote_deletion(
        self,
        row: dict[str, Any],
        dry_run_path: Path,
    ) -> RemoteDeletionPlan:
        conversation_id = str(row.get("conversation_id") or "")
        expected_channel = conversation_id.removeprefix("discord:")
        summary = validate_collector_export(dry_run_path)
        if summary.channel_id != expected_channel:
            raise ValueError(
                f"Dry run belongs to Discord DM {summary.channel_id}, expected {expected_channel}."
            )

        payload = json.loads(Path(dry_run_path).read_text(encoding="utf-8"))
        current_user = payload.get("current_user") if isinstance(payload, dict) else None
        current_user_id = str(current_user.get("id") or "") if isinstance(current_user, dict) else ""
        if not current_user_id.isdigit():
            raise ValueError("Dry run could not identify the current Discord user ID.")

        messages = payload.get("messages") if isinstance(payload, dict) else None
        if not isinstance(messages, list):
            raise ValueError("Dry run has no Discord messages array.")
        remote_ids = tuple(
            str(message.get("id"))
            for message in messages
            if isinstance(message, dict)
            and isinstance(message.get("author"), dict)
            and message["author"].get("is_self") is True
            and str(message.get("id") or "").isdigit()
        )
        if len(remote_ids) != len(set(remote_ids)):
            raise ValueError("Dry run contains duplicate own-message IDs.")

        canonical_path = self._canonical_path_for_row(row)
        if canonical_path is None:
            raise ValueError("The selected conversation no longer has a readable canonical archive.")
        archived = read_canonical_conversation(canonical_path)
        if archived.conversation_id != conversation_id:
            raise ValueError("Canonical archive conversation ID does not match the selected row.")
        archived_ids = {str(message.message_id) for message in archived.messages}
        archived_candidates = tuple(message_id for message_id in remote_ids if message_id in archived_ids)
        missing = tuple(message_id for message_id in remote_ids if message_id not in archived_ids)

        return RemoteDeletionPlan(
            provider_id="discord",
            conversation_id=conversation_id,
            conversation_title=str(row.get("title") or archived.title or f"Discord DM {expected_channel}"),
            operation_label="Delete my messages from Discord",
            remote_candidate_ids=remote_ids,
            archived_candidate_ids=archived_candidates,
            missing_candidate_ids=missing,
            dry_run_path=Path(dry_run_path),
            payload={
                "channel_id": expected_channel,
                "current_user_id": current_user_id,
                "canonical_path": str(canonical_path),
            },
        )

    def copy_remote_delete_execute(self, plan: RemoteDeletionPlan) -> bool:
        if plan.provider_id != "discord" or not plan.safe_to_execute:
            return False
        channel_id = str(plan.payload.get("channel_id") or "")
        current_user_id = str(plan.payload.get("current_user_id") or "")
        if not channel_id.isdigit() or not current_user_id.isdigit():
            raise ValueError("Deletion plan is missing its pinned Discord identity.")
        if plan.conversation_id != f"discord:{channel_id}":
            raise ValueError("Deletion plan conversation/channel mismatch.")

        resource = files("gpt_exporter.providers.discord.resources").joinpath(
            "delete_own_messages.js"
        )
        source = resource.read_text(encoding="utf-8")
        replacements = {
            '"__EXPECTED_CHANNEL_ID__"': json.dumps(channel_id),
            '"__EXPECTED_CURRENT_USER_ID__"': json.dumps(current_user_id),
            "__CANDIDATE_IDS_JSON__": json.dumps(list(plan.remote_candidate_ids)),
        }
        for marker, value in replacements.items():
            if marker not in source:
                raise RuntimeError(f"Packaged Discord deletion payload marker is missing: {marker}")
            source = source.replace(marker, value, 1)

        self.app.clipboard_clear()
        self.app.clipboard_append(source)
        self.app.update_idletasks()
        self.app.status_var.set(
            f"Discord deletion payload copied — {len(plan.remote_candidate_ids)} archived message(s) authorized."
        )
        return True


__all__ = ["DiscordRemoteDeleteActions"]
