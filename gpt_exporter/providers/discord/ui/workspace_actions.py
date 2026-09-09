"""Discord actions injected into the shared conversation workspace shell."""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import closing
from importlib.resources import files
from pathlib import Path
from tkinter import messagebox
from typing import Any

from gpt_exporter.providers.discord.archive import archive_collector_export
from gpt_exporter.providers.discord.collector import (
    EXPORT_GLOB,
    collector_javascript,
    open_discord,
    snapshot_exports,
    validate_collector_export,
)
from gpt_exporter.providers.discord.naming import dm_artifact_stem, dm_title, legacy_paths
from gpt_exporter.providers.discord.raw_archive import (
    iter_raw_files,
    migrate_plain_raw_file,
    read_raw_json,
)
from gpt_exporter.ui.archive_workflow import (
    ArchiveProcessingDialog,
    ArchiveWorkflowDialog,
    ArchiveWorkflowSpec,
    latest_archive_log_path,
)
from gpt_exporter.ui.browser import archive_browser as browser
from gpt_exporter.workspaces import ConversationWorkspace


class DiscordWorkspaceActions:
    service_label = "Discord"
    process_label = "Process Downloaded Export…"
    regenerate_label = "Regenerate Missing DOCX…"
    can_regenerate = True
    archive_workflow_spec = ArchiveWorkflowSpec(
        service_label="Discord",
        open_instructions=(
            "Open Discord in your normal browser, make sure you are signed in, "
            "and select the DM to archive."
        ),
        collector_instructions=(
            "The collector JavaScript is copied to the clipboard automatically. "
            "Open Developer Tools (F12), select Console, paste it and run it."
        ),
        download_instructions=(
            "When the collector finishes, the browser downloads a Discord DM export. "
            "As soon as a new valid export is detected, the archive workflow starts automatically."
        ),
        waiting_text="Waiting for a new Discord DM export in Downloads…",
    )

    def __init__(self, app, workspace: ConversationWorkspace) -> None:
        self.app = app
        self.workspace = workspace
        self.download_directory = Path.home() / "Downloads"

    @property
    def workflow_log_directory(self) -> Path:
        return self.workspace.root_path / "reports"

    def _migrate_raw_archives(self) -> bool:
        raw_dir = self.workspace.root_path / "raw"
        if not raw_dir.is_dir():
            return False
        changed = False
        for path in sorted(raw_dir.glob("*.json")):
            try:
                payload = read_raw_json(path)
                conversation = payload.get("conversation") if isinstance(payload, dict) else None
                channel_id = str(conversation.get("channel_id") or "") if isinstance(conversation, dict) else ""
                if not channel_id:
                    continue
                metadata = {
                    "participants": conversation.get("participants"),
                    "current_user": payload.get("current_user"),
                }
                stem = dm_artifact_stem(metadata, channel_id)
                destination = raw_dir / f"{stem}.json.xz"
                migrate_plain_raw_file(path, destination)
                changed = True
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
        return changed

    def prepare_index(self) -> bool:
        """Repair provider-derived fields and migrate historical Discord names/storage."""
        changed = self._migrate_raw_archives()
        if not self.workspace.database_path.is_file():
            return changed
        with closing(sqlite3.connect(self.workspace.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT c.conversation_id, c.title, c.source_json_path, c.docx_path,
                       c.primary_origin_type, pm.metadata_json
                FROM conversations AS c
                LEFT JOIN conversation_provider_metadata AS pm
                  ON pm.conversation_id = c.conversation_id
                 AND pm.provider_id = 'discord'
                WHERE c.conversation_id LIKE 'discord:%'
                """
            ).fetchall()
            for row in rows:
                conversation_id = str(row["conversation_id"])
                channel_id = conversation_id.removeprefix("discord:")
                metadata: dict[str, Any] = {}
                raw_metadata = row["metadata_json"]
                if raw_metadata:
                    try:
                        parsed = json.loads(raw_metadata)
                    except (TypeError, json.JSONDecodeError):
                        parsed = {}
                    if isinstance(parsed, dict):
                        metadata = parsed

                is_dm = str(metadata.get("conversation_type") or "").casefold() == "dm"
                if not is_dm:
                    continue

                human_title = dm_title(metadata, str(row["title"] or ""))
                stem = dm_artifact_stem(metadata, channel_id)
                new_docx = self.workspace.root_path / f"{stem}.docx"
                new_raw = self.workspace.root_path / "raw" / f"{stem}.json.xz"
                new_canonical = self.workspace.root_path / "downloads" / f"{stem}.json.xz"
                old_docx, old_raw, old_canonical = legacy_paths(self.workspace.root_path, channel_id)

                if old_raw.is_file() and not new_raw.exists():
                    try:
                        migrate_plain_raw_file(old_raw, new_raw)
                    except OSError:
                        pass
                    else:
                        changed = True

                for old, new in ((old_docx, new_docx), (old_canonical, new_canonical)):
                    if old.is_file() and not new.exists():
                        new.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            old.replace(new)
                        except OSError:
                            shutil.copy2(old, new)
                            old.unlink(missing_ok=True)
                        changed = True

                recorded_docx = str(row["docx_path"] or "").strip()
                recorded_source = str(row["source_json_path"] or "").strip()
                docx_value = str(new_docx) if new_docx.is_file() else (recorded_docx or None)
                source_value = str(new_canonical) if new_canonical.is_file() else recorded_source
                connection.execute(
                    """
                    UPDATE conversations
                       SET title = ?, docx_path = ?, source_json_path = ?,
                           primary_origin_type = ?, primary_origin_id = ?
                     WHERE conversation_id = ?
                    """,
                    (
                        human_title,
                        docx_value,
                        source_value,
                        "Direct Messages",
                        channel_id,
                        conversation_id,
                    ),
                )
                changed = changed or (
                    human_title != row["title"]
                    or row["primary_origin_type"] != "Direct Messages"
                    or (new_docx.is_file() and recorded_docx != str(new_docx))
                    or (new_canonical.is_file() and recorded_source != str(new_canonical))
                )

                if new_canonical.is_file():
                    try:
                        connection.execute(
                            "UPDATE canonical_conversation_sources SET source_path = ? WHERE conversation_id = ?",
                            (str(new_canonical), conversation_id),
                        )
                    except sqlite3.OperationalError:
                        pass
            connection.commit()
        return changed

    def resolve_docx_path(self, row: dict[str, Any]) -> Path | None:
        conversation_id = str(row.get("conversation_id") or "")
        if not conversation_id.startswith("discord:"):
            return None
        channel_id = conversation_id.removeprefix("discord:")
        metadata: dict[str, Any] = {}
        try:
            with closing(sqlite3.connect(self.workspace.database_path)) as connection:
                record = connection.execute(
                    "SELECT metadata_json FROM conversation_provider_metadata WHERE conversation_id = ? AND provider_id = 'discord'",
                    (conversation_id,),
                ).fetchone()
            if record and record[0]:
                parsed = json.loads(record[0])
                if isinstance(parsed, dict):
                    metadata = parsed
        except (sqlite3.Error, json.JSONDecodeError):
            pass
        return self.workspace.root_path / f"{dm_artifact_stem(metadata, channel_id)}.docx"

    def archive_new(self) -> None:
        ArchiveWorkflowDialog(self.app, actions=self)

    def snapshot_exports(self):
        return snapshot_exports(self.download_directory)

    def find_new_export(self, snapshot) -> Path | None:
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
                return validate_collector_export(candidate).path
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                continue
        return None

    def open_service(self, row: dict[str, Any] | None = None) -> None:
        channel_id = ""
        if isinstance(row, dict):
            conversation_id = str(row.get("conversation_id") or "")
            if conversation_id.startswith("discord:"):
                candidate = conversation_id.removeprefix("discord:")
                if candidate.isdigit():
                    channel_id = candidate
        try:
            opened = open_discord(channel_id or None)
        except (OSError, ValueError) as error:
            messagebox.showerror("Open Discord", str(error), parent=self.app)
            return
        if not opened:
            messagebox.showwarning(
                "Open Discord",
                "The default browser did not report that it opened Discord.",
                parent=self.app,
            )

    def copy_collector(self) -> bool:
        try:
            source = collector_javascript()
            self.app.clipboard_clear()
            self.app.clipboard_append(source)
            self.app.update_idletasks()
        except Exception as error:
            messagebox.showerror("Copy Collector JavaScript", str(error), parent=self.app)
            return False
        self.app.status_var.set("Discord collector JavaScript copied to the clipboard.")
        return True

    def show_collector(self) -> None:
        resource = files("gpt_exporter.providers.discord.resources").joinpath("export_current_dm.js")
        path = Path(str(resource))
        if not path.is_file():
            messagebox.showinfo(
                "Show Collector JavaScript",
                "The collector is packaged as an application resource and has no directly revealable filesystem path in this build.",
                parent=self.app,
            )
            return
        try:
            browser.reveal_in_file_manager(str(path))
        except OSError as error:
            messagebox.showerror("Show Collector JavaScript", str(error), parent=self.app)

    def process_export(self, path: Path) -> bool:
        export_path = Path(path)
        try:
            validate_collector_export(export_path)
        except Exception:
            return False
        self.app.status_var.set(f"Discord export detected: {export_path.name} — archiving…")
        ArchiveProcessingDialog(self.app, actions=self, export_path=export_path)
        return True

    def run_export(self, path: Path, progress):
        progress("Validating and normalizing Discord export…")
        result = archive_collector_export(Path(path), archive_root=self.workspace.root_path)
        progress(f"Conversation archived: {result.message_count} message(s).")
        progress(
            "Assets: "
            f"{result.available_assets} available, {result.downloaded_assets} downloaded, "
            f"{result.reused_assets} reused, {len(result.failed_assets)} failed."
        )
        progress(f"Raw archive: {result.raw_path}")
        progress(f"Canonical archive: {result.canonical_path}")
        progress(f"DOCX: {result.docx_path}")
        progress(f"Search index: {result.database_path}")
        return result

    def finish_export(self, result) -> bool:
        asset_text = (
            f" Assets: {result.available_assets} available, "
            f"{result.downloaded_assets} downloaded, {result.reused_assets} reused, "
            f"{len(result.failed_assets)} failed."
        )
        if result.updated:
            self.app.provider_content_changed(
                f"Discord archive updated — {result.message_count} messages.{asset_text}"
            )
        else:
            self.app.provider_content_changed(
                "Incoming Discord export was incomplete; existing archive preserved."
            )
        return True

    def process_downloaded(self) -> bool:
        try:
            candidates = sorted(
                self.download_directory.glob(EXPORT_GLOB),
                key=lambda item: item.stat().st_mtime_ns,
                reverse=True,
            )
        except OSError as error:
            messagebox.showerror("Process Downloaded Export", str(error), parent=self.app)
            return False

        for candidate in candidates:
            try:
                validate_collector_export(candidate)
            except Exception:
                continue
            return self.process_export(candidate)

        messagebox.showinfo(
            "Process Downloaded Export",
            f"No valid Discord collector export was found in {self.download_directory}.",
            parent=self.app,
        )
        return False

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

        failures: list[str] = []
        for raw_path in missing:
            try:
                archive_collector_export(raw_path, archive_root=self.workspace.root_path)
            except Exception as error:
                failures.append(f"{raw_path.name}: {error}")

        self.app.provider_content_changed(
            f"Discord DOCX regeneration complete — {len(missing) - len(failures)} created, {len(failures)} failed."
        )
        if failures:
            messagebox.showwarning(
                "Regenerate Missing DOCX",
                "Some conversations could not be regenerated:\n\n" + "\n".join(failures[:12]),
                parent=self.app,
            )
        return not failures

    def show_last_log(self) -> None:
        log_path = latest_archive_log_path(self.workflow_log_directory)
        if not log_path.is_file():
            messagebox.showinfo(
                "Show Last Archive Log",
                "No persistent archive-workflow log is available yet.",
                parent=self.app,
            )
            return
        try:
            browser.open_with_default_application(str(log_path))
        except OSError as error:
            messagebox.showerror("Show Last Archive Log", str(error), parent=self.app)


__all__ = ["DiscordWorkspaceActions"]
