from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BotState:
    initialized: bool = False
    last_log_size: int = 0
    seen_event_keys: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> BotState:
        if not path.is_file():
            return cls()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()

        return cls(
            initialized=bool(data.get("initialized", False)),
            last_log_size=int(data.get("last_log_size", 0)),
            seen_event_keys=_string_list(data.get("seen_event_keys", [])),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "initialized": self.initialized,
            "last_log_size": self.last_log_size,
            "seen_event_keys": self.seen_event_keys,
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def remember(self, keys: list[str], max_seen: int) -> None:
        ordered = list(dict.fromkeys([*self.seen_event_keys, *keys]))
        self.seen_event_keys = ordered[-max_seen:]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]

