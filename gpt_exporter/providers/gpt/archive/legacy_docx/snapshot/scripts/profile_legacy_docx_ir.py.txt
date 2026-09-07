import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Profile Word-layout signatures from legacy DOCX intermediate JSON."""

import argparse
import collections
import json
from pathlib import Path


EXPECTED_SCHEMA = "gpt-exporter-legacy-conversation-v2-collection"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a compact Word-layout profile from legacy DOCX IR v2."
    )
    parser.add_argument("input", type=Path, help="legacy-docx-ir.json generated from v2")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("legacy-docx-profile.json"),
        help="Profile output path (default: legacy-docx-profile.json)",
    )
    parser.add_argument(
        "--examples-per-signature",
        type=int,
        default=4,
        help="Maximum text examples retained per layout signature",
    )
    return parser


def _signature(block: dict[str, object]) -> tuple[object, ...]:
    return (
        block.get("kind"),
        block.get("style"),
        block.get("blank_blocks_before", 0),
        block.get("alignment"),
        block.get("left_indent_emu"),
        block.get("right_indent_emu"),
        block.get("first_line_indent_emu"),
        block.get("shading_fill"),
        bool(block.get("has_borders")),
        bool(block.get("has_numbering")),
        block.get("run_count", 0),
        block.get("bold_run_count", 0),
        block.get("italic_run_count", 0),
        block.get("hyperlink_count", 0),
    )


def _signature_dict(signature: tuple[object, ...]) -> dict[str, object]:
    keys = (
        "kind",
        "style",
        "blank_blocks_before",
        "alignment",
        "left_indent_emu",
        "right_indent_emu",
        "first_line_indent_emu",
        "shading_fill",
        "has_borders",
        "has_numbering",
        "run_count",
        "bold_run_count",
        "italic_run_count",
        "hyperlink_count",
    )
    return dict(zip(keys, signature, strict=True))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.input.expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("schema") != EXPECTED_SCHEMA:
        raise ValueError(
            f"Expected {EXPECTED_SCHEMA!r}, got {payload.get('schema')!r}. "
            "Regenerate the IR with the current feature/legacy-docx-import branch."
        )

    examples_per_signature = max(1, args.examples_per_signature)
    counts: collections.Counter[tuple[object, ...]] = collections.Counter()
    examples: dict[tuple[object, ...], list[dict[str, object]]] = collections.defaultdict(list)
    kind_counts: collections.Counter[str] = collections.Counter()
    blank_counts: collections.Counter[int] = collections.Counter()

    for conversation in payload.get("conversations", []):
        filename = conversation.get("source_filename")
        for block in conversation.get("blocks", []):
            kind = str(block.get("kind", "unknown"))
            kind_counts[kind] += 1
            blank_counts[int(block.get("blank_blocks_before", 0) or 0)] += 1
            if kind not in {"paragraph", "heading"}:
                continue
            signature = _signature(block)
            counts[signature] += 1
            if len(examples[signature]) < examples_per_signature:
                text = str(block.get("text", ""))
                examples[signature].append(
                    {
                        "source_filename": filename,
                        "order": block.get("order"),
                        "text": text[:500],
                    }
                )

    signatures = []
    for signature, count in counts.most_common():
        signatures.append(
            {
                "count": count,
                "features": _signature_dict(signature),
                "examples": examples[signature],
            }
        )

    result = {
        "schema": "gpt-exporter-legacy-docx-profile-v1",
        "source_schema": payload.get("schema"),
        "source_count": payload.get("source_count"),
        "kind_counts": dict(kind_counts),
        "blank_blocks_before_counts": {
            str(key): value for key, value in sorted(blank_counts.items())
        },
        "signature_count": len(signatures),
        "signatures": signatures,
    }

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Profiled {payload.get('source_count', 0)} legacy conversation(s)")
    print(f"Layout signatures: {len(signatures)}")
    print(f"Profile: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
