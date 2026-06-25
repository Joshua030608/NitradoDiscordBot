from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class BotState:
    initialized: bool = False
    last_log_size: int = 0
    seen_event_keys: list[str] = field(default_factory=list)
    presence_initialized: bool = False
    online_players: dict[str, str] = field(default_factory=dict)
    recent_presence_events: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> BotState:
        if not path.is_file():
            return cls()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(data, dict):
            return cls()

        return cls(
            initialized=bool(data.get("initialized", False)),
            last_log_size=_safe_int(data.get("last_log_size", 0)),
            seen_event_keys=_string_list(data.get("seen_event_keys", [])),
            presence_initialized=bool(data.get("presence_initialized", False)),
            online_players=_string_dict(data.get("online_players", {})),
            recent_presence_events=_string_dict(data.get("recent_presence_events", {})),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "initialized": self.initialized,
            "last_log_size": self.last_log_size,
            "seen_event_keys": self.seen_event_keys,
            "presence_initialized": self.presence_initialized,
            "online_players": self.online_players,
            "recent_presence_events": self.recent_presence_events,
        }
        temp_path = path.with_name(f"{path.name}.tmp")
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(path)

    def save_monitor_update(self, path: Path) -> None:
        latest = type(self).load(path)
        latest.initialized = self.initialized
        latest.last_log_size = self.last_log_size
        latest.seen_event_keys = self.seen_event_keys
        latest.save(path)

    def save_presence_update(self, path: Path) -> None:
        latest = type(self).load(path)
        latest.presence_initialized = self.presence_initialized
        latest.online_players = self.online_players
        latest.recent_presence_events = {
            **latest.recent_presence_events,
            **self.recent_presence_events,
        }
        latest.save(path)

    def remember(self, keys: list[str], max_seen: int) -> None:
        ordered = list(dict.fromkeys([*self.seen_event_keys, *keys]))
        self.seen_event_keys = ordered[-max_seen:]

    def remember_presence(
        self,
        keys: list[str],
        seen_at: datetime,
        max_seen: int = 200,
    ) -> None:
        timestamp = seen_at.isoformat()
        for key in keys:
            self.recent_presence_events[key] = timestamp
        self.recent_presence_events = dict(
            sorted(
                self.recent_presence_events.items(),
                key=lambda item: item[1],
            )[-max_seen:]
        )

    def presence_seen_at(self, key: str) -> datetime | None:
        raw_value = self.recent_presence_events.get(key)
        if not raw_value:
            return None
        try:
            return datetime.fromisoformat(raw_value)
        except ValueError:
            return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
