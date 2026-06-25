from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ark_log_bot.config import AppConfig
from ark_log_bot.monitor import ArkLogMonitor, MonitorOptions


STARTUP_LOG = """
[2026.06.25-07.37.22:000][  0]Server: "Guppy's Collectibles Ragnarok" has successfully started!
[2026.06.25-17.40.03:000][  0]LilGuppy [UniqueNetId:123 Platform:STEAM] joined this ARK!
""".strip()

EXTENDED_LOG = (
    STARTUP_LOG
    + "\n[2026.06.25-17.47.23:000][  0]Tribe Tribe of Guppy, ID 123: Day 1, "
    "12:00:00: Tribemember Guppy - Lvl 49 was killed by a Direwolf - Lvl 114!"
)

LEAVE_LOG = (
    STARTUP_LOG
    + "\n[2026.06.25-21.14.08:000][  0]YasHFlasH1 "
    "[UniqueNetId:abc Platform:STEAM] left this ARK!"
)


class MonitorTests(unittest.TestCase):
    def test_first_run_baselines_then_sends_only_new_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            log_path = temp_path / "ShooterGame.log"
            state_path = temp_path / "state.json"
            log_path.write_text(STARTUP_LOG, encoding="utf-8")

            monitor = ArkLogMonitor(
                _config(state_path),
                MonitorOptions(local_log=log_path, no_discord=True),
            )

            first = monitor.evaluate_once()
            self.assertEqual(first.events_to_send, [])
            self.assertTrue(first.baseline_saved)
            monitor.commit_evaluation(first)

            log_path.write_text(EXTENDED_LOG, encoding="utf-8")
            second = monitor.evaluate_once()

            self.assertEqual(len(second.events_to_send), 1)
            self.assertEqual(second.events_to_send[0].category, "PLAYER DEATH")

    def test_send_existing_overrides_first_run_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            log_path = temp_path / "ShooterGame.log"
            state_path = temp_path / "state.json"
            log_path.write_text(STARTUP_LOG, encoding="utf-8")

            monitor = ArkLogMonitor(
                _config(state_path),
                MonitorOptions(local_log=log_path, no_discord=True, send_existing=True),
            )

            evaluation = monitor.evaluate_once()

            self.assertEqual(len(evaluation.events_to_send), 2)
            self.assertFalse(evaluation.baseline_saved)

    def test_suppresses_delayed_log_presence_event_after_rcon_presence_alert(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            log_path = temp_path / "ShooterGame.log"
            state_path = temp_path / "state.json"
            log_path.write_text(LEAVE_LOG, encoding="utf-8")
            config = _config(state_path)
            config.rcon_host = "127.0.0.1"
            config.rcon_port = 27020
            config.rcon_password = "secret"

            monitor = ArkLogMonitor(
                config,
                MonitorOptions(local_log=log_path, no_discord=True, send_existing=True),
            )
            state = config.state_file
            state.write_text(
                (
                    '{"initialized": true, "last_log_size": 0, '
                    '"seen_event_keys": [], '
                    '"recent_presence_events": {'
                    '"LEAVE:yashflash1": "2026-06-25T21:45:00+00:00"'
                    "}}"
                ),
                encoding="utf-8",
            )

            evaluation = monitor.evaluate_once()

            self.assertEqual(
                [event.category for event in evaluation.events_to_send],
                ["STARTUP", "JOIN"],
            )

    def test_presence_dedupe_expires_for_future_log_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            log_path = temp_path / "ShooterGame.log"
            state_path = temp_path / "state.json"
            log_path.write_text(LEAVE_LOG, encoding="utf-8")
            config = _config(state_path)
            config.rcon_host = "127.0.0.1"
            config.rcon_port = 27020
            config.rcon_password = "secret"
            config.rcon_presence_dedupe_seconds = 60

            monitor = ArkLogMonitor(
                config,
                MonitorOptions(local_log=log_path, no_discord=True, send_existing=True),
            )
            state_path.write_text(
                (
                    '{"initialized": true, "last_log_size": 0, '
                    '"seen_event_keys": [], '
                    '"recent_presence_events": {'
                    '"LEAVE:yashflash1": "2026-06-25T21:45:00+00:00"'
                    "}}"
                ),
                encoding="utf-8",
            )

            evaluation = monitor.evaluate_once()

            self.assertEqual(
                [event.category for event in evaluation.events_to_send],
                ["STARTUP", "JOIN", "LEAVE"],
            )


def _config(state_file: Path) -> AppConfig:
    return AppConfig(
        discord_webhook_url=None,
        discord_user_id="123456789012345678",
        discord_bot_token=None,
        discord_guild_id=None,
        discord_alert_channel_id=None,
        discord_admin_user_ids={123456789012345678},
        enable_discord_bot=False,
        ftp_host=None,
        ftp_port=21,
        ftp_username=None,
        ftp_password=None,
        ftp_path=None,
        ftp_use_tls=False,
        rcon_host=None,
        rcon_port=None,
        rcon_password=None,
        rcon_timeout_seconds=8,
        rcon_presence_poll_seconds=15,
        rcon_presence_dedupe_seconds=7200,
        nitrado_api_token=None,
        nitrado_service_id=None,
        nitrado_timeout_seconds=15,
        poll_seconds=60,
        timezone_name="recorded",
        server_name=None,
        state_file=state_file,
        send_existing_on_first_run=False,
        include_saves=False,
        max_seen_events=2000,
    )


if __name__ == "__main__":
    unittest.main()
