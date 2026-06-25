from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python 3.8 fallback only.
    ZoneInfo = None
    ZoneInfoNotFoundError = Exception


PREFIX_RE = re.compile(
    r"^\ufeff?\[(?P<stamp>\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3})\]"
    r"\[\s*\d+\](?P<message>.*)$"
)
EMBEDDED_STAMP_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}_\d{2}\.\d{2}\.\d{2}:\s*")
TRIBE_RE = re.compile(
    r"^Tribe (?P<tribe>.*?), ID \d+: Day \d+, \d{2}:\d{2}:\d{2}:\s*"
    r"(?P<event>.*?)(?:\)\s*)?$"
)
PLAYER_RE = re.compile(
    r"^(?P<name>.*?) \[UniqueNetId:(?P<id>\S+) Platform:(?P<platform>[^\]]+)\] "
    r"(?P<action>joined|left) this ARK!$",
    re.IGNORECASE,
)
RAW_DEATH_RE = re.compile(
    r"^(?P<character>.*?) \[(?P<account>.*?)\([^)]*\)\] from Tribe\[\d+\]"
    r'"(?P<tribe>.*?)" died\.$'
)
MOD_RE = re.compile(r"^LogCFCore: Mod valid: (?P<name>.+) \((?P<id>\d+)\)$")
MOD_VERSION_RE = re.compile(r"^\[(?P<name>.+)\] Server mod version: (?P<version>.+)$")
SAVE_RE = re.compile(r"World Save Complete\. Took:\s*(?P<seconds>[0-9.]+)", re.IGNORECASE)


@dataclass
class LogRecord:
    timestamp: datetime
    message: str


@dataclass
class Event:
    timestamp: datetime
    category: str
    message: str


@dataclass
class PlayerStats:
    name: str
    joins: int = 0
    leaves: int = 0
    connected_seconds: float = 0.0
    open_sessions: list[datetime] = field(default_factory=list)


@dataclass
class Report:
    source: str
    records: list[LogRecord]
    events: list[Event] = field(default_factory=list)
    issues: list[Event] = field(default_factory=list)
    counts: Counter[str] = field(default_factory=Counter)
    players: dict[str, PlayerStats] = field(default_factory=dict)
    mods: dict[str, str] = field(default_factory=dict)
    mod_versions: dict[str, str] = field(default_factory=dict)
    saves: list[float] = field(default_factory=list)
    server_name: str | None = None
    ark_version: str | None = None
    startup_seconds: float | None = None
    ready_memory: str | None = None
    core_count: int | None = None
    ready: bool = False


def parse_stamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y.%m.%d-%H.%M.%S:%f").replace(tzinfo=timezone.utc)


def parse_log_text(text: str) -> list[LogRecord]:
    records: list[LogRecord] = []
    current: LogRecord | None = None

    for line in text.splitlines():
        match = PREFIX_RE.match(line)
        if match:
            if current is not None:
                records.append(current)
            current = LogRecord(
                timestamp=parse_stamp(match.group("stamp")),
                message=match.group("message").strip(),
            )

    if current is not None:
        records.append(current)
    return records


def parse_log(path: Path) -> list[LogRecord]:
    return parse_log_text(path.read_text(encoding="utf-8-sig", errors="replace"))


def clean_text(message: str) -> str:
    message = EMBEDDED_STAMP_RE.sub("", message.strip())
    message = re.sub(r"<RichColor\b[^>]*>", "", message)
    message = message.replace("</>", "")
    message = re.sub(r"\s+", " ", message).strip()
    message = message.replace("()!", "!")
    if message.endswith("!)"):
        message = message[:-1]
    return message


def second(timestamp: datetime) -> datetime:
    return timestamp.replace(microsecond=0)


def issue_category(message: str) -> str | None:
    lowered = message.lower()
    if re.search(r"\b(fatal|error|exception|crash)\b", lowered):
        return "ERROR"
    if re.search(r"\b(failed|failure|warning)\b", lowered):
        return "WARNING"
    return None


