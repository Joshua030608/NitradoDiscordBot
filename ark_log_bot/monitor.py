from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .discord_webhook import DiscordWebhook, format_discord_event
from .ftp_client import FtpLogClient
from .parser import Event, Report, analyze_text, event_key
from .state import BotState


@dataclass
class MonitorOptions:
    local_log: Path | None = None
    no_discord: bool = False
    print_events: bool = False
    send_existing: bool | None = None


@dataclass
class MonitorEvaluation:
    report: Report
    raw_log_size: int
    state: BotState
    events_to_send: list[Event]
    first_run: bool
    rotated: bool
    baseline_saved: bool


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
        evaluation = self.evaluate_once()
        if evaluation.events_to_send:
            self._emit_events(
                evaluation.events_to_send,
                server_name=evaluation.report.server_name,
                source_name=evaluation.report.source,
            )
        self.commit_evaluation(evaluation)
        return len(evaluation.events_to_send)

    def evaluate_once(self) -> MonitorEvaluation:
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
        if self.config.rcon_presence_enabled() and state.recent_presence_events:
            new_events = [
                event
                for event in new_events
                if not _is_rcon_presence_duplicate(
                    event,
                    state,
                    self.config.rcon_presence_dedupe_seconds,
                )
            ]
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

        return MonitorEvaluation(
            report=report,
            raw_log_size=len(raw_log),
            state=state,
            events_to_send=events_to_send,
            first_run=first_run,
            rotated=rotated,
            baseline_saved=first_run and not send_existing and bool(new_events),
        )

    def commit_evaluation(self, evaluation: MonitorEvaluation) -> None:
        state = evaluation.state
        state.initialized = True
        state.last_log_size = evaluation.raw_log_size
        state.remember(
            [event_key(event) for event in evaluation.report.events],
            self.config.max_seen_events,
        )
        state.save_monitor_update(self.config.state_file)

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

    def _emit_events(
        self,
        events: list[Event],
        server_name: str | None = None,
        source_name: str = "ShooterGame.log",
    ) -> None:
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
        webhook.send_events(
            events,
            self.config.timezone_name,
            server_name=self.config.server_name or server_name,
            source_name=Path(source_name).name,
        )


def _presence_dedupe_key(event: Event) -> str | None:
    category = event.category.upper()
    if category not in {"JOIN", "LEAVE"}:
        return None

    action = " joined " if category == "JOIN" else " left "
    if action not in event.message:
        return None

    player_name = event.message.split(action, 1)[0].strip()
    if not player_name:
        return None
    return f"{category}:{player_name.casefold()}"


def _is_rcon_presence_duplicate(
    event: Event,
    state: BotState,
    dedupe_seconds: int,
) -> bool:
    key = _presence_dedupe_key(event)
    if key is None or dedupe_seconds <= 0:
        return False

    seen_at = state.presence_seen_at(key)
    if seen_at is None:
        return False

    age_seconds = abs((event.timestamp - seen_at).total_seconds())
    return age_seconds <= dedupe_seconds
