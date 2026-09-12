"""Discord implementation of the shared remote deletion safety workflow."""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from importlib.resources import files
from pathlib import Path
from tkinter import messagebox
from typing import Any

from gpt_exporter.core.serialization import read_canonical_conversation
from export_provider_discord.archive import archive_collector_export
from export_provider_discord.collector import (
    EXPORT_GLOB,
    collector_javascript,
    snapshot_exports,
    validate_collector_export,
)
from export_provider_discord.naming import (
    discord_artifact_paths,
    dm_artifact_stem,
    dm_title,
    is_group_dm,
)
from export_provider_discord.raw_archive import (
    iter_raw_files,
    migrate_plain_raw_file,
    read_raw_json,
)
from gpt_exporter.ui.archive_workflow import (
    ArchiveProcessingDialog,
    ArchiveWorkflowSpec,
)
from gpt_exporter.ui.remote_delete import RemoteDeletionPlan

from .workspace_actions import DiscordWorkspaceActions


_DIRECT_DM_CATEGORY = "Discord Direct Message"
_GROUP_DM_CATEGORY = "Discord Group DM"


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

    def _raw_archive_files(self) -> tuple[Path, ...]:
        """Return new co-located raw snapshots plus historical raw-directory files."""
        downloads = self.workspace.root_path / "downloads"
        current = tuple(sorted(downloads.glob("*.raw.json.xz"))) if downloads.is_dir() else ()
        legacy_dir = self.workspace.root_path / "raw"
        legacy = iter_raw_files(legacy_dir) if legacy_dir.is_dir() else ()
        seen: set[Path] = set()
        result: list[Path] = []
        for path in (*current, *legacy):
            resolved = Path(path).resolve()
            if resolved not in seen:
                seen.add(resolved)
                result.append(Path(path))
        return tuple(result)

    def prepare_index(self) -> bool:
        """Migrate Discord artifacts, normalize titles, and classify DM kinds."""
        root = self.workspace.root_path
        downloads = root / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        changed = False
        metadata_by_channel: dict[str, dict[str, Any]] = {}

        for raw_path in self._raw_archive_files():
            try:
                payload = read_raw_json(raw_path)
                conversation = payload.get("conversation") if isinstance(payload, dict) else None
                channel_id = str(conversation.get("channel_id") or "") if isinstance(conversation, dict) else ""
                if not channel_id:
                    continue
                raw_title = str(conversation.get("title") or "")
                metadata = {
                    "participants": conversation.get("participants"),
                    "current_user": payload.get("current_user"),
                    "conversation_type": conversation.get("type"),
                }
                dm_title(metadata, raw_title)
                metadata_by_channel[channel_id] = metadata
                target_raw, _target_canonical, _target_docx = discord_artifact_paths(
                    root, metadata, channel_id
                )
                if raw_path.resolve() != target_raw.resolve():
                    migrate_plain_raw_file(raw_path, target_raw)
                    changed = True
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue

        historical_canonicals = tuple(
            path
            for path in sorted(downloads.glob("*.json.xz"))
            if not path.name.casefold().endswith(".raw.json.xz")
            and not path.name.casefold().endswith(".canonical.json.xz")
        )
        for source in historical_canonicals:
            try:
                canonical = read_canonical_conversation(source)
            except (OSError, ValueError):
                continue
            if canonical.provider_id != "discord":
                continue
            channel_id = str(canonical.conversation_id).removeprefix("discord:")
            metadata = dict(canonical.metadata)
            metadata.update(metadata_by_channel.get(channel_id, {}))
            _target_raw, target_canonical, target_docx = discord_artifact_paths(
                root, metadata, channel_id
            )
            if source.resolve() != target_canonical.resolve() and not target_canonical.exists():
                source.replace(target_canonical)
                changed = True

            old_docx_candidates = sorted(
                (*root.glob(f"Discord DM * {channel_id}.docx"),
                 *root.glob(f"Discord Group DM * {channel_id}.docx"))
            )
            if not target_docx.exists() and old_docx_candidates:
                old_docx = max(old_docx_candidates, key=lambda path: path.stat().st_mtime_ns)
                if old_docx.resolve() != target_docx.resolve():
                    try:
                        old_docx.replace(target_docx)
                    except OSError:
                        shutil.copy2(old_docx, target_docx)
                        old_docx.unlink(missing_ok=True)
                    changed = True

        if self.workspace.database_path.is_file():
            try:
                with sqlite3.connect(self.workspace.database_path) as connection:
                    connection.row_factory = sqlite3.Row
                    for name, description in (
                        (_DIRECT_DM_CATEGORY, "Discord one-to-one direct-message conversations"),
                        (_GROUP_DM_CATEGORY, "Discord multi-participant direct-message conversations"),
                    ):
                        connection.execute(
                            "INSERT OR IGNORE INTO categories (name, description, created_at) VALUES (?, ?, datetime('now'))",
                            (name, description),
                        )
                    category_rows = connection.execute(
                        "SELECT category_id, name FROM categories WHERE name IN (?, ?) COLLATE NOCASE",
                        (_DIRECT_DM_CATEGORY, _GROUP_DM_CATEGORY),
                    ).fetchall()
                    category_ids = {str(item["name"]): int(item["category_id"]) for item in category_rows}
                    direct_category_id = category_ids.get(_DIRECT_DM_CATEGORY)
                    group_category_id = category_ids.get(_GROUP_DM_CATEGORY)

                    rows = connection.execute(
                        """
                        SELECT c.conversation_id, c.title, c.source_json_path, c.docx_path,
                               pm.metadata_json
                        FROM conversations AS c
                        LEFT JOIN conversation_provider_metadata AS pm
                          ON pm.conversation_id = c.conversation_id
                         AND pm.provider_id = 'discord'
                        WHERE c.conversation_id LIKE 'discord:%'
                        """
                    ).fetchall()
                    for row in rows:
                        channel_id = str(row["conversation_id"]).removeprefix("discord:")
                        metadata = dict(metadata_by_channel.get(channel_id, {}))
                        raw_metadata = row["metadata_json"]
                        if raw_metadata:
                            try:
                                parsed = json.loads(raw_metadata)
                            except (TypeError, json.JSONDecodeError):
                                parsed = {}
                            if isinstance(parsed, dict):
                                merged = dict(parsed)
                                merged.update(metadata)
                                metadata = merged
                        target_raw, target_canonical, target_docx = discord_artifact_paths(
                            root, metadata, channel_id
                        )
                        source_value = (
                            str(target_canonical)
                            if target_canonical.is_file()
                            else str(row["source_json_path"] or "")
                        )
                        docx_value = (
                            str(target_docx)
                            if target_docx.is_file()
                            else (str(row["docx_path"] or "") or None)
                        )
                        title = dm_title(metadata, str(row["title"] or ""))
                        if title != str(row["title"] or ""):
                            changed = True
                        connection.execute(
                            """
                            UPDATE conversations
                               SET title = ?, source_json_path = ?, docx_path = ?,
                                   primary_origin_type = ?, primary_origin_id = ?
                             WHERE conversation_id = ?
                            """,
                            (
                                title,
                                source_value,
                                docx_value,
                                "Direct Messages",
                                channel_id,
                                row["conversation_id"],
                            ),
                        )

                        group_dm = is_group_dm(metadata)
                        desired_category_id = group_category_id if group_dm else direct_category_id
                        obsolete_category_id = direct_category_id if group_dm else group_category_id
                        if desired_category_id is not None:
                            before = connection.total_changes
                            connection.execute(
                                """
                                INSERT OR IGNORE INTO conversation_categories (
                                    conversation_id, category_id, assigned_at
                                ) VALUES (?, ?, datetime('now'))
                                """,
                                (row["conversation_id"], desired_category_id),
                            )
                            changed = changed or connection.total_changes > before
                        if obsolete_category_id is not None:
                            before = connection.total_changes
                            connection.execute(
                                "DELETE FROM conversation_categories WHERE conversation_id = ? AND category_id = ?",
                                (row["conversation_id"], obsolete_category_id),
                            )
                            changed = changed or connection.total_changes > before

                        try:
                            connection.execute(
                                "UPDATE canonical_conversation_sources SET source_path = ? WHERE conversation_id = ?",
                                (source_value, row["conversation_id"]),
                            )
                        except sqlite3.OperationalError:
                            pass
                    connection.commit()
            except sqlite3.Error:
                pass

        legacy_raw_dir = root / "raw"
        if legacy_raw_dir.is_dir():
            try:
                legacy_raw_dir.rmdir()
            except OSError:
                pass
            else:
                changed = True
        return changed

    def regenerate_missing(self) -> bool:
        raw_files = list(self._raw_archive_files())
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
                    "conversation_type": conversation.get("type"),
                }
                dm_title(metadata, str(conversation.get("title") or ""))
                _raw, _canonical, docx_path = discord_artifact_paths(
                    self.workspace.root_path,
                    metadata,
                    channel_id,
                )
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
            export_path=self.workspace.root_path / "downloads",
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
        if not conversation_id.startswith("discord:"):
            return False
        canonical_path = self._canonical_path_for_row(row)
        if canonical_path is None:
            return False
        try:
            archived = read_canonical_conversation(canonical_path)
        except (OSError, ValueError):
            return False
        return not is_group_dm(archived.metadata)

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

        resource = files("export_provider_discord.resources").joinpath(
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