def tribe_event(message: str) -> tuple[str, str] | None:
    match = TRIBE_RE.match(message)
    if not match:
        return None

    tribe = match.group("tribe")
    event = clean_text(match.group("event"))
    lowered = event.lower()

    if event.startswith("Tribemember "):
        event = event.removeprefix("Tribemember ")
        category = "PLAYER DEATH" if "killed" in lowered else "TRIBE"
        return category, f"{event} (Tribe: {tribe})"

    if event.startswith("Your Tribe Tamed "):
        detail = event.removeprefix("Your Tribe ")
        return "TAME", f"{tribe} {detail[0].lower() + detail[1:]}"

    if event.startswith("Your "):
        event = event.removeprefix("Your ")
        category = "TAME DEATH" if "killed" in lowered else "TRIBE"
        return category, f"{event} (Tribe: {tribe})"

    if " tamed " in lowered:
        return "TAME", f"{event} (Tribe: {tribe})"
    if "killed" in lowered:
        return "DEATH", f"{event} (Tribe: {tribe})"
    return "TRIBE", f"{event} (Tribe: {tribe})"


def generic_category(message: str) -> str:
    lowered = message.lower()
    issue = issue_category(message)
    if issue:
        return issue
    if " tamed " in lowered:
        return "TAME"
    if "killed" in lowered or lowered.endswith(" died."):
        return "DEATH"
    if "chat" in lowered:
        return "CHAT"
    if "admin" in lowered:
        return "ADMIN"
    if any(word in lowered for word in ("shutdown", "shutting down", "stopped", "restart")):
        return "SERVER"
    if any(word in lowered for word in ("demolished", "destroyed", "claimed", "unclaimed")):
        return "TRIBE"
    return "EVENT"


def add_event(report: Report, timestamp: datetime, category: str, message: str) -> None:
    event = Event(timestamp, category, message)
    report.events.append(event)
    report.counts[category] += 1
    if category in {"ERROR", "WARNING"}:
        report.issues.append(event)


