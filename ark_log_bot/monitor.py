from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .discord_webhook import DiscordWebhook, format_discord_event
from .ftp_client import FtpLogClient
from .parser import Event, analyze_text, event_key
from .state import BotState


@dataclass
class MonitorOptions:
    local_log: Path | None = None
    no_discord: bool = False
    print_events: bool = False
    send_existing: bool | None = None


class ArkLogMonitor:
    def __init__(self, config: AppConfig, options: MonitorOptions) -> None:
        self.config = config
        self.options = options

    def run_forever(self) -> None:
        print(f"ARK log monitor started. Polling every {self.config.poll_seconds}s.")
        while True:
            try:
                sent_count = self.process_once()
                if sent_count:
                    print(f"Processed {sent_count} new event(s).")
            except Exception as exc:
                print(f"Monitor error: {exc}", file=sys.stderr)
            time.sleep(self.config.poll_seconds)

    def process_once(self) -> int:
        raw_log = self._download_log()
        report = analyze_text(
            raw_log.decode("utf-8-sig", errors="replace"),
            source=str(self.options.local_log or self.config.ftp_path or "ShooterGame.log"),
            include_saves=self.config.include_saves,
        )

        state = BotState.load(self.config.state_file)
        rotated = state.initialized and len(raw_log) < state.last_log_size
        if rotated:
            state.seen_event_keys = []

        seen = set(state.seen_event_keys)
        new_events = [event for event in report.events if event_key(event) not in seen]
        first_run = not state.initialized
        send_existing = (
            self.config.send_existing_on_first_run
            if self.options.send_existing is None
            else self.options.send_existing
        )

        if first_run and not send_existing:
            events_to_send: list[Event] = []
            if new_events:
                print(
                    "First run baseline saved. "
                    f"{len(new_events)} existing event(s) will not be sent."
                )
        else:
            events_to_send = new_events

        if events_to_send:
            self._emit_events(events_to_send)

        state.initialized = True
        state.last_log_size = len(raw_log)
        state.remember([event_key(event) for event in report.events], self.config.max_seen_events)
        state.save(self.config.state_file)
        return len(events_to_send)

    def _download_log(self) -> bytes:
        if self.options.local_log is not None:
            return self.options.local_log.read_bytes()

        missing = self.config.missing_ftp_fields()
        if missing:
            raise ValueError("Missing FTP configuration: " + ", ".join(missing))

        client = FtpLogClient(
            host=self.config.ftp_host or "",
            port=self.config.ftp_port,
            username=self.config.ftp_username or "",
            password=self.config.ftp_password or "",
            remote_path=self.config.ftp_path or "",
            use_tls=self.config.ftp_use_tls,
        )
        return client.download()

    def _emit_events(self, events: list[Event]) -> None:
        if self.options.print_events or self.options.no_discord:
            for event in events:
                print(format_discord_event(event, self.config.timezone_name))

        if self.options.no_discord:
            return

        if not self.config.discord_webhook_url:
            raise ValueError("Missing DISCORD_WEBHOOK_URL. Use --no-discord for dry runs.")

        webhook = DiscordWebhook(
            url=self.config.discord_webhook_url,
            mention_user_id=self.config.discord_user_id,
        )
        webhook.send_events(events, self.config.timezone_name)

