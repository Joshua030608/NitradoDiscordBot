from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ark_log_bot.config import AppConfig


class ConfigTests(unittest.TestCase):
    def test_parses_discord_bot_and_rcon_settings(self) -> None:
        env = {
            "DISCORD_USER_ID": "123456789012345678",
            "DISCORD_BOT_TOKEN": "token",
            "DISCORD_GUILD_ID": "111",
            "DISCORD_ALERT_CHANNEL_ID": "222",
            "DISCORD_ADMIN_USER_IDS": "123456789012345678,333",
            "RCON_HOST": "example.rcon",
            "RCON_PORT": "27020",
            "RCON_PASSWORD": "secret",
            "NITRADO_API_TOKEN": "nitrado-token",
            "NITRADO_SERVICE_ID": "123456",
            "SERVER_NAME": "Guppy's Collectibles Ragnarok",
        }

        with patch.dict(os.environ, env, clear=True):
            config = AppConfig.from_env()

        self.assertTrue(config.enable_discord_bot)
        self.assertEqual(config.discord_guild_id, 111)
        self.assertEqual(config.discord_alert_channel_id, 222)
        self.assertEqual(config.discord_admin_user_ids, {123456789012345678, 333})
        self.assertEqual(config.rcon_host, "example.rcon")
        self.assertEqual(config.rcon_port, 27020)
        self.assertEqual(config.rcon_password, "secret")
        self.assertEqual(config.nitrado_api_token, "nitrado-token")
        self.assertEqual(config.nitrado_service_id, 123456)
        self.assertEqual(config.server_name, "Guppy's Collectibles Ragnarok")

    def test_defaults_admins_to_pinged_user(self) -> None:
        with patch.dict(os.environ, {"DISCORD_USER_ID": "123456789012345678"}, clear=True):
            config = AppConfig.from_env()

        self.assertEqual(config.discord_admin_user_ids, {123456789012345678})

    def test_reports_missing_rcon_fields(self) -> None:
        with patch.dict(os.environ, {"RCON_HOST": "example.rcon"}, clear=True):
            config = AppConfig.from_env()

        self.assertEqual(config.missing_rcon_fields(), ["RCON_PORT", "RCON_PASSWORD"])

    def test_reports_missing_nitrado_fields(self) -> None:
        with patch.dict(os.environ, {"NITRADO_API_TOKEN": "token"}, clear=True):
            config = AppConfig.from_env()

        self.assertEqual(config.missing_nitrado_fields(), ["NITRADO_SERVICE_ID"])


if __name__ == "__main__":
    unittest.main()
