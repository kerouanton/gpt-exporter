import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import json
import lzma
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "characterization"
IMPORT_SCRIPT = PROJECT_ROOT / "import_browser_bundle.py"
CONVERSATION_ID = "conv-characterization-001"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def write_bundle(path: Path, conversation_fixture: str) -> None:
    payload = load_fixture("bundle_base.json")
    payload["conversations"] = [load_fixture(conversation_fixture)]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_import(user_profile: Path, bundle_path: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["USERPROFILE"] = str(user_profile)
    return subprocess.run(
        [sys.executable, str(IMPORT_SCRIPT), str(bundle_path)],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def find_archived_conversation(user_profile: Path) -> Path:
    downloads = user_profile / "Documents" / "ChatGPT Archive" / "downloads"
    matches = sorted(downloads.glob(f"*_{CONVERSATION_ID}.json.xz"))
    if len(matches) != 1:
        raise AssertionError(f"Expected exactly one archived conversation, found {matches}")
    return matches[0]


def read_archived_conversation(path: Path) -> dict:
    with lzma.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


class V28ImportCharacterizationTests(unittest.TestCase):
    def test_larger_incoming_conversation_replaces_stored_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            bundle = profile / "bundle.json"

            write_bundle(bundle, "conversation_base.json")
            first = run_import(profile, bundle)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            archived_path = find_archived_conversation(profile)
            base_size = archived_path.stat().st_size

            write_bundle(bundle, "conversation_extended.json")
            second = run_import(profile, bundle)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

            updated_path = find_archived_conversation(profile)
            stored = read_archived_conversation(updated_path)
            self.assertEqual(stored["current_node"], "node-assistant-2")
            self.assertGreater(updated_path.stat().st_size, base_size)
            self.assertIn("Imported conversation:", second.stdout)

    def test_shorter_incoming_conversation_never_replaces_larger_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            bundle = profile / "bundle.json"

            write_bundle(bundle, "conversation_extended.json")
            first = run_import(profile, bundle)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            archived_path = find_archived_conversation(profile)
            original_bytes = archived_path.read_bytes()

            write_bundle(bundle, "conversation_shorter.json")
            second = run_import(profile, bundle)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

            preserved_path = find_archived_conversation(profile)
            self.assertEqual(preserved_path.read_bytes(), original_bytes)
            stored = read_archived_conversation(preserved_path)
            self.assertEqual(stored["current_node"], "node-assistant-2")
            self.assertIn("Preserved conversation:", second.stdout)

    def test_equal_incoming_conversation_is_preserved_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            bundle = profile / "bundle.json"

            write_bundle(bundle, "conversation_base.json")
            first = run_import(profile, bundle)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            archived_path = find_archived_conversation(profile)
            original_bytes = archived_path.read_bytes()

            second = run_import(profile, bundle)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

            preserved_path = find_archived_conversation(profile)
            self.assertEqual(preserved_path.read_bytes(), original_bytes)
            self.assertIn("Preserved conversation:", second.stdout)

    def test_current_batch_lists_only_written_or_enlarged_conversations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            bundle = profile / "bundle.json"
            reports = profile / "Documents" / "ChatGPT Archive" / "reports"

            write_bundle(bundle, "conversation_base.json")
            first = run_import(profile, bundle)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

            batch_files = sorted(reports.glob("*batch*.json"))
            self.assertTrue(batch_files, f"No batch file found in {reports}")
            first_batch = json.loads(batch_files[-1].read_text(encoding="utf-8"))
            self.assertEqual(len(first_batch.get("conversation_files", [])), 1)

            write_bundle(bundle, "conversation_shorter.json")
            second = run_import(profile, bundle)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

            batch_files = sorted(reports.glob("*batch*.json"))
            self.assertTrue(batch_files, f"No batch file found in {reports}")
            second_batch = json.loads(batch_files[-1].read_text(encoding="utf-8"))
            self.assertEqual(second_batch.get("conversation_files", []), [])


if __name__ == "__main__":
    unittest.main()
