from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TRUE_VALUES = {"1", "true", "yes", "on"}


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().casefold() in TRUE_VALUES


def parse_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


def parse_optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return int(value)


def parse_int_set(value: str | None) -> set[int]:
    if value is None or not value.strip():
        return set()

    cleaned = value.replace(",", " ")
    return {int(part.strip()) for part in cleaned.split() if part.strip()}


def first_present(names: Iterable[str]) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass
class AppConfig:
    discord_webhook_url: str | None
    discord_user_id: str | None
    discord_bot_token: str | None
    discord_guild_id: int | None
    discord_alert_channel_id: int | None
    discord_admin_user_ids: set[int]
    enable_discord_bot: bool
    ftp_host: str | None
    ftp_port: int
    ftp_username: str | None
    ftp_password: str | None
    ftp_path: str | None
    ftp_use_tls: bool
    rcon_host: str | None
    rcon_port: int | None
    rcon_password: str | None
    rcon_timeout_seconds: float
    rcon_presence_poll_seconds: int
    rcon_presence_dedupe_seconds: int
    nitrado_api_token: str | None
    nitrado_service_id: int | None
    nitrado_timeout_seconds: float
    poll_seconds: int
    timezone_name: str
    server_name: str | None
    state_file: Path
    send_existing_on_first_run: bool
    include_saves: bool
    max_seen_events: int

    @classmethod
    def from_env(cls) -> AppConfig:
        discord_user_id = os.getenv("DISCORD_USER_ID")
        discord_bot_token = os.getenv("DISCORD_BOT_TOKEN")
        discord_alert_channel_id = parse_optional_int(os.getenv("DISCORD_ALERT_CHANNEL_ID"))
        discord_admin_user_ids = parse_int_set(os.getenv("DISCORD_ADMIN_USER_IDS"))
        if not discord_admin_user_ids and discord_user_id and discord_user_id.strip().isdigit():
            discord_admin_user_ids = {int(discord_user_id.strip())}

        return cls(
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL"),
            discord_user_id=discord_user_id,
            discord_bot_token=discord_bot_token,
            discord_guild_id=parse_optional_int(os.getenv("DISCORD_GUILD_ID")),
            discord_alert_channel_id=discord_alert_channel_id,
            discord_admin_user_ids=discord_admin_user_ids,
            enable_discord_bot=parse_bool(
                os.getenv("ENABLE_DISCORD_BOT"),
                bool(discord_bot_token and discord_alert_channel_id),
            ),
            ftp_host=os.getenv("FTP_HOST"),
            ftp_port=parse_int(os.getenv("FTP_PORT"), 21),
            ftp_username=os.getenv("FTP_USERNAME"),
            ftp_password=os.getenv("FTP_PASSWORD"),
            ftp_path=os.getenv("FTP_PATH"),
            ftp_use_tls=parse_bool(os.getenv("FTP_USE_TLS"), False),
            rcon_host=os.getenv("RCON_HOST"),
            rcon_port=parse_optional_int(os.getenv("RCON_PORT")),
            rcon_password=os.getenv("RCON_PASSWORD"),
            rcon_timeout_seconds=float(os.getenv("RCON_TIMEOUT_SECONDS", "8")),
            rcon_presence_poll_seconds=parse_int(os.getenv("RCON_PRESENCE_POLL_SECONDS"), 15),
            rcon_presence_dedupe_seconds=parse_int(
                os.getenv("RCON_PRESENCE_DEDUPE_SECONDS"),
                7200,
            ),
            nitrado_api_token=os.getenv("NITRADO_API_TOKEN"),
            nitrado_service_id=parse_optional_int(os.getenv("NITRADO_SERVICE_ID")),
            nitrado_timeout_seconds=float(os.getenv("NITRADO_TIMEOUT_SECONDS", "15")),
            poll_seconds=parse_int(os.getenv("POLL_SECONDS"), 60),
            timezone_name=os.getenv("TIMEZONE", "local"),
            server_name=first_present(("SERVER_NAME", "ARK_SERVER_NAME")),
            state_file=Path(os.getenv("STATE_FILE", ".ark-log-bot-state.json")),
            send_existing_on_first_run=parse_bool(
                os.getenv("SEND_EXISTING_ON_FIRST_RUN"), False
            ),
            include_saves=parse_bool(os.getenv("INCLUDE_SAVES"), False),
            max_seen_events=parse_int(os.getenv("MAX_SEEN_EVENTS"), 2000),
        )

    def missing_ftp_fields(self) -> list[str]:
        missing: list[str] = []
        for field_name, value in (
            ("FTP_HOST", self.ftp_host),
            ("FTP_USERNAME", self.ftp_username),
            ("FTP_PASSWORD", self.ftp_password),
            ("FTP_PATH", self.ftp_path),
        ):
            if not value:
                missing.append(field_name)
        return missing

    def missing_ftp_login_fields(self) -> list[str]:
        missing: list[str] = []
        for field_name, value in (
            ("FTP_HOST", self.ftp_host),
            ("FTP_USERNAME", self.ftp_username),
            ("FTP_PASSWORD", self.ftp_password),
        ):
            if not value:
                missing.append(field_name)
        return missing

    def missing_discord_bot_fields(self) -> list[str]:
        missing: list[str] = []
        for field_name, value in (
            ("DISCORD_BOT_TOKEN", self.discord_bot_token),
            ("DISCORD_ALERT_CHANNEL_ID", self.discord_alert_channel_id),
        ):
            if not value:
                missing.append(field_name)
        return missing

    def missing_rcon_fields(self) -> list[str]:
        missing: list[str] = []
        for field_name, value in (
            ("RCON_HOST", self.rcon_host),
            ("RCON_PORT", self.rcon_port),
            ("RCON_PASSWORD", self.rcon_password),
        ):
            if not value:
                missing.append(field_name)
        return missing

    def rcon_presence_enabled(self) -> bool:
        return self.rcon_presence_poll_seconds > 0 and not self.missing_rcon_fields()

    def missing_nitrado_fields(self) -> list[str]:
        missing: list[str] = []
        for field_name, value in (
            ("NITRADO_API_TOKEN", self.nitrado_api_token),
            ("NITRADO_SERVICE_ID", self.nitrado_service_id),
        ):
            if not value:
                missing.append(field_name)
        return missing
