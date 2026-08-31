"""Explicit CORE/legacy compatibility validation command.

This command is intentionally separate from the normal archive workflow. The
full shadow + legacy oracle is useful while migrating providers, but it is too
expensive to run after every incremental archive update.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gpt_exporter.paths import ArchivePaths, default_archive_paths
from gpt_exporter.providers import BUILTIN_PROVIDERS
from gpt_exporter.validation import run_normalized_shadow_validation


def _batch_sources(paths: ArchivePaths) -> list[Path]:
    batch_path = paths.reports / "current-batch.json"
    if not batch_path.is_file():
        raise FileNotFoundError(f"Current batch not found: {batch_path}")

    payload = json.loads(batch_path.read_text(encoding="utf-8"))
    names = payload.get("conversation_files") or []
    if not isinstance(names, list):
        raise ValueError(f"Invalid conversation_files in {batch_path}")

    by_name = {
        candidate.name: candidate
        for candidate in paths.downloads.rglob("*.json.xz")
        if candidate.is_file()
    }
    sources: list[Path] = []
    missing: list[str] = []
    for raw_name in names:
        if not isinstance(raw_name, str):
            continue
        candidate = Path(raw_name)
        if candidate.is_absolute() and candidate.is_file():
            sources.append(candidate.resolve())
            continue
        resolved = by_name.get(candidate.name)
        if resolved is None:
            missing.append(candidate.name)
        else:
            sources.append(resolved.resolve())

    if missing:
        raise FileNotFoundError(
            "Current batch references missing archived conversation(s): "
            + ", ".join(sorted(missing))
        )
    if not sources:
        raise ValueError(
            "Current batch contains no changed conversations. Use --all to validate the complete archive."
        )
    return sorted(sources)


def _all_sources(paths: ArchivePaths) -> list[Path]:
    sources = sorted(path.resolve() for path in paths.downloads.rglob("*.json.xz") if path.is_file())
    if not sources:
        raise FileNotFoundError(f"No compressed conversations found under {paths.downloads}")
    return sources


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run explicit CORE/shadow/legacy compatibility validation."
    )
    parser.add_argument(
        "--provider",
        default="chatgpt",
        help="Provider key (default: chatgpt).",
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=None,
        help="Archive root. Defaults to the selected provider's standard archive directory.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate every archived conversation instead of reports/current-batch.json.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    provider = BUILTIN_PROVIDERS.get(arguments.provider)
    paths = (
        ArchivePaths.from_root(arguments.archive_root.expanduser().resolve())
        if arguments.archive_root is not None
        else default_archive_paths(archive_directory_name=provider.archive_directory_name)
    )

    sources = _all_sources(paths) if arguments.all else _batch_sources(paths)
    print(f"Provider    : {provider.display_name}")
    print(f"Archive root: {paths.root}")
    print(f"Sources     : {len(sources)}")
    print("Validation  : CORE production + shadow CORE + legacy index/export")
    print()

    result = run_normalized_shadow_validation(
        provider,
        sources,
        archive_root=paths.root,
        production_database=paths.database,
        compare_with_legacy_oracle=True,
        progress=print,
    )

    print()
    print(f"Checked     : {result.checked}")
    print(f"Matched     : {result.matched}")
    print(f"Mismatched  : {result.mismatched}")
    print(f"Failed      : {result.failed}")
    print(f"Report      : {result.report_path}")
    return 0 if result.checked == result.matched and not result.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
