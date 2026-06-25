from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


TRUE_VALUES = {"1", "true", "yes", "on"}


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().casefold() in TRUE_VALUES


def parse_int(value: str | None, default: int) -> int:
    if value is None or not value.strip():
        return default
    return int(value)


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
    ftp_host: str | None
    ftp_port: int
    ftp_username: str | None
    ftp_password: str | None
    ftp_path: str | None
    ftp_use_tls: bool
    poll_seconds: int
    timezone_name: str
    state_file: Path
    send_existing_on_first_run: bool
    include_saves: bool
    max_seen_events: int

    @classmethod
    def from_env(cls) -> AppConfig:
        return cls(
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL"),
            discord_user_id=os.getenv("DISCORD_USER_ID"),
            ftp_host=os.getenv("FTP_HOST"),
            ftp_port=parse_int(os.getenv("FTP_PORT"), 21),
            ftp_username=os.getenv("FTP_USERNAME"),
            ftp_password=os.getenv("FTP_PASSWORD"),
            ftp_path=os.getenv("FTP_PATH"),
            ftp_use_tls=parse_bool(os.getenv("FTP_USE_TLS"), False),
            poll_seconds=parse_int(os.getenv("POLL_SECONDS"), 60),
            timezone_name=os.getenv("TIMEZONE", "local"),
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
