"""Promote completed legacy-DOCX turns into canonical provider JSON/XZ.

This is a one-time ChatGPT-provider migration. It deliberately does not read the
historical DOCX files. Once promotion is validated, canonical JSON/XZ becomes
sufficient for indexing/rebuild and the DOCX migration pipeline is no longer a
runtime dependency.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from gpt_exporter.core import CanonicalConversation, CanonicalMessage
from gpt_exporter.core.serialization import (
    read_canonical_conversation,
    write_canonical_conversation,
)
from gpt_exporter.paths import default_archive_paths, default_legacy_paths


PROMOTION_VERSION = "legacy-docx-canonical-promotion-v1"


def _legacy_conversation_id(source_sha256: str) -> str:
    return f"legacy-docx-{source_sha256.lower()}"


def _date_hint_iso(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    return value + "T00:00:00" if len(value) == 10 else value


def _conversation_from_legacy(payload: dict[str, Any]) -> CanonicalConversation:
    source_sha = str(payload.get("source_sha256") or "").strip().lower()
    if len(source_sha) != 64:
        raise ValueError("Legacy conversation requires a 64-character source_sha256")

    raw_turns = payload.get("turns")
    if not isinstance(raw_turns, list):
        raise ValueError("Legacy conversation requires a turns list")

    messages: list[CanonicalMessage] = []
    for position, turn in enumerate(raw_turns, start=1):
        if not isinstance(turn, dict):
            continue
        content = str(turn.get("content") or "").strip()
        if not content:
            continue
        metadata = {
            key: turn[key]
            for key in (
                "confidence",
                "block_count",
                "first_order",
                "last_order",
                "source_orders",
                "block_kinds",
            )
            if key in turn
        }
        messages.append(
            CanonicalMessage(
                message_id=f"legacy-turn-{position:04d}",
                role=str(turn.get("role") or "unknown"),
                content=content,
                metadata=metadata,
            )
        )

    source_filename = str(payload.get("source_filename") or "").strip()
    title = str(payload.get("title_hint") or "").strip()
    if not title:
        title = Path(source_filename).stem if source_filename else "Untitled legacy conversation"
    category = str(payload.get("category_hint") or "").strip()

    provenance = {
        "migration": "legacy_docx",
        "promotion_version": PROMOTION_VERSION,
        "source_sha256": source_sha,
        "source_filename": source_filename or None,
        "parser_version": payload.get("parser_version"),
        "role_inference_version": payload.get("role_inference_version"),
        "turn_builder_version": payload.get("turn_builder_version"),
        "starts_mid_conversation": payload.get("starts_mid_conversation"),
    }

    return CanonicalConversation(
        conversation_id=_legacy_conversation_id(source_sha),
        provider_id="gpt",
        title=title,
        messages=tuple(messages),
        created_at=_date_hint_iso(payload.get("date_hint")),
        updated_at=_date_hint_iso(payload.get("date_hint")),
        category_hints=(category,) if category else (),
        metadata=provenance,
    )


def promote_collection(
    input_path: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> dict[str, object]:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    conversations = payload.get("conversations")
    if not isinstance(conversations, list):
        raise ValueError("Expected legacy turn collection")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    created = 0
    skipped = 0
    source_roles: Counter[str] = Counter()
    written_roles: Counter[str] = Counter()
    written_messages = 0

    expected_ids: set[str] = set()
    for raw in conversations:
        if not isinstance(raw, dict):
            raise ValueError("Invalid legacy conversation entry")
        conversation = _conversation_from_legacy(raw)
        if conversation.conversation_id in expected_ids:
            raise ValueError(f"Duplicate canonical conversation id: {conversation.conversation_id}")
        expected_ids.add(conversation.conversation_id)
        for message in conversation.messages:
            source_roles[message.role] += 1

        destination = output_dir / f"{conversation.conversation_id}.json.xz"
        if destination.exists() and not overwrite:
            skipped += 1
        else:
            write_canonical_conversation(destination, conversation)
            created += 1

        roundtrip = read_canonical_conversation(destination)
        if roundtrip.conversation_id != conversation.conversation_id:
            raise ValueError(f"Round-trip id mismatch: {destination}")
        if roundtrip.messages != conversation.messages:
            raise ValueError(f"Round-trip message mismatch: {destination}")
        for message in roundtrip.messages:
            written_roles[message.role] += 1
            written_messages += 1

    if written_roles != source_roles:
        raise ValueError(f"Role-count mismatch after canonical promotion: {source_roles} != {written_roles}")

    return {
        "source_conversations": len(conversations),
        "canonical_conversations": len(expected_ids),
        "created": created,
        "skipped": skipped,
        "messages": written_messages,
        "roles": dict(sorted(written_roles.items())),
        "output_dir": str(output_dir.resolve()),
    }


def main(argv: list[str] | None = None) -> int:
    archive = default_archive_paths()
    legacy = default_legacy_paths()
    parser = argparse.ArgumentParser(
        description=(
            "Promote completed legacy DOCX turn JSON into provider-neutral canonical JSON/XZ. "
            "Historical DOCX files are not read."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=legacy.turns_json,
        help=f"Legacy turn collection (default: {legacy.turns_json})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=archive.downloads / "gpt" / "legacy-docx",
        help="Canonical conversation output directory",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    result = promote_collection(
        args.input.expanduser().resolve(),
        args.output_dir.expanduser().resolve(),
        overwrite=args.overwrite,
    )
    print(f"Promotion version: {PROMOTION_VERSION}")
    print(f"Source conversations: {result['source_conversations']}")
    print(f"Canonical conversations: {result['canonical_conversations']}")
    print(f"Created: {result['created']}")
    print(f"Skipped: {result['skipped']}")
    print(f"Messages: {result['messages']}")
    print(f"Roles: {result['roles']}")
    print(f"Output: {result['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
