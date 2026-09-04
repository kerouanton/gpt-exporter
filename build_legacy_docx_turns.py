import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Build compact normalized turns from classified legacy DOCX IR."""

import argparse
import json
from pathlib import Path

from gpt_exporter.legacy.model import LegacyBlock
from gpt_exporter.legacy.turns import TURN_BUILDER_VERSION, TURN_SCHEMA, build_turns


def _block_from_dict(payload: dict[str, object]) -> LegacyBlock:
    fields = LegacyBlock.__dataclass_fields__
    return LegacyBlock(**{name: payload[name] for name in fields if name in payload})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build normalized turns from classified legacy DOCX IR")
    parser.add_argument("input", type=Path, help="legacy-docx-ir-classified-v3.json")
    parser.add_argument("--output", type=Path, default=Path("legacy-docx-turns.json"))
    args = parser.parse_args(argv)

    payload = json.loads(args.input.expanduser().resolve().read_text(encoding="utf-8"))
    conversations = payload.get("conversations")
    if not isinstance(conversations, list):
        raise ValueError("Expected classified legacy conversation collection")

    output_conversations = []
    totals = {"user": 0, "assistant": 0, "unknown": 0}
    for conversation in conversations:
        if not isinstance(conversation, dict):
            raise ValueError("Invalid conversation entry")
        raw_blocks = conversation.get("blocks", [])
        blocks = tuple(_block_from_dict(block) for block in raw_blocks)
        turns = build_turns(blocks)
        counts = {"user": 0, "assistant": 0, "unknown": 0}
        for turn in turns:
            counts[turn.role] += 1
            totals[turn.role] += 1
        output_conversations.append({
            "source_filename": conversation.get("source_filename"),
            "source_sha256": conversation.get("source_sha256"),
            "title_hint": conversation.get("title_hint"),
            "category_hint": conversation.get("category_hint"),
            "date_hint": conversation.get("date_hint"),
            "starts_mid_conversation": conversation.get("starts_mid_conversation"),
            "role_inference_version": conversation.get("role_inference_version"),
            "turn_builder_version": TURN_BUILDER_VERSION,
            "turn_counts": counts,
            "turns": [turn.to_dict() for turn in turns],
        })

    result = {
        "schema": TURN_SCHEMA + "-collection",
        "source_schema": payload.get("schema"),
        "source_count": len(output_conversations),
        "role_inference_version": payload.get("role_inference_version"),
        "turn_builder_version": TURN_BUILDER_VERSION,
        "turn_counts": totals,
        "conversations": output_conversations,
    }
    output = args.output.expanduser().resolve()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Turn builder: {TURN_BUILDER_VERSION}")
    print(f"User turns: {totals['user']}")
    print(f"Assistant turns: {totals['assistant']}")
    print(f"Unknown turns: {totals['unknown']}")
    print(f"Normalized turns: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
