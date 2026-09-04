import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Annotate legacy DOCX IR v2 with conservative User/Assistant roles."""

import argparse
import json
from pathlib import Path

from gpt_exporter.legacy.model import LegacyBlock
from gpt_exporter.legacy.roles import ROLE_INFERENCE_VERSION, infer_roles


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Classify structurally anchored legacy DOCX segments. "
            "Ambiguous segments remain role=unknown."
        )
    )
    parser.add_argument("input", type=Path, help="legacy-docx-ir-v2.json")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("legacy-docx-ir-classified.json"),
        help="Annotated JSON output path",
    )
    return parser


def _block_from_dict(payload: dict[str, object]) -> LegacyBlock:
    fields = LegacyBlock.__dataclass_fields__
    return LegacyBlock(**{name: payload[name] for name in fields if name in payload})


def classify_payload(payload: dict[str, object]) -> dict[str, object]:
    conversations = payload.get("conversations")
    if not isinstance(conversations, list):
        raise ValueError("Expected a legacy conversation collection")

    output_conversations = []
    role_counts = {"user": 0, "assistant": 0, "unknown": 0}
    confidence_counts: dict[str, int] = {}

    for conversation in conversations:
        if not isinstance(conversation, dict):
            raise ValueError("Invalid conversation entry")
        raw_blocks = conversation.get("blocks", [])
        if not isinstance(raw_blocks, list):
            raise ValueError("Invalid blocks entry")
        inferred = infer_roles(tuple(_block_from_dict(block) for block in raw_blocks))
        blocks = []
        for block in inferred:
            item = dict(block.__dict__) if hasattr(block, "__dict__") else {
                name: getattr(block, name) for name in LegacyBlock.__dataclass_fields__
            }
            blocks.append(item)
            role_counts[block.role] += 1
            confidence_counts[block.role_confidence] = confidence_counts.get(block.role_confidence, 0) + 1

        updated = dict(conversation)
        updated["blocks"] = blocks
        updated["role_inference_version"] = ROLE_INFERENCE_VERSION
        output_conversations.append(updated)

    result = dict(payload)
    result["schema"] = "gpt-exporter-legacy-conversation-v2-classified-collection"
    result["role_inference_version"] = ROLE_INFERENCE_VERSION
    result["role_counts"] = role_counts
    result["role_confidence_counts"] = confidence_counts
    result["conversations"] = output_conversations
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.input.expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    result = classify_payload(payload)
    output = args.output.expanduser().resolve()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = result["role_counts"]
    print(f"User blocks: {counts['user']}")
    print(f"Assistant blocks: {counts['assistant']}")
    print(f"Unknown blocks: {counts['unknown']}")
    print(f"Classified IR: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
