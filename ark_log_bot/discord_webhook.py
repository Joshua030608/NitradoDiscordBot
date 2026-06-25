from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .parser import Event, display_time


DISCORD_LIMIT = 2000
MESSAGE_BUDGET = 1850
EVENT_LINE_LIMIT = 360


@dataclass
class DiscordWebhook:
    url: str
    mention_user_id: str | None = None
    timeout_seconds: int = 15

    def send_events(self, events: list[Event], timezone_name: str) -> None:
        for content in self._build_messages(events, timezone_name):
            self._post(content)

    def _build_messages(self, events: list[Event], timezone_name: str) -> list[str]:
        if not events:
            return []

        prefix = ""
        if self.mention_user_id:
            prefix = f"<@{self.mention_user_id}> "

        header = f"{prefix}**ARK server activity**"
        lines = [format_discord_event(event, timezone_name) for event in events]
        messages: list[str] = []
        current: list[str] = []
        current_length = len(header) + len("\n```text\n```")

        for line in lines:
            projected = current_length + len(line) + 1
            if current and projected > MESSAGE_BUDGET:
                messages.append(_wrap_code_block(header, current))
                current = []
                current_length = len(header) + len("\n```text\n```")
            current.append(line)
            current_length += len(line) + 1

        if current:
            messages.append(_wrap_code_block(header, current))

        return [message[:DISCORD_LIMIT] for message in messages]

    def _post(self, content: str) -> None:
        allowed_mentions = {"parse": []}
        if self.mention_user_id:
            allowed_mentions["users"] = [self.mention_user_id]

        payload = json.dumps(
            {"content": content, "allowed_mentions": allowed_mentions}
        ).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=payload,
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


def format_discord_event(event: Event, timezone_name: str) -> str:
    shown = display_time(event.timestamp, timezone_name)
    line = f"{shown:%I:%M:%S %p} [{event.category:<12}] {event.message}"
    if len(line) <= EVENT_LINE_LIMIT:
        return line
    return line[: EVENT_LINE_LIMIT - 3] + "..."


def _wrap_code_block(header: str, lines: list[str]) -> str:
    return f"{header}\n```text\n" + "\n".join(lines) + "\n```"
