from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from ark_log_bot.nitrado import NitradoApiError, NitradoClient


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        pass

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class UrlOpenQueue:
    def __init__(self, *payloads: dict) -> None:
        self.payloads = list(payloads)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if not self.payloads:
            raise AssertionError("No fake Nitrado response queued")
        return FakeResponse(self.payloads.pop(0))


class NitradoClientTests(unittest.TestCase):
    def test_lists_services(self) -> None:
        fake = UrlOpenQueue(
            {
                "status": "success",
                "data": {
                    "services": [
                        {
                            "id": 123,
                            "status": "active",
                            "type": "gameserver",
                            "details": {
                                "name": "Example ARK Server",
                                "game": "ARK: Survival Ascended",
                                "address": "31.214.239.80:7777",
                                "slots": 20,
                                "folder_short": "arksa",
                            },
                        }
                    ]
                },
            }
        )

        with patch("urllib.request.urlopen", fake):
            services = NitradoClient("token").list_services()

        self.assertEqual(services[0].id, 123)
        self.assertEqual(services[0].folder_short, "arksa")
        request, timeout = fake.requests[0]
        self.assertEqual(request.full_url, "https://api.nitrado.net/services")
        self.assertEqual(request.get_header("Authorization"), "Bearer token")
        self.assertEqual(timeout, 15.0)

    def test_gets_gameserver_status(self) -> None:
        fake = UrlOpenQueue(
            {
                "status": "success",
                "data": {
                    "gameserver": {
                        "service_id": 123,
                        "status": "started",
                        "game": "arksa",
                        "game_human": "ARK: Survival Ascended",
                        "ip": "31.214.239.80",
                        "port": 7777,
                        "query_port": 27015,
                        "rcon_port": 11660,
                        "slots": 20,
                    }
                },
            }
        )

        with patch("urllib.request.urlopen", fake):
            gameserver = NitradoClient("token", service_id=123).get_gameserver()

        self.assertEqual(gameserver.status, "started")
        self.assertEqual(gameserver.address, "31.214.239.80:7777")
        self.assertEqual(gameserver.rcon_port, 11660)

    def test_restart_posts_form_body(self) -> None:
        fake = UrlOpenQueue({"status": "success", "message": "Server will be restarted now."})

        with patch("urllib.request.urlopen", fake):
            response = NitradoClient("token", service_id=123).restart(
                message="Discord restart",
                restart_message="Discord restart",
            )

        self.assertEqual(response, "Server will be restarted now.")
        request, _ = fake.requests[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            request.full_url,
            "https://api.nitrado.net/services/123/gameservers/restart",
        )
        self.assertEqual(
            request.data.decode("utf-8"),
            "message=Discord+restart&restart_message=Discord+restart",
        )

    def test_start_uses_gameserver_game_short_name(self) -> None:
        fake = UrlOpenQueue(
            {
                "status": "success",
                "data": {"gameserver": {"service_id": 123, "status": "stopped", "game": "arksa"}},
            },
            {"status": "success", "message": "Game will be started now."},
        )

        with patch("urllib.request.urlopen", fake):
            response = NitradoClient("token", service_id=123).start()

        self.assertEqual(response, "Game will be started now.")
        start_request, _ = fake.requests[1]
        self.assertEqual(
            start_request.full_url,
            "https://api.nitrado.net/services/123/gameservers/games/start",
        )
        self.assertEqual(start_request.data.decode("utf-8"), "game=arksa")

    def test_api_failure_raises(self) -> None:
        fake = UrlOpenQueue({"status": "error", "message": "No permission"})

        with patch("urllib.request.urlopen", fake):
            with self.assertRaises(NitradoApiError):
                NitradoClient("token").list_services()


if __name__ == "__main__":
    unittest.main()
