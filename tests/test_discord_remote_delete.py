from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from gpt_exporter.core import CanonicalConversation, CanonicalMessage
from gpt_exporter.core.serialization import write_canonical_conversation
from gpt_exporter.providers.discord.ui.remote_delete_actions import DiscordRemoteDeleteActions
from gpt_exporter.workspaces import ConversationWorkspace


def canonical_message(message_id: str, author_name: str = "Gadget MCS") -> CanonicalMessage:
    return CanonicalMessage(
        message_id=message_id,
        role="user",
        author_id="350248805700075521",
        author_name=author_name,
        content=f"message {message_id}",
        created_at="2026-09-09T10:00:00+00:00",
        metadata={"provider": "discord"},
    )


def dry_run_payload(message_ids: tuple[str, ...], *, self_ids: set[str]) -> dict:
    messages = []
    for message_id in message_ids:
        is_self = message_id in self_ids
        messages.append(
            {
                "id": message_id,
                "timestamp": "2026-09-09T10:00:00.000Z",
                "author": {
                    "id": "350248805700075521" if is_self else "2",
                    "name": "Gadget MCS" if is_self else "soundy",
                    "is_self": is_self,
                    "self_detection": "discord-user-id",
                },
                "content": f"message {message_id}",
                "content_type": "text",
                "content_types": ["text"],
                "mentions": [],
                "links": [],
                "linked_media": [],
                "attachments": [],
                "external_previews": [],
                "stickers": [],
                "reply": None,
                "reactions": [],
                "edited": False,
                "resource_refs": [],
            }
        )
    return {
        "schema_version": 15,
        "exporter": "9c discord-exporter",
        "exported_at": "2026-09-09T10:10:00.000Z",
        "source_url": "https://discord.com/channels/@me/123456",
        "current_user": {
            "id": "350248805700075521",
            "display_name": "Gadget MCS",
            "username": "gadgetmcs",
        },
        "conversation": {
            "channel_id": "123456",
            "title": "(1) Discord | @soundy",
            "type": "dm",
            "participants": [],
        },
        "message_count": len(messages),
        "messages": messages,
        "diagnostics": {},
        "resources": {"counts": {}},
    }


class FakeApp:
    def __init__(self) -> None:
        self.status_var = SimpleNamespace(set=lambda _value: None)
        self.clipboard = ""

    def clipboard_clear(self) -> None:
        self.clipboard = ""

    def clipboard_append(self, value: str) -> None:
        self.clipboard += value

    def update_idletasks(self) -> None:
        pass


