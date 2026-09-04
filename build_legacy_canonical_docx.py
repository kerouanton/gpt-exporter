import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Build normalized DOCX derivatives from reconstructed legacy turns."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gpt_exporter.legacy.canonical_docx import (
    CANONICAL_LEGACY_DOCX_VERSION,
    export_legacy_canonical_docx,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate separate normalized DOCX derivatives from legacy-docx-turns.json. "
            "Historical source DOCX files are never modified."
        )
    )
    parser.add_argument("input", type=Path, help="legacy-docx-turns.json")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("legacy-normalized-docx"),
        help="Directory for derived DOCX files (default: legacy-normalized-docx)",
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
    created = 0
    skipped = 0
    total_turns = 0
    unknown_turns = 0

    for conversation in selected:
        if not isinstance(conversation, dict):
            continue
        result = export_legacy_canonical_docx(
            conversation,
            output_dir,
            overwrite=args.overwrite,
        )
        total_turns += result.turn_count
        unknown_turns += result.unknown_turn_count
        if result.skipped:
            skipped += 1
            print(f"Skipped existing: {result.output_path.name}")
        else:
            created += 1
            print(f"Created: {result.output_path.name}")

    print(f"Canonical renderer: {CANONICAL_LEGACY_DOCX_VERSION}")
    print(f"Created DOCX: {created}")
    print(f"Skipped DOCX: {skipped}")
    print(f"Rendered turns: {total_turns}")
    print(f"Unknown turns preserved: {unknown_turns}")
    print(f"Output directory: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