def analyze_text(text: str, source: str = "ShooterGame.log", include_saves: bool = False) -> Report:
    records = parse_log_text(text)
    report = Report(source, records)
    tribe_seconds = {
        second(record.timestamp)
        for record in records
        if TRIBE_RE.match(clean_text(record.message))
    }
    ready_timestamp: datetime | None = None

    for record in records:
        message = clean_text(record.message)

        if not message or message.isdigit():
            continue

        if message.startswith("LogSentrySdk:"):
            continue

        if message.startswith("LogMemory:"):
            continue

        if message.startswith("LogCFCore: SetSettings called:") or message.startswith(
            "LogCFCore: InternalSettings called:"
        ):
            continue

        if message.startswith("LogCFCore: Detected OS"):
            continue

        if message.startswith("LogCFCore: No need to update existing mod:"):
            continue

        mod_match = MOD_RE.match(message)
        if mod_match:
            report.mods[mod_match.group("id")] = mod_match.group("name")
            continue

        mod_version = MOD_VERSION_RE.match(message)
        if mod_version:
            report.mod_versions[mod_version.group("name")] = mod_version.group("version")
            continue

        if message.startswith("UShooterEngine::LoadGameMods"):
            continue

        if message.startswith("Added Explorer Note Entry:"):
            continue

        if message.startswith("Initialize Primal Game Data") or message.startswith(
            "Primal Game Data Took"
        ):
            continue

        if message.startswith("Attempted GC & Defrag:") or message.startswith(
            "Garbage Collection Triggered!"
        ):
            continue

        if message.startswith("Difference Detected:"):
            continue

        if message.startswith("IP for incoming account"):
            continue

        if message.lower().endswith("saving world..."):
            continue

        save_match = SAVE_RE.search(message)
        if save_match:
            duration = float(save_match.group("seconds"))
            report.saves.append(duration)
            if include_saves:
                add_event(report, record.timestamp, "SAVE", f"World saved in {duration:.2f}s")
            continue

        if message.startswith("Log file open,"):
            continue

        if message.startswith("ARK Version:"):
            report.ark_version = message.partition(":")[2].strip()
            continue

        server_match = re.match(r'^Server: "(?P<name>.+)" has successfully started!$', message)
        if server_match:
            report.server_name = server_match.group("name")
            add_event(report, record.timestamp, "STARTUP", f'Server "{report.server_name}" started')
            continue

        if message.startswith("Full Startup:"):
            number = re.search(r"([0-9.]+)\s+seconds", message)
            if number:
                report.startup_seconds = float(number.group(1))
            continue

        if message.startswith("Number of cores "):
            number = re.search(r"(\d+)$", message)
            if number:
                report.core_count = int(number.group(1))
            continue

        if message.startswith("Server has completed startup and is now advertising for join"):
            memory = re.search(r"\(([^)]+) Mem\)", message)
            report.ready_memory = memory.group(1) if memory else None
            report.ready = True
            ready_timestamp = record.timestamp
            detail = "Server ready for players"
            if report.ready_memory:
                detail += f" ({report.ready_memory} memory)"
            add_event(report, record.timestamp, "READY", detail)
            continue

        if message.startswith("Initializing Steam Subsystem") or message.startswith("Server Region is"):
            continue

        player_match = PLAYER_RE.match(message)
        if player_match:
            player_id = player_match.group("id")
            name = player_match.group("name")
            platform = player_match.group("platform")
            action = player_match.group("action").lower()
            stats = report.players.setdefault(player_id, PlayerStats(name=name))
            stats.name = name

            if action == "joined":
                stats.joins += 1
                stats.open_sessions.append(record.timestamp)
                category = "JOIN"
            else:
                stats.leaves += 1
                if stats.open_sessions:
                    joined_at = stats.open_sessions.pop()
                    stats.connected_seconds += (record.timestamp - joined_at).total_seconds()
                category = "LEAVE"
            add_event(report, record.timestamp, category, f"{name} {action} ({platform})")
            continue

        parsed_tribe_event = tribe_event(message)
        if parsed_tribe_event:
            category, detail = parsed_tribe_event
            add_event(report, record.timestamp, category, detail)
            continue

        raw_death = RAW_DEATH_RE.match(message)
        if raw_death:
            if second(record.timestamp) not in tribe_seconds:
                detail = f"{raw_death.group('character')} died (Tribe: {raw_death.group('tribe')})"
                add_event(report, record.timestamp, "PLAYER DEATH", detail)
            continue

        if second(record.timestamp) in tribe_seconds and (
            "killed" in message.lower() or " tamed " in message.lower()
        ):
            continue

        issue = issue_category(message)
        if issue:
            add_event(report, record.timestamp, issue, message)
            continue

        if ready_timestamp is None or record.timestamp < ready_timestamp:
            continue
        add_event(report, record.timestamp, generic_category(message), message)

    report.events.sort(key=lambda event: event.timestamp)
    report.issues.sort(key=lambda event: event.timestamp)
    return report


def analyze(path: Path, include_saves: bool = False) -> Report:
    return analyze_text(
        path.read_text(encoding="utf-8-sig", errors="replace"),
        source=str(path),
        include_saves=include_saves,
    )


def timezone_converter(name: str):
    if name == "recorded":
        return timezone.utc
    if name == "local":
        return None
    if ZoneInfo is None:
        raise ValueError("Named time zones require Python 3.9 or newer")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown time zone: {name}") from exc


def display_time(value: datetime, timezone_name: str) -> datetime:
    target_tz = timezone_converter(timezone_name)
    return value.astimezone() if target_tz is None else value.astimezone(target_tz)


def format_event(event: Event, timezone_name: str) -> str:
    shown = display_time(event.timestamp, timezone_name)
    return f"{shown:%I:%M:%S %p}  [{event.category:<12}] {event.message}"


def event_key(event: Event) -> str:
    timestamp = event.timestamp.isoformat(timespec="milliseconds")
    return f"{timestamp}|{event.category}|{event.message}"


def event_keys(events: Iterable[Event]) -> list[str]:
    return [event_key(event) for event in events]

