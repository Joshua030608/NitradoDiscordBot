from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ark_log_bot.alert_format import build_event_embed_dicts, build_event_message_content
from ark_log_bot.parser import Event


class AlertFormatTests(unittest.TestCase):
    def test_builds_ping_content_for_every_batch(self) -> None:
        events = [Event(datetime(2026, 6, 25, 12, tzinfo=timezone.utc), "JOIN", "LilGuppy joined")]

        content = build_event_message_content(events, "123456789012345678")

        self.assertEqual(content, "<@123456789012345678> **1 ARK timeline event**")

    def test_builds_embed_fields_and_chunks(self) -> None:
        events = [
            Event(datetime(2026, 6, 25, 12, minute, tzinfo=timezone.utc), "PLAYER DEATH", f"Death {minute}")
            for minute in range(11)
        ]

        embeds = build_event_embed_dicts(
            events,
            "recorded",
            server_name="Guppy's Collectibles Ragnarok",
        )

        self.assertEqual(len(embeds), 2)
        self.assertEqual(len(embeds[0]["fields"]), 10)
        self.assertEqual(len(embeds[1]["fields"]), 1)
        self.assertEqual(embeds[0]["color"], 0xD92D20)
        self.assertEqual(embeds[0]["footer"]["text"], "Guppy's Collectibles Ragnarok • ShooterGame.log")


if __name__ == "__main__":
    unittest.main()
