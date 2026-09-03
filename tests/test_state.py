from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ark_log_bot.state import BotState


class BotStateTests(unittest.TestCase):
    def test_load_ignores_malformed_state_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            state_path.write_text(
                '{"last_log_size": "not-a-number", "seen_event_keys": "bad"}',
                encoding="utf-8",
            )

            saved = BotState.load(state_path)

            self.assertEqual(saved.last_log_size, 0)
            self.assertEqual(saved.seen_event_keys, [])

    def test_monitor_update_preserves_presence_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            initial = BotState(
                presence_initialized=True,
                online_players={"steam123": "TestPlayer"},
                recent_presence_events={
                    "JOIN:testplayer": "2026-06-25T21:45:00+00:00",
                },
            )
            initial.save(state_path)

            update = BotState(
                initialized=True,
                last_log_size=1234,
                seen_event_keys=["event-a", "event-b"],
            )
            update.save_monitor_update(state_path)

            saved = BotState.load(state_path)

            self.assertTrue(saved.initialized)
            self.assertEqual(saved.last_log_size, 1234)
            self.assertEqual(saved.seen_event_keys, ["event-a", "event-b"])
            self.assertTrue(saved.presence_initialized)
            self.assertEqual(saved.online_players, {"steam123": "TestPlayer"})
            self.assertEqual(
                saved.recent_presence_events,
                {"JOIN:testplayer": "2026-06-25T21:45:00+00:00"},
            )

    def test_presence_update_preserves_monitor_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state_path = Path(temp) / "state.json"
            initial = BotState(
                initialized=True,
                last_log_size=5678,
                seen_event_keys=["event-a"],
            )
            initial.save(state_path)

            update = BotState(
                presence_initialized=True,
                online_players={"steam456": "SecondPlayer"},
            )
            update.remember_presence(
                ["LEAVE:secondplayer"],
                datetime(2026, 6, 25, 21, 45, tzinfo=timezone.utc),
            )
            update.save_presence_update(state_path)

            saved = BotState.load(state_path)

            self.assertTrue(saved.initialized)
            self.assertEqual(saved.last_log_size, 5678)
            self.assertEqual(saved.seen_event_keys, ["event-a"])
            self.assertTrue(saved.presence_initialized)
            self.assertEqual(saved.online_players, {"steam456": "SecondPlayer"})
            self.assertEqual(
                saved.recent_presence_events,
                {"LEAVE:secondplayer": "2026-06-25T21:45:00+00:00"},
            )


if __name__ == "__main__":
    unittest.main()
