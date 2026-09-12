import unittest

from export_provider_discord.naming import (
    dm_artifact_stem,
    dm_peer,
    dm_title,
    is_group_dm,
)


class DiscordNamingTests(unittest.TestCase):
    def test_unresolved_peer_is_not_replaced_by_local_user(self) -> None:
        metadata = {
            "participants": [
                {
                    "id": "350248805700075521",
                    "name": "Gadget MCS",
                    "is_self": True,
                },
                {
                    "id": None,
                    "name": "a33z",
                    "is_self": None,
                },
                {
                    "id": None,
                    "name": None,
                    "is_self": None,
                },
            ],
            "current_user": {
                "id": "350248805700075521",
                "display_name": "Gadget MCS",
                "username": "gadgetmcs",
            },
        }

        peer = dm_peer(metadata)

        self.assertIsNotNone(peer)
        self.assertEqual(peer["name"], "a33z")
        self.assertEqual(
            dm_title(metadata, "(101) Discord | @a33z"),
            "Gadget MCS ↔ a33z",
        )
        self.assertEqual(
            dm_artifact_stem(metadata, "1467602455704371264"),
            "Discord DM Gadget MCS ↔ a33z 1467602455704371264",
        )

    def test_explicit_non_self_peer_still_wins(self) -> None:
        metadata = {
            "participants": [
                {"id": "self", "name": "Me", "is_self": True},
                {"id": "peer", "name": "TomZ", "is_self": False},
            ],
            "current_user": {"id": "self", "username": "me"},
        }

        self.assertEqual(dm_peer(metadata)["name"], "TomZ")
        self.assertEqual(dm_title(metadata, "Discord | @TomZ"), "me ↔ TomZ")

    def test_title_matches_artifact_identity_order(self) -> None:
        metadata = {
            "participants": [
                {
                    "id": "little",
                    "name": "Littleloulita",
                    "display_name": "Littleloulita",
                    "is_self": True,
                },
                {
                    "id": "gadget",
                    "name": "Gadget MCS",
                    "display_name": "Gadget MCS",
                    "is_self": False,
                },
            ],
            "current_user": {
                "id": "little",
                "display_name": "Littleloulita",
                "username": "littleloulita",
            },
        }

        self.assertEqual(
            dm_title(metadata, "@Gadget MCS"),
            "Littleloulita ↔ Gadget MCS",
        )
        self.assertEqual(
            dm_artifact_stem(metadata, "994497416583708703"),
            "Discord DM Littleloulita ↔ Gadget MCS 994497416583708703",
        )

    def test_group_dm_uses_group_name_in_title_and_artifacts(self) -> None:
        metadata = {
            "conversation_type": "dm",
            "participants": [
                {"id": None, "name": None, "is_self": None},
                {"id": "little", "name": "Littleloulita", "is_self": False},
                {"id": "moon", "name": "moomoon", "is_self": False},
                {"id": "self", "name": "Gadget MCS", "is_self": True},
                {"id": "angel", "name": "Angelmunks 🪽", "is_self": False},
            ],
            "current_user": {
                "id": "self",
                "display_name": "Gadget MCS",
                "username": "gadgetmcs",
            },
        }

        self.assertTrue(is_group_dm(metadata))
        self.assertEqual(
            dm_title(metadata, "(104) Discord | la Tanière Orga"),
            "la Tanière Orga",
        )
        self.assertEqual(metadata["conversation_type"], "group_dm")
        self.assertEqual(metadata["group_name"], "la Tanière Orga")
        self.assertEqual(
            dm_artifact_stem(metadata, "1461351991145140234"),
            "Discord Group DM la Tanière Orga 1461351991145140234",
        )

    def test_unnamed_group_dm_falls_back_to_other_participants(self) -> None:
        metadata = {
            "conversation_type": "group_dm",
            "participants": [
                {"id": "self", "name": "Gadget MCS", "is_self": True},
                {"id": "m", "name": "Miziix", "is_self": False},
                {"id": "x", "name": "Xylitol", "is_self": False},
                {"id": "c", "name": "M7Cryptic", "is_self": False},
            ],
            "current_user": {"id": "self", "display_name": "Gadget MCS"},
        }

        self.assertEqual(
            dm_artifact_stem(metadata, "123"),
            "Discord Group DM Miziix · Xylitol · M7Cryptic 123",
        )

    def test_duplicate_local_participant_does_not_make_group_dm(self) -> None:
        metadata = {
            "conversation_type": "dm",
            "current_user": {
                "id": "self",
                "display_name": "Gadget MCS",
                "username": "gadgetmcs",
            },
            "participants": [
                {"id": "self", "name": "Gadget MCS", "is_self": True},
                {"id": None, "name": "Gadget MCS", "username": "gadgetmcs", "is_self": None},
                {"id": "peer", "name": "Raphael", "is_self": False},
            ],
        }
        self.assertFalse(is_group_dm(metadata))

    def test_duplicate_peer_records_do_not_make_group_dm(self) -> None:
        metadata = {
            "conversation_type": "dm",
            "current_user": {"id": "self", "display_name": "Gadget MCS"},
            "participants": [
                {"id": "self", "name": "Gadget MCS", "is_self": True},
                {"id": "peer", "name": "Raphael", "is_self": False},
                {"id": None, "name": "Raphael", "is_self": None},
            ],
        }
        self.assertFalse(is_group_dm(metadata))


if __name__ == "__main__":
    unittest.main()
