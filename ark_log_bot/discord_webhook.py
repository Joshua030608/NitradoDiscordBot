from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .alert_format import EVENTS_PER_EMBED, build_event_embed_dicts, build_event_message_content
from .parser import Event, display_time


DISCORD_LIMIT = 2000
EVENT_LINE_LIMIT = 360
MAX_EMBEDS_PER_MESSAGE = 10
MAX_EVENTS_PER_MESSAGE = EVENTS_PER_EMBED * MAX_EMBEDS_PER_MESSAGE


@dataclass
class DiscordWebhook:
    url: str
    mention_user_id: str | None = None
    timeout_seconds: int = 15

    def send_events(
        self,
        events: list[Event],
        timezone_name: str,
        server_name: str | None = None,
        source_name: str = "ShooterGame.log",
    ) -> None:
        if not events:
            return

        for events_chunk in _chunks(events, MAX_EVENTS_PER_MESSAGE):
            embeds = build_event_embed_dicts(
                events_chunk,
                timezone_name,
                server_name=server_name,
                source_name=source_name,
            )
            payload = {
                "content": build_event_message_content(
                    events_chunk, self.mention_user_id
                )[:DISCORD_LIMIT],
                "embeds": embeds,
                "allowed_mentions": _allowed_mentions(self.mention_user_id),
            }
            self._post_payload(payload)

    def _post_payload(self, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ArkLogBot/0.1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status not in {200, 204}:
                    raise RuntimeError(f"Discord webhook returned HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Discord webhook returned HTTP {exc.code}: {body}") from exc


def _allowed_mentions(mention_user_id: str | None) -> dict:
    if mention_user_id:
        return {"users": [mention_user_id]}
    return {"parse": []}


def _chunks(items: list[Event], size: int) -> list[list[Event]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def format_discord_event(event: Event, timezone_name: str) -> str:
    shown = display_time(event.timestamp, timezone_name)
    line = f"{shown:%I:%M:%S %p} [{event.category:<12}] {event.message}"
    if len(line) <= EVENT_LINE_LIMIT:
        return line
    return line[: EVENT_LINE_LIMIT - 3] + "..."
