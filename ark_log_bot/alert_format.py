from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from .parser import Event, display_time


FIELD_NAME_LIMIT = 256
FIELD_VALUE_LIMIT = 1024
EVENTS_PER_EMBED = 10

COLORS = {
    "ERROR": 0xD92D20,
    "WARNING": 0xF79009,
    "PLAYER DEATH": 0xD92D20,
    "TAME DEATH": 0xD92D20,
    "DEATH": 0xD92D20,
    "TAME": 0x12B76A,
    "JOIN": 0x2E90FA,
    "LEAVE": 0x667085,
    "READY": 0x12B76A,
    "STARTUP": 0x667085,
    "SAVE": 0x7A5AF8,
    "ADMIN": 0x7A5AF8,
    "CHAT": 0x2E90FA,
    "SERVER": 0x667085,
    "TRIBE": 0xF79009,
    "TEST": 0x2E90FA,
}
DEFAULT_COLOR = 0x475467

SEVERITY = {
    "ERROR": 100,
    "WARNING": 90,
    "PLAYER DEATH": 80,
    "TAME DEATH": 80,
    "DEATH": 70,
    "ADMIN": 60,
    "SERVER": 50,
    "JOIN": 40,
    "LEAVE": 40,
    "TAME": 35,
    "READY": 30,
    "STARTUP": 30,
    "SAVE": 20,
    "CHAT": 10,
    "TRIBE": 10,
    "TEST": 0,
}


def build_event_embed_dicts(
    events: list[Event],
    timezone_name: str,
    server_name: str | None = None,
    source_name: str = "ShooterGame.log",
) -> list[dict]:
    embeds: list[dict] = []
    total = len(events)

    for index, chunk in enumerate(_chunks(events, EVENTS_PER_EMBED), start=1):
        title = "ARK server activity"
        if total > EVENTS_PER_EMBED:
            title += f" ({index}/{_chunk_count(total, EVENTS_PER_EMBED)})"

        embed = {
            "title": title,
            "description": f"{len(chunk)} new timeline event(s)",
            "color": _chunk_color(chunk),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fields": [
                {
                    "name": _truncate(_field_name(event, timezone_name), FIELD_NAME_LIMIT),
                    "value": _truncate(event.message or "(no detail)", FIELD_VALUE_LIMIT),
                    "inline": False,
                }
                for event in chunk
            ],
            "footer": {"text": _footer_text(server_name, source_name)},
        }
        embeds.append(embed)

    return embeds


def build_event_message_content(
    events: list[Event],
    mention_user_id: str | None,
) -> str:
    prefix = f"<@{mention_user_id}> " if mention_user_id else ""
    count = len(events)
    noun = "event" if count == 1 else "events"
    return f"{prefix}**{count} ARK timeline {noun}**"


def category_color(category: str) -> int:
    return COLORS.get(category.upper(), DEFAULT_COLOR)


def _field_name(event: Event, timezone_name: str) -> str:
    shown = display_time(event.timestamp, timezone_name)
    return f"{shown:%I:%M:%S %p} • {event.category}"


def _chunk_color(events: Iterable[Event]) -> int:
    top_category = max(
        (event.category for event in events),
        key=lambda category: SEVERITY.get(category.upper(), -1),
        default="EVENT",
    )
    return category_color(top_category)


def _footer_text(server_name: str | None, source_name: str) -> str:
    if server_name:
        return f"{server_name} • {source_name}"
    return source_name


def _chunks(items: list[Event], size: int) -> Iterable[list[Event]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _chunk_count(total: int, size: int) -> int:
    return (total + size - 1) // size


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
