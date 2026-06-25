from __future__ import annotations

import unittest

from ark_log_bot.parser import analyze_text


SAMPLE_LOG = """
[2026.06.25-07.36.06:195][  0]Log file open, 06/25/26 03:36:06
[2026.06.25-07.36.06:750][  0]ARK Version: 88.25
[2026.06.25-07.37.22:000][  0]Server: "Guppy's Collectibles Ragnarok" has successfully started!
[2026.06.25-07.37.22:100][  0]Steam Subsystem initialized: FAILED
[2026.06.25-07.37.45:000][  0]Server has completed startup and is now advertising for join (10.95GB Mem)
[2026.06.25-17.40.03:000][  0]LilGuppy [UniqueNetId:123 Platform:STEAM] joined this ARK!
[2026.06.25-17.46.46:000][  0]Tribe Tribe of Guppy, ID 123: Day 1, 12:00:00: Your Tribe Tamed a Juvenile Kentrosaurus - Lvl 24 (Kentrosaurus)!
[2026.06.25-17.47.23:000][  0]Tribe Tribe of Guppy, ID 123: Day 1, 12:00:00: Tribemember Guppy - Lvl 49 was killed by a Direwolf - Lvl 114!
""".strip()


class ParserTests(unittest.TestCase):
    def test_extracts_clean_timeline_events(self) -> None:
        report = analyze_text(SAMPLE_LOG)

        categories = [event.category for event in report.events]
        self.assertEqual(
            categories,
            ["STARTUP", "WARNING", "READY", "JOIN", "TAME", "PLAYER DEATH"],
        )

        messages = [event.message for event in report.events]
        self.assertIn('Server "Guppy\'s Collectibles Ragnarok" started', messages)
        self.assertIn("LilGuppy joined (STEAM)", messages)
        self.assertIn(
            "Guppy - Lvl 49 was killed by a Direwolf - Lvl 114! (Tribe: Tribe of Guppy)",
            messages,
        )

    def test_world_saves_are_optional(self) -> None:
        log = SAMPLE_LOG + "\n[2026.06.25-17.50.00:000][  0]World Save Complete. Took: 0.67"

        without_saves = analyze_text(log, include_saves=False)
        with_saves = analyze_text(log, include_saves=True)

        self.assertNotIn("SAVE", [event.category for event in without_saves.events])
        self.assertIn("SAVE", [event.category for event in with_saves.events])


if __name__ == "__main__":
    unittest.main()

