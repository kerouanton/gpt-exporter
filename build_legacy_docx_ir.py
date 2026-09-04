import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Build versioned intermediate JSON from legacy ChatGPT DOCX files."""

import argparse
import json
from pathlib import Path

from gpt_exporter.legacy import LEGACY_SCHEMA, parse_legacy_conversation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build non-destructive intermediate JSON for legacy ChatGPT DOCX files. "
            "Source DOCX, canonical archive, and SQLite index are not modified."
        )
    )
    parser.add_argument("path", type=Path, help="DOCX file or directory")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("legacy-docx-ir.json"),
        help="Aggregate JSON output path (default: legacy-docx-ir.json)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not recurse into subdirectories",
    )
    return parser


def _paths(source: Path, *, recursive: bool) -> list[Path]:
    source = source.expanduser().resolve()
    if source.is_file():
        if source.suffix.lower() != ".docx":
            raise ValueError(f"Expected a .docx file: {source}")
        return [source]
    if not source.is_dir():
        raise FileNotFoundError(source)
    iterator = source.rglob("*.docx") if recursive else source.glob("*.docx")
    return sorted(iterator, key=lambda item: str(item).casefold())


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = _paths(args.path, recursive=not args.no_recursive)
    conversations = [parse_legacy_conversation(path) for path in paths]
    payload = {
        "schema": f"{LEGACY_SCHEMA}-collection",
        "source_count": len(conversations),
        "conversations": [conversation.to_dict() for conversation in conversations],
    }
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Parsed {len(conversations)} legacy DOCX file(s)")
    print(f"Intermediate representation: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
