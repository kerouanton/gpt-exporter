import unittest

from gpt_exporter.providers.discord.naming import dm_artifact_stem, dm_peer, dm_title


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
        self.assertEqual(dm_title(metadata, "(101) Discord | @a33z"), "@a33z")
        self.assertEqual(
            dm_artifact_stem(metadata, "1467602455704371264"),
            "Discord DM gadgetmcs ↔ a33z 1467602455704371264",
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
        self.assertEqual(dm_title(metadata, "Discord | @TomZ"), "@TomZ")


if __name__ == "__main__":
    unittest.main()
