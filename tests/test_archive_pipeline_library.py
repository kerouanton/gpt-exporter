import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import gpt_exporter.pipeline as pipeline


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ArchivePipelineLibraryTests(unittest.TestCase):
    def _prepare_archive(
        self,
        root: Path,
        *,
        batch_files: list[str] | None = None,
    ) -> tuple[Path, Path]:
        downloads = root / "downloads"
        reports = root / "reports"
        assets = root / "assets"
        downloads.mkdir(parents=True)
        reports.mkdir(parents=True)
        assets.mkdir(parents=True)
        conversation = downloads / "conversation.json.xz"
        conversation.write_bytes(b"placeholder")
        if batch_files is not None:
            (reports / "current-batch.json").write_text(
                json.dumps({"conversation_files": batch_files}),
                encoding="utf-8",
            )
        source = root / "chatgpt-archive-source.json"
        source.write_text("{}", encoding="utf-8")
        return conversation, source

    def _patch_stages(self, events: list[str]):
        import_result = SimpleNamespace(success=True)
        inventory_result = mock.sentinel.inventory_result
        manifest_result = mock.sentinel.manifest_result
        export_result = SimpleNamespace(success=True)
        index_result = mock.sentinel.index_result

        return (
            mock.patch.object(
                pipeline,
                "import_bundle",
                side_effect=lambda *args, **kwargs: (events.append("import"), import_result)[1],
            ),
            mock.patch.object(
                pipeline,
                "inventory_media",
                side_effect=lambda *args, **kwargs: (events.append("inventory"), inventory_result)[1],
            ),
            mock.patch.object(
                pipeline,
                "build_asset_manifest",
                side_effect=lambda *args, **kwargs: (events.append("manifest"), manifest_result)[1],
            ),
            mock.patch.object(
                pipeline,
                "export_batch",
                side_effect=lambda *args, **kwargs: (events.append("export"), export_result)[1],
            ),
            mock.patch.object(
                pipeline,
                "update_archive_index",
                side_effect=lambda *args, **kwargs: (events.append("index"), index_result)[1],
            ),
            mock.patch.object(pipeline, "render_inventory_summary", return_value="inventory summary"),
            mock.patch.object(pipeline, "render_manifest_summary", return_value="manifest summary"),
        )

    def test_library_import_has_no_console_or_archive_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment["USERPROFILE"] = temporary
            completed = subprocess.run(
                [sys.executable, "-c", "import gpt_exporter.pipeline"],
                cwd=REPOSITORY_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "")
            self.assertFalse(
                (Path(temporary) / "Documents" / "ChatGPT Archive").exists()
            )

    def test_pipeline_step_order_is_stable_and_source_deletes_only_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            _conversation, source = self._prepare_archive(
                root,
                batch_files=["conversation.json.xz"],
            )
            events: list[str] = []
            patches = self._patch_stages(events)

            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
                result = pipeline.archive_bundle(
                    archive_root=root,
                    source_bundle=source,
                    legacy_root=None,
                    progress=None,
                )

            self.assertEqual(events, ["import", "inventory", "manifest", "export", "index"])
            self.assertTrue(result.source_bundle_deleted)
            self.assertFalse(source.exists())

    def test_stage_failure_stops_pipeline_and_preserves_source_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            _conversation, source = self._prepare_archive(
                root,
                batch_files=["conversation.json.xz"],
            )
            events: list[str] = []
            import_result = SimpleNamespace(success=True)

            with (
                mock.patch.object(
                    pipeline,
                    "import_bundle",
                    side_effect=lambda *args, **kwargs: (events.append("import"), import_result)[1],
                ),
                mock.patch.object(
                    pipeline,
                    "inventory_media",
                    side_effect=lambda *args, **kwargs: (
                        events.append("inventory"),
                        (_ for _ in ()).throw(ValueError("synthetic inventory failure")),
                    )[1],
                ),
                mock.patch.object(pipeline, "build_asset_manifest") as manifest,
                mock.patch.object(pipeline, "export_batch") as export,
                mock.patch.object(pipeline, "update_archive_index") as index,
            ):
                with self.assertRaises(RuntimeError):
                    pipeline.archive_bundle(
                        archive_root=root,
                        source_bundle=source,
                        legacy_root=None,
                        progress=None,
                    )

            self.assertEqual(events, ["import", "inventory"])
            manifest.assert_not_called()
            export.assert_not_called()
            index.assert_not_called()
            self.assertTrue(source.is_file())

    def test_empty_current_batch_skips_export_but_still_updates_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            _conversation, source = self._prepare_archive(root, batch_files=[])
            events: list[str] = []
            patches = self._patch_stages(events)

            with patches[0], patches[1], patches[2], patches[3] as export, patches[4], patches[5], patches[6]:
                result = pipeline.archive_bundle(
                    archive_root=root,
                    source_bundle=source,
                    legacy_root=None,
                    progress=None,
                )

            self.assertEqual(events, ["import", "inventory", "manifest", "index"])
            export.assert_not_called()
            self.assertTrue(result.export_skipped)

    def test_convert_only_skips_import_and_exports_all_conversations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            self._prepare_archive(root, batch_files=[])
            events: list[str] = []
            patches = self._patch_stages(events)

            with patches[0] as importer, patches[1], patches[2], patches[3] as export, patches[4], patches[5], patches[6]:
                result = pipeline.archive_bundle(
                    archive_root=root,
                    convert_only=True,
                    legacy_root=None,
                    delete_source=False,
                    progress=None,
                )

            importer.assert_not_called()
            self.assertEqual(events, ["inventory", "manifest", "export", "index"])
            export.assert_called_once()
            self.assertIsNone(export.call_args.kwargs["batch_file"])
            self.assertFalse(result.export_skipped)

    def test_index_step_uses_explicit_archive_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            _conversation, source = self._prepare_archive(root, batch_files=[])
            events: list[str] = []
            patches = self._patch_stages(events)

            with patches[0], patches[1], patches[2], patches[3], patches[4] as update_index, patches[5], patches[6]:
                pipeline.archive_bundle(
                    archive_root=root,
                    source_bundle=source,
                    legacy_root=None,
                    delete_source=False,
                    progress=None,
                )

            update_index.assert_called_once_with(
                root.resolve(),
                downloads_dir=(root / "downloads").resolve(),
                database_path=(root / "conversations-index.sqlite").resolve(),
                progress=None,
            )


if __name__ == "__main__":
    unittest.main()
