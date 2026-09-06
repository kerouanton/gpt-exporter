"""Build normalized DOCX derivatives from reconstructed legacy turns."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from gpt_exporter.legacy.canonical_docx_v9 import (
    CANONICAL_LEGACY_DOCX_VERSION,
    export_legacy_canonical_docx,
)


file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate normalized DOCX derivatives from legacy-docx-turns.json through "
            "the standard Markdown-to-DOCX renderer. Historical source DOCX files are never modified."
        )
    )
    parser.add_argument("input", type=Path, help="legacy-docx-turns.json")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("legacy-normalized-docx"),
        help="Directory for derived DOCX files and exported assets (default: legacy-normalized-docx)",
    )
    parser.add_argument(
        "--docx-root",
        type=Path,
        default=None,
        help=(
            "Optional root containing immutable historical DOCX files. When supplied, "
            "the renderer restores original Word structure and exports embedded assets."
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
    docx_root = args.docx_root.expanduser().resolve() if args.docx_root is not None else None
    created = 0
    skipped = 0
    restored = 0
    total_turns = 0
    unknown_turns = 0
    asset_count = 0
    image_count = 0
    attachment_count = 0
    unresolved_asset_count = 0

    for conversation in selected:
        if not isinstance(conversation, dict):
            continue
        result = export_legacy_canonical_docx(
            conversation,
            output_dir,
            overwrite=args.overwrite,
            docx_root=docx_root,
        )
        total_turns += result.turn_count
        unknown_turns += result.unknown_turn_count
        restored += int(result.source_text_restored)
        asset_count += result.asset_count
        image_count += result.image_count
        attachment_count += result.attachment_count
        unresolved_asset_count += result.unresolved_asset_count
        if result.skipped:
            skipped += 1
            print(f"Skipped existing: {result.output_path.name}")
        else:
            created += 1
            print(
                f"Created: {result.output_path.name} "
                f"(images={result.image_count}, attachments={result.attachment_count}, "
                f"unresolved={result.unresolved_asset_count})"
            )

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
    print(f"Output directory: {output_dir}")
    return 0 if unresolved_asset_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
