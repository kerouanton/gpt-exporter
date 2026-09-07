"""Build normalized DOCX derivatives from reconstructed legacy turns."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from gpt_exporter.legacy.canonical_docx_v10 import (
    CANONICAL_LEGACY_DOCX_VERSION,
    export_legacy_canonical_docx,
)
from gpt_exporter.paths import default_legacy_paths


file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")


def _stamp() -> str:
    return datetime.now().astimezone().strftime("%H:%M:%S")


def main(argv: list[str] | None = None) -> int:
    defaults = default_legacy_paths()
    parser = argparse.ArgumentParser(
        description=(
            "Generate normalized DOCX derivatives from legacy-docx-turns.json through "
            "the standard Markdown-to-DOCX renderer. Historical source DOCX files are never modified."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=defaults.turns,
        help=f"Normalized legacy turns JSON (default: {defaults.turns})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=defaults.normalized_docx,
        help=f"Directory for derived DOCX files and exported assets (default: {defaults.normalized_docx})",
    )
    parser.add_argument(
        "--docx-root",
        type=Path,
        default=defaults.sources,
        help=(
            "Root containing immutable historical DOCX files. The renderer restores "
            f"original Word structure and exports embedded assets (default: {defaults.sources})."
        ),
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace existing normalized derivatives")
    parser.add_argument("--limit", type=int, default=0, help="Generate only the first N conversations (0 = all)")
    args = parser.parse_args(argv)

    source = args.input.expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    conversations = payload.get("conversations")
    if not isinstance(conversations, list):
        raise ValueError("Expected normalized legacy turn collection")

    selected = conversations[: args.limit] if args.limit > 0 else conversations
    output_dir = args.output_dir.expanduser().resolve()
    docx_root = args.docx_root.expanduser().resolve()
    if not docx_root.is_dir():
        raise FileNotFoundError(f"Legacy source DOCX directory does not exist: {docx_root}")

    created = 0
    skipped = 0
    restored = 0
    total_turns = 0
    unknown_turns = 0
    asset_count = 0
    image_count = 0
    attachment_count = 0
    unresolved_asset_count = 0
    total_started = time.perf_counter()

    for index, conversation in enumerate(selected, start=1):
        if not isinstance(conversation, dict):
            continue
        source_name = str(conversation.get("source_file") or conversation.get("title") or f"conversation {index}")
        started = time.perf_counter()
        print(f"[{_stamp()}] START {index:02}/{len(selected):02} {source_name}", flush=True)
        result = export_legacy_canonical_docx(
            conversation,
            output_dir,
            overwrite=args.overwrite,
            docx_root=docx_root,
        )
        elapsed = time.perf_counter() - started
        total_turns += result.turn_count
        unknown_turns += result.unknown_turn_count
        restored += int(result.source_text_restored)
        asset_count += result.asset_count
        image_count += result.image_count
        attachment_count += result.attachment_count
        unresolved_asset_count += result.unresolved_asset_count
        if result.skipped:
            skipped += 1
            print(f"[{_stamp()}] DONE  {index:02}/{len(selected):02} {elapsed:7.2f}s Skipped: {result.output_path.name}", flush=True)
        else:
            created += 1
            print(
                f"[{_stamp()}] DONE  {index:02}/{len(selected):02} {elapsed:7.2f}s Created: {result.output_path.name} "
                f"(images={result.image_count}, attachments={result.attachment_count}, "
                f"unresolved={result.unresolved_asset_count})",
                flush=True,
            )

    total_elapsed = time.perf_counter() - total_started
    print(f"Canonical renderer: {CANONICAL_LEGACY_DOCX_VERSION}")
    print(f"Created DOCX: {created}")
    print(f"Skipped DOCX: {skipped}")
    print(f"Rendered turns: {total_turns}")
    print(f"Unknown turns preserved: {unknown_turns}")
    print(f"Source Word structure restored: {restored}/{len(selected)}")
    print(f"Exported assets: {asset_count}")
    print(f"  images: {image_count}")
    print(f"  attachments: {attachment_count}")
    print(f"Unresolved embedded relationships: {unresolved_asset_count}")
    print(f"Total elapsed: {total_elapsed:.2f}s")
    print(f"Source DOCX directory: {docx_root}")
    print(f"Turns JSON: {source}")
    print(f"Output directory: {output_dir}")
    return 0 if unresolved_asset_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
