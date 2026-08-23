import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import base64
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from gpt_exporter.export.docx import export_docx


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlF4dQAAAAASUVORK5CYII="
)


class DocxLibraryTests(unittest.TestCase):
    def _build_fixture(self, root: Path) -> tuple[Path, Path]:
        markdown_dir = root / "markdown"
        image_dir = root / "assets" / "image"
        attachment_dir = root / "assets" / "attachment"
        markdown_dir.mkdir(parents=True)
        image_dir.mkdir(parents=True)
        attachment_dir.mkdir(parents=True)

        (image_dir / "file_img1__pixel.png").write_bytes(PIXEL_PNG)
        (attachment_dir / "file_att1__note.txt").write_text(
            "synthetic note\n",
            encoding="utf-8",
        )

        markdown_path = markdown_dir / "synthetic.md"
        markdown_path.write_text(
            "# Synthetic DOCX\n\n"
            "## Bruno\n\n"
            "Hello **world**.\n\n"
            "![Pixel](../assets/image/file_img1__pixel.png)\n\n"
            "📎 **Archived attachment:** "
            "[note.txt](../assets/attachment/file_att1__note.txt)  \n"
            "Asset ID: `file_att1`  \n"
            "Archive path: `assets/attachment/file_att1__note.txt`\n\n"
            "Sandbox copy: [note.txt](sandbox:/mnt/data/note.txt)\n\n"
            "Unsafe entity must not create invalid XML: &#x0; done.\n",
            encoding="utf-8",
        )
        return markdown_path, root / "synthetic.docx"

    def test_library_creates_semantic_docx_with_image_and_local_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            markdown_path, output_path = self._build_fixture(root)
            progress: list[str] = []

            result = export_docx(
                markdown_path,
                output_path,
                overwrite=True,
                progress=progress.append,
            )

            self.assertFalse(result.skipped)
            self.assertEqual(result.output_path, output_path.resolve())
            self.assertGreater(result.size_bytes, 0)
            self.assertTrue(any(line.startswith("Converting:") for line in progress))
            self.assertTrue(any(line.startswith("Created:") for line in progress))

            with zipfile.ZipFile(output_path, "r") as archive:
                names = archive.namelist()
                document_xml = archive.read("word/document.xml").decode(
                    "utf-8", errors="strict"
                )
                relationships = archive.read(
                    "word/_rels/document.xml.rels"
                ).decode("utf-8", errors="strict")

            self.assertTrue(any(name.startswith("word/media/") for name in names))
            self.assertIn("Synthetic DOCX", document_xml)
            self.assertIn("Hello", document_xml)
            self.assertIn("world", document_xml)
            self.assertIn("note.txt", document_xml)
            self.assertIn("file_att1", document_xml)
            self.assertNotIn("\x00", document_xml)
            self.assertIn("file_att1__note.txt", relationships)

    def test_library_is_quiet_without_progress_callback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            markdown_path, output_path = self._build_fixture(root)
            captured = io.StringIO()

            with contextlib.redirect_stdout(captured):
                export_docx(
                    markdown_path,
                    output_path,
                    overwrite=True,
                )

            self.assertEqual(captured.getvalue(), "")

    def test_existing_non_empty_docx_is_preserved_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            markdown_path, output_path = self._build_fixture(root)
            original = b"existing synthetic docx placeholder"
            output_path.write_bytes(original)

            result = export_docx(
                markdown_path,
                output_path,
                overwrite=False,
            )

            self.assertTrue(result.skipped)
            self.assertEqual(output_path.read_bytes(), original)
            self.assertEqual(result.size_bytes, len(original))

    def test_library_call_does_not_mutate_sys_argv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            markdown_path, output_path = self._build_fixture(root)
            original = sys.argv[:]

            export_docx(
                markdown_path,
                output_path,
                overwrite=True,
            )

            self.assertEqual(sys.argv, original)

    def test_library_import_has_no_console_or_archive_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment["USERPROFILE"] = temporary

            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import gpt_exporter.export.docx",
                ],
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


if __name__ == "__main__":
    unittest.main()