class DiscordRemoteDeleteTests(unittest.TestCase):
    def _actions(self, root: Path) -> DiscordRemoteDeleteActions:
        workspace = ConversationWorkspace("Discord", "discord", root)
        return DiscordRemoteDeleteActions(FakeApp(), workspace)

    def _canonical(self, root: Path, ids: tuple[str, ...]) -> Path:
        path = root / "downloads" / "soundy.json.xz"
        path.parent.mkdir(parents=True, exist_ok=True)
        write_canonical_conversation(
            path,
            CanonicalConversation(
                conversation_id="discord:123456",
                provider_id="discord",
                title="@soundy",
                messages=tuple(canonical_message(message_id) for message_id in ids),
            ),
        )
        return path

    def _dry_run(self, root: Path, ids: tuple[str, ...], self_ids: set[str]) -> Path:
        path = root / "discord-dm-export-v15_123456_test.json"
        path.write_text(json.dumps(dry_run_payload(ids, self_ids=self_ids)), encoding="utf-8")
        return path

    def test_plan_is_safe_only_when_every_remote_candidate_is_archived(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = self._canonical(root, ("100", "101", "102"))
            dry_run = self._dry_run(root, ("100", "101", "102"), {"100", "102"})
            actions = self._actions(root)

            plan = actions.prepare_remote_deletion(
                {
                    "conversation_id": "discord:123456",
                    "title": "@soundy",
                    "source_json_path": str(canonical),
                },
                dry_run,
            )

            self.assertTrue(plan.safe_to_execute)
            self.assertEqual(plan.remote_candidate_ids, ("100", "102"))
            self.assertEqual(plan.archived_candidate_ids, ("100", "102"))
            self.assertEqual(plan.missing_candidate_ids, ())
            self.assertEqual(plan.payload["current_user_id"], "350248805700075521")

    def test_plan_blocks_when_one_own_message_is_not_archived(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = self._canonical(root, ("100", "101"))
            dry_run = self._dry_run(root, ("100", "101", "102"), {"100", "102"})
            actions = self._actions(root)

            plan = actions.prepare_remote_deletion(
                {
                    "conversation_id": "discord:123456",
                    "title": "@soundy",
                    "source_json_path": str(canonical),
                },
                dry_run,
            )

            self.assertFalse(plan.safe_to_execute)
            self.assertEqual(plan.archived_candidate_ids, ("100",))
            self.assertEqual(plan.missing_candidate_ids, ("102",))

    def test_execute_payload_is_pinned_to_channel_user_and_exact_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = self._canonical(root, ("100", "101"))
            dry_run = self._dry_run(root, ("100", "101"), {"100"})
            actions = self._actions(root)
            plan = actions.prepare_remote_deletion(
                {
                    "conversation_id": "discord:123456",
                    "title": "@soundy",
                    "source_json_path": str(canonical),
                },
                dry_run,
            )

            self.assertTrue(actions.copy_remote_delete_execute(plan))
            payload = actions.app.clipboard
            self.assertIn('const EXPECTED_CHANNEL_ID = "123456";', payload)
            self.assertIn('const EXPECTED_CURRENT_USER_ID = "350248805700075521";', payload)
            self.assertIn('const CANDIDATE_IDS = ["100"]', payload)
            self.assertNotIn("__CANDIDATE_IDS_JSON__", payload)

    def test_execute_payload_uses_actions_inside_exact_message_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = self._canonical(root, ("100",))
            dry_run = self._dry_run(root, ("100",), {"100"})
            actions = self._actions(root)
            plan = actions.prepare_remote_deletion(
                {
                    "conversation_id": "discord:123456",
                    "title": "@soundy",
                    "source_json_path": str(canonical),
                },
                dry_run,
            )

            self.assertTrue(actions.copy_remote_delete_execute(plan))
            payload = actions.app.clipboard
            self.assertIn('root.querySelector(\'[role="group"][aria-label="Message Actions"]\')', payload)
            self.assertIn('normalize(element.getAttribute("aria-label")) === "more"', payload)
            self.assertIn('normalize(element.textContent) === "delete message"', payload)
            self.assertIn('document.getElementById(`chat-messages-${id}`)', payload)
            self.assertNotIn('root.querySelector(\'[aria-label="Message Actions"] [aria-label="Delete"]', payload)

    def test_execute_payload_reacquires_dom_and_deletes_only_one_message_per_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = self._canonical(root, ("100", "101"))
            dry_run = self._dry_run(root, ("100", "101"), {"100", "101"})
            actions = self._actions(root)
            plan = actions.prepare_remote_deletion(
                {
                    "conversation_id": "discord:123456",
                    "title": "@soundy",
                    "source_json_path": str(canonical),
                },
                dry_run,
            )

            self.assertTrue(actions.copy_remote_delete_execute(plan))
            payload = actions.app.clipboard
            self.assertIn("function materializedTargetRoot(id)", payload)
            self.assertIn("async function deleteOne(id)", payload)
            self.assertIn("const candidate = materializedTargetRoots().find", payload)
            self.assertIn("await deleteOne(candidate.id);", payload)
            self.assertNotIn("for (const { root, id } of materializedTargetRoots())", payload)
            self.assertIn("consecutiveFailures", payload)
            self.assertIn("backing off", payload)
            self.assertIn("await sleep(650);", payload)


if __name__ == "__main__":
    unittest.main()
