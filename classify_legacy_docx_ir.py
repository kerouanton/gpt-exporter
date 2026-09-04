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
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("legacy-docx-role-summary.json"),
        help="Compact role-run summary output path",
    )
    return parser


def _block_from_dict(payload: dict[str, object]) -> LegacyBlock:
    fields = LegacyBlock.__dataclass_fields__
    return LegacyBlock(**{name: payload[name] for name in fields if name in payload})


def _role_runs(blocks: tuple[LegacyBlock, ...]) -> list[dict[str, object]]:
    """Collapse contiguous classified blocks into turn-like role runs.

    These are deliberately called role runs rather than turns: the classifier
    may still miss a weak speaker transition, but the runs are a much more
    useful validation unit than raw Word block totals.
    """

    runs: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for block in blocks:
        if block.kind == "hyperlink_sentinel":
            continue

        if current is None or current["role"] != block.role:
            current = {
                "role": block.role,
                "block_count": 0,
                "first_order": block.order,
                "last_order": block.order,
                "first_text": block.text[:240],
                "max_confidence": block.role_confidence,
            }
            runs.append(current)

        current["block_count"] = int(current["block_count"]) + 1
        current["last_order"] = block.order
        confidence_rank = {"none": 0, "low": 1, "medium": 2, "high": 3}
        if confidence_rank.get(block.role_confidence, 0) > confidence_rank.get(
            str(current["max_confidence"]), 0
        ):
            current["max_confidence"] = block.role_confidence

    return runs


def classify_payload(payload: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    conversations = payload.get("conversations")
    if not isinstance(conversations, list):
        raise ValueError("Expected a legacy conversation collection")

    output_conversations = []
    summary_conversations = []
    role_counts = {"user": 0, "assistant": 0, "unknown": 0}
    confidence_counts: dict[str, int] = {}
    role_confidence_counts: dict[str, dict[str, int]] = {
        "user": {},
        "assistant": {},
        "unknown": {},
    }
    role_run_counts = {"user": 0, "assistant": 0, "unknown": 0}

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
            by_role = role_confidence_counts[block.role]
            by_role[block.role_confidence] = by_role.get(block.role_confidence, 0) + 1

        runs = _role_runs(inferred)
        conversation_run_counts = {"user": 0, "assistant": 0, "unknown": 0}
        for run in runs:
            role = str(run["role"])
            conversation_run_counts[role] += 1
            role_run_counts[role] += 1

        updated = dict(conversation)
        updated["blocks"] = blocks
        updated["role_inference_version"] = ROLE_INFERENCE_VERSION
        output_conversations.append(updated)

        summary_conversations.append(
            {
                "source_filename": conversation.get("source_filename"),
                "title_hint": conversation.get("title_hint"),
                "starts_mid_conversation": conversation.get("starts_mid_conversation"),
                "block_count": len(inferred),
                "role_block_counts": {
                    role: sum(1 for block in inferred if block.role == role)
                    for role in ("user", "assistant", "unknown")
                },
                "role_run_counts": conversation_run_counts,
                "role_runs": runs,
            }
        )

    result = dict(payload)
    result["schema"] = "gpt-exporter-legacy-conversation-v2-classified-collection"
    result["role_inference_version"] = ROLE_INFERENCE_VERSION
    result["role_counts"] = role_counts
    result["role_confidence_counts"] = confidence_counts
    result["role_confidence_by_role"] = role_confidence_counts
    result["role_run_counts"] = role_run_counts
    result["conversations"] = output_conversations

    summary = {
        "schema": "gpt-exporter-legacy-role-summary-v1",
        "source_count": len(summary_conversations),
        "role_inference_version": ROLE_INFERENCE_VERSION,
        "role_block_counts": role_counts,
        "role_run_counts": role_run_counts,
        "conversations": summary_conversations,
    }
    return result, summary


def _format_confidence(counts: dict[str, int]) -> str:
    order = ("high", "medium", "low", "none")
    return ", ".join(f"{name}={counts.get(name, 0)}" for name in order)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.input.expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    result, summary = classify_payload(payload)

    output = args.output.expanduser().resolve()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary_output = args.summary.expanduser().resolve()
    summary_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    counts = result["role_counts"]
    by_role = result["role_confidence_by_role"]
    runs = result["role_run_counts"]
    print(f"Role inference: {result['role_inference_version']}")
    print(f"User blocks: {counts['user']} ({_format_confidence(by_role['user'])})")
    print(f"Assistant blocks: {counts['assistant']} ({_format_confidence(by_role['assistant'])})")
    print(f"Unknown blocks: {counts['unknown']} ({_format_confidence(by_role['unknown'])})")
    print(f"User role runs: {runs['user']}")
    print(f"Assistant role runs: {runs['assistant']}")
    print(f"Unknown role runs: {runs['unknown']}")
    print(f"Classified IR: {output}")
    print(f"Compact summary: {summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
