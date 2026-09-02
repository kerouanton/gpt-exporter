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


def _previous_report_path(paths: ArchivePaths, provider_key: str) -> Path:
    return paths.reports / "provider-validation" / provider_key / "latest.json"


def _result_is_mismatched(item: dict[str, object]) -> bool:
    if item.get("error"):
        return True
    match_fields = (
        "title_matches",
        "message_count_matches",
        "message_content_matches",
        "provenance_matches",
        "origins_match",
        "legacy_matches",
        "markdown_legacy_matches",
        "docx_legacy_matches",
    )
    return any(item.get(field) is False for field in match_fields)


def _mismatched_sources(paths: ArchivePaths, provider_key: str) -> list[Path]:
    report_path = _previous_report_path(paths, provider_key)
    if not report_path.is_file():
        raise FileNotFoundError(
            f"Previous validation report not found: {report_path}. Run --all or a normal validation first."
        )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    conversations = payload.get("conversations") or []
    if not isinstance(conversations, list):
        raise ValueError(f"Invalid conversations list in {report_path}")

    by_name = {
        candidate.name: candidate.resolve()
        for candidate in paths.downloads.rglob("*.json.xz")
        if candidate.is_file()
    }
    sources: list[Path] = []
    missing: list[str] = []
    for item in conversations:
        if not isinstance(item, dict) or not _result_is_mismatched(item):
            continue
        raw_source = item.get("source")
        if not isinstance(raw_source, str) or not raw_source:
            continue
        source = Path(raw_source)
        if source.is_file():
            sources.append(source.resolve())
            continue
        resolved = by_name.get(source.name)
        if resolved is None:
            missing.append(source.name)
        else:
            sources.append(resolved)

    if missing:
        raise FileNotFoundError(
            "Previous mismatch report references missing archived conversation(s): "
            + ", ".join(sorted(set(missing)))
        )
    if not sources:
        raise ValueError("Previous validation report contains no mismatched conversations.")
    return sorted(set(sources))


def _short_line(value: str, limit: int = 240) -> str:
    compact = value.replace("\t", "\\t")
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _first_markdown_excerpt(legacy_text: str, core_text: str) -> dict[str, object] | None:
    if legacy_text == core_text:
        return None
    legacy_lines = legacy_text.splitlines()
    core_lines = core_text.splitlines()
    common = min(len(legacy_lines), len(core_lines))
    for index in range(common):
        if legacy_lines[index] != core_lines[index]:
            start = max(0, index - 1)
            end = min(max(len(legacy_lines), len(core_lines)), index + 2)
            return {
                "line": index + 1,
                "legacy": _short_line(legacy_lines[index]),
                "core": _short_line(core_lines[index]),
                "legacy_context": [_short_line(line) for line in legacy_lines[start:min(end, len(legacy_lines))]],
                "core_context": [_short_line(line) for line in core_lines[start:min(end, len(core_lines))]],
            }
    return {
        "line": common + 1,
        "legacy": _short_line(legacy_lines[common]) if common < len(legacy_lines) else "<EOF>",
        "core": _short_line(core_lines[common]) if common < len(core_lines) else "<EOF>",
        "legacy_context": [],
        "core_context": [],
    }


def _augment_report_with_markdown_excerpts(report_path: Path) -> None:
    if not report_path.is_file():
        return
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    conversations = payload.get("conversations") or []
    if not isinstance(conversations, list):
        return

    oracle_root = report_path.parent / "export-oracle"
    changed = False
    for item in conversations:
        if not isinstance(item, dict) or item.get("markdown_legacy_matches") is not False:
            continue
        conversation_id = item.get("conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id:
            continue
        core_path = oracle_root / f"{conversation_id}-core.md"
        legacy_path = oracle_root / f"{conversation_id}-legacy.md"
        if not core_path.is_file() or not legacy_path.is_file():
            continue
        excerpt = _first_markdown_excerpt(
            legacy_path.read_text(encoding="utf-8"),
            core_path.read_text(encoding="utf-8"),
        )
        if excerpt is not None:
            item["markdown_excerpt"] = excerpt
            changed = True

    if changed:
        report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


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
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--all",
        action="store_true",
        help="Validate every archived conversation instead of reports/current-batch.json.",
    )
    selection.add_argument(
        "--mismatched",
        action="store_true",
        help="Revalidate only conversations marked mismatched/failed in the previous latest.json.",
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

    if arguments.all:
        sources = _all_sources(paths)
        selection_label = "complete archive"
    elif arguments.mismatched:
        # Resolve the previous mismatch list before validation recreates its diagnostics directory.
        sources = _mismatched_sources(paths, provider.key)
        selection_label = "previous mismatches only"
    else:
        sources = _batch_sources(paths)
        selection_label = "current batch"

    print(f"Provider    : {provider.display_name}")
    print(f"Archive root: {paths.root}")
    print(f"Sources     : {len(sources)} ({selection_label})")
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
    _augment_report_with_markdown_excerpts(result.report_path)

    print()
    print(f"Checked     : {result.checked}")
    print(f"Matched     : {result.matched}")
    print(f"Mismatched  : {result.mismatched}")
    print(f"Failed      : {result.failed}")
    print(f"Report      : {result.report_path}")
    return 0 if result.checked == result.matched and not result.failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
