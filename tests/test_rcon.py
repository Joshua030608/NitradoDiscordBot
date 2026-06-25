from __future__ import annotations

import socket
import struct
import threading
import unittest

from ark_log_bot.rcon import (
    PACKET_HEADER,
    SERVERDATA_AUTH,
    SERVERDATA_AUTH_RESPONSE,
    SERVERDATA_EXECCOMMAND,
    SERVERDATA_RESPONSE_VALUE,
    RconAuthenticationError,
    RconClient,
    RconPacket,
    parse_list_players,
)


class FakeRconServer:
    def __init__(self, password: str = "secret", answer_sentinel: bool = True) -> None:
        self.password = password
        self.answer_sentinel = answer_sentinel
        self.client_socket, self.server_socket = socket.socketpair()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._stopped = threading.Event()

    def __enter__(self) -> FakeRconServer:
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._stopped.set()
        for sock in (self.client_socket, self.server_socket):
            try:
                sock.close()
            except OSError:
                pass
        self._thread.join(timeout=2)

    def _serve(self) -> None:
        self._handle_connection(self.server_socket)

    def _handle_connection(self, conn: socket.socket) -> None:
        while not self._stopped.is_set():
            try:
                packet = _read_packet(conn)
            except OSError:
                return

            if packet.packet_type == SERVERDATA_AUTH:
                if packet.body == self.password:
                    _send_packet(conn, RconPacket(packet.request_id, SERVERDATA_RESPONSE_VALUE, ""))
                    _send_packet(conn, RconPacket(packet.request_id, SERVERDATA_AUTH_RESPONSE, ""))
                else:
                    _send_packet(conn, RconPacket(-1, SERVERDATA_AUTH_RESPONSE, ""))
                continue

            if (
                packet.packet_type == SERVERDATA_RESPONSE_VALUE
                and packet.body == ""
                and self.answer_sentinel
            ):
                _send_packet(conn, RconPacket(packet.request_id, SERVERDATA_RESPONSE_VALUE, ""))
                continue

            if packet.packet_type != SERVERDATA_EXECCOMMAND:
                continue

            if packet.body == "ListPlayers":
                _send_packet(conn, RconPacket(packet.request_id, SERVERDATA_RESPONSE_VALUE, "0. LilGuppy, "))
                _send_packet(conn, RconPacket(packet.request_id, SERVERDATA_RESPONSE_VALUE, "76561198000000000\n1. YasHFlasH1"))
            elif packet.body == "SaveWorld":
                _send_packet(conn, RconPacket(packet.request_id, SERVERDATA_RESPONSE_VALUE, "World Saved"))
            elif packet.body.startswith("Broadcast "):
                _send_packet(conn, RconPacket(packet.request_id, SERVERDATA_RESPONSE_VALUE, "Broadcast sent"))
            else:
                _send_packet(conn, RconPacket(packet.request_id, SERVERDATA_RESPONSE_VALUE, "Unknown command"))


class RconTests(unittest.TestCase):
    def test_executes_command_and_joins_split_response(self) -> None:
        with FakeRconServer() as server:
            with connected_client(server, "secret") as client:
                result = client.command("ListPlayers")

        self.assertEqual(result, "0. LilGuppy, 76561198000000000\n1. YasHFlasH1")

    def test_command_returns_after_quiet_period_when_server_ignores_sentinel(self) -> None:
        with FakeRconServer(answer_sentinel=False) as server:
            with connected_client(server, "secret", command_quiet_seconds=0.05) as client:
                result = client.command("ListPlayers")

        self.assertEqual(result, "0. LilGuppy, 76561198000000000\n1. YasHFlasH1")

    def test_parses_list_players(self) -> None:
        result = parse_list_players(
            "0. LilGuppy, 76561198000000000\n"
            "1. YasHFlasH1\n"
            "2. 76561198000000001, AnotherPlayer\n"
            "3. YasHFlasH1, 0002dfb3c8934ab880f70b167f1a2204\n"
            "Unparsed diagnostic line"
        )

        self.assertEqual(len(result.players), 4)
        self.assertEqual(result.players[0].name, "LilGuppy")
        self.assertEqual(result.players[0].steam_id, "76561198000000000")
        self.assertEqual(result.players[1].name, "YasHFlasH1")
        self.assertIsNone(result.players[1].steam_id)
        self.assertEqual(result.players[2].name, "AnotherPlayer")
        self.assertEqual(result.players[2].steam_id, "76561198000000001")
        self.assertEqual(result.players[3].name, "YasHFlasH1")
        self.assertEqual(result.players[3].steam_id, "0002dfb3c8934ab880f70b167f1a2204")

    def test_list_players_convenience(self) -> None:
        with FakeRconServer() as server:
            with connected_client(server, "secret") as client:
                result = client.list_players()

        self.assertEqual([player.name for player in result.players], ["LilGuppy", "YasHFlasH1"])

    def test_save_world(self) -> None:
        with FakeRconServer() as server:
            with connected_client(server, "secret") as client:
                result = client.save_world()

        self.assertEqual(result, "World Saved")

    def test_authentication_failure(self) -> None:
        with FakeRconServer() as server:
            with self.assertRaises(RconAuthenticationError):
                with connected_client(server, "wrong"):
                    pass


class connected_client:
    def __init__(
        self,
        server: FakeRconServer,
        password: str,
        command_quiet_seconds: float = 0.05,
    ) -> None:
        self.server = server
        self.client = RconClient(
            "socketpair",
            0,
            password,
            timeout_seconds=1,
            command_quiet_seconds=command_quiet_seconds,
        )

    def __enter__(self) -> RconClient:
        self.client._socket = self.server.client_socket
        self.client._socket.settimeout(self.client.timeout_seconds)
        self.client.authenticate()
        return self.client

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.client._socket = None


def _send_packet(conn: socket.socket, packet: RconPacket) -> None:
    body = packet.body.encode("utf-8")
    length = 4 + 4 + len(body) + 2
    conn.sendall(PACKET_HEADER.pack(length, packet.request_id, packet.packet_type) + body + b"\x00\x00")


def _read_packet(conn: socket.socket) -> RconPacket:
    raw_length = _recv_exact(conn, 4)
    (length,) = struct.unpack("<i", raw_length)
    payload = _recv_exact(conn, length)
    request_id, packet_type = struct.unpack("<ii", payload[:8])
    return RconPacket(
        request_id=request_id,
        packet_type=packet_type,
        body=payload[8:-2].decode("utf-8", errors="replace"),
    )


def _recv_exact(conn: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = conn.recv(remaining)
        if not chunk:
            raise OSError("closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


if __name__ == "__main__":
    unittest.main()
