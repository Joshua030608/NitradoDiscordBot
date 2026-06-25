from __future__ import annotations

import itertools
import socket
import struct
from dataclasses import dataclass


SERVERDATA_RESPONSE_VALUE = 0
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_AUTH = 3

MAX_PACKET_LENGTH = 4096
PACKET_HEADER = struct.Struct("<iii")


class RconError(RuntimeError):
    """Base class for RCON failures."""


class RconAuthenticationError(RconError):
    """Raised when the RCON server rejects the password."""


class RconProtocolError(RconError):
    """Raised when the RCON server sends malformed data."""


class RconTimeoutError(RconError):
    """Raised when the RCON server does not answer in time."""


@dataclass(frozen=True)
class RconPacket:
    request_id: int
    packet_type: int
    body: str


@dataclass(frozen=True)
class RconPlayer:
    index: int
    name: str
    steam_id: str | None = None


@dataclass(frozen=True)
class ListPlayersResult:
    raw: str
    players: list[RconPlayer]

    @property
    def is_empty(self) -> bool:
        return not self.players


class RconClient:
    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        timeout_seconds: float = 8.0,
        command_quiet_seconds: float = 1.0,
    ) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.timeout_seconds = timeout_seconds
        self.command_quiet_seconds = command_quiet_seconds
        self._socket: socket.socket | None = None
        self._ids = itertools.count(1000)

    def __enter__(self) -> RconClient:
        self.connect()
        self.authenticate()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def connect(self) -> None:
        if self._socket is not None:
            return
        try:
            self._socket = socket.create_connection(
                (self.host, self.port),
                timeout=self.timeout_seconds,
            )
            self._socket.settimeout(self.timeout_seconds)
        except TimeoutError as exc:
            raise RconTimeoutError(f"Timed out connecting to RCON at {self.host}:{self.port}") from exc
        except OSError as exc:
            raise RconError(f"Could not connect to RCON at {self.host}:{self.port}: {exc}") from exc

    def close(self) -> None:
        if self._socket is None:
            return
        try:
            self._socket.close()
        finally:
            self._socket = None

    def authenticate(self) -> None:
        auth_id = self._next_id()
        self._send_packet(RconPacket(auth_id, SERVERDATA_AUTH, self.password))

        for _ in range(4):
            packet = self._read_packet()
            if packet.request_id == -1:
                raise RconAuthenticationError("RCON authentication failed")
            if packet.request_id == auth_id and packet.packet_type == SERVERDATA_AUTH_RESPONSE:
                return

        raise RconProtocolError("RCON authentication response was not received")

    def command(self, command: str, allow_empty_response: bool = False) -> str:
        if not command.strip():
            raise ValueError("RCON command cannot be empty")

        sock = self._require_socket()
        previous_timeout = sock.gettimeout()
        command_id = self._next_id()
        chunks: list[str] = []

        try:
            sock.settimeout(self.timeout_seconds)
            self._send_packet(RconPacket(command_id, SERVERDATA_EXECCOMMAND, command))
            if allow_empty_response:
                sock.settimeout(min(self.command_quiet_seconds, self.timeout_seconds))

            while True:
                try:
                    packet = self._read_packet()
                except RconTimeoutError:
                    if chunks or allow_empty_response:
                        break
                    raise

                if packet.request_id == command_id:
                    chunks.append(packet.body)
                    sock.settimeout(min(self.command_quiet_seconds, self.timeout_seconds))
        finally:
            sock.settimeout(previous_timeout)

        return "".join(chunks).strip()

    def list_players(self) -> ListPlayersResult:
        raw = self.command("ListPlayers")
        return parse_list_players(raw)

    def save_world(self) -> str:
        return self.command("SaveWorld", allow_empty_response=True)

    def broadcast(self, message: str) -> str:
        clean_message = " ".join(message.split())
        if not clean_message:
            raise ValueError("Broadcast message cannot be empty")
        return self.command(f"Broadcast {clean_message}", allow_empty_response=True)

    def _next_id(self) -> int:
        return next(self._ids)

    def _send_packet(self, packet: RconPacket) -> None:
        sock = self._require_socket()
        body = packet.body.encode("utf-8")
        length = 4 + 4 + len(body) + 2
        payload = PACKET_HEADER.pack(length, packet.request_id, packet.packet_type)
        try:
            sock.sendall(payload + body + b"\x00\x00")
        except TimeoutError as exc:
            raise RconTimeoutError("Timed out sending RCON packet") from exc
        except OSError as exc:
            raise RconError(f"Failed to send RCON packet: {exc}") from exc

    def _read_packet(self) -> RconPacket:
        sock = self._require_socket()
        try:
            raw_length = _recv_exact(sock, 4)
            (length,) = struct.unpack("<i", raw_length)
            if length < 10 or length > MAX_PACKET_LENGTH:
                raise RconProtocolError(f"Invalid RCON packet length: {length}")

            payload = _recv_exact(sock, length)
            request_id, packet_type = struct.unpack("<ii", payload[:8])
            body_bytes = payload[8:-2]
            body = body_bytes.decode("utf-8", errors="replace")
            return RconPacket(request_id, packet_type, body)
        except socket.timeout as exc:
            raise RconTimeoutError("Timed out waiting for RCON response") from exc
        except OSError as exc:
            raise RconError(f"Failed to read RCON packet: {exc}") from exc

    def _require_socket(self) -> socket.socket:
        if self._socket is None:
            raise RconError("RCON client is not connected")
        return self._socket


def parse_list_players(raw: str) -> ListPlayersResult:
    players: list[RconPlayer] = []
    for line in raw.splitlines():
        clean = line.strip()
        if not clean:
            continue
        lowered = clean.casefold()
        if "no players" in lowered or "no one is connected" in lowered:
            continue

        parsed = _parse_player_line(clean)
        if parsed is not None:
            players.append(parsed)

    return ListPlayersResult(raw=raw, players=players)


def _parse_player_line(line: str) -> RconPlayer | None:
    prefix, separator, rest = line.partition(".")
    if not separator or not prefix.strip().isdigit():
        return None

    index = int(prefix.strip())
    name = rest.strip()
    steam_id: str | None = None

    if "," in name:
        parts = [part.strip() for part in name.split(",")]
        first = parts[0]
        last = parts[-1]
        if _looks_like_player_id(last):
            name = ", ".join(parts[:-1]).strip()
            steam_id = last
        elif _looks_like_player_id(first):
            name = ", ".join(parts[1:]).strip()
            steam_id = first

    if not name:
        return None
    return RconPlayer(index=index, name=name, steam_id=steam_id)


def _looks_like_player_id(value: str) -> bool:
    if len(value) < 15:
        return False
    return all(character.isalnum() for character in value)


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise RconProtocolError("RCON connection closed while reading packet")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
