from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


NITRADO_API_BASE_URL = "https://api.nitrado.net"


class NitradoError(RuntimeError):
    """Base class for Nitrado API failures."""


class NitradoApiError(NitradoError):
    """Raised when the Nitrado API returns an error response."""


@dataclass(frozen=True)
class NitradoService:
    id: int
    status: str
    type: str
    name: str | None = None
    game: str | None = None
    address: str | None = None
    slots: int | None = None
    folder_short: str | None = None


@dataclass(frozen=True)
class NitradoGameserver:
    service_id: int
    status: str
    game: str | None = None
    game_human: str | None = None
    ip: str | None = None
    port: int | None = None
    query_port: int | None = None
    rcon_port: int | None = None
    slots: int | None = None
    raw: dict[str, Any] | None = None

    @property
    def address(self) -> str | None:
        if self.ip and self.port:
            return f"{self.ip}:{self.port}"
        return self.ip


class NitradoClient:
    def __init__(
        self,
        api_token: str,
        service_id: int | None = None,
        timeout_seconds: float = 15.0,
        base_url: str = NITRADO_API_BASE_URL,
    ) -> None:
        self.api_token = api_token
        self.service_id = service_id
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")

    def list_services(self) -> list[NitradoService]:
        payload = self._request("GET", "/services")
        services = payload.get("data", {}).get("services", [])
        if not isinstance(services, list):
            raise NitradoApiError("Nitrado service list response was malformed")
        return [_parse_service(service) for service in services if isinstance(service, dict)]

    def get_gameserver(self, service_id: int | None = None) -> NitradoGameserver:
        service_id = self._service_id(service_id)
        payload = self._request("GET", f"/services/{service_id}/gameservers")
        gameserver = payload.get("data", {}).get("gameserver")
        if not isinstance(gameserver, dict):
            raise NitradoApiError("Nitrado gameserver response was malformed")
        return _parse_gameserver(gameserver, fallback_service_id=service_id)

    def restart(
        self,
        service_id: int | None = None,
        message: str | None = None,
        restart_message: str | None = None,
    ) -> str:
        service_id = self._service_id(service_id)
        data = _clean_form(
            {
                "message": message,
                "restart_message": restart_message,
            }
        )
        payload = self._request("POST", f"/services/{service_id}/gameservers/restart", data=data)
        return str(payload.get("message") or "Server will be restarted now.")

    def stop(
        self,
        service_id: int | None = None,
        message: str | None = None,
        stop_message: str | None = None,
    ) -> str:
        service_id = self._service_id(service_id)
        data = _clean_form(
            {
                "message": message,
                "stop_message": stop_message,
            }
        )
        payload = self._request("POST", f"/services/{service_id}/gameservers/stop", data=data)
        return str(payload.get("message") or "Server will be stopped now.")

    def start(self, service_id: int | None = None, game: str | None = None) -> str:
        service_id = self._service_id(service_id)
        game = game or self.get_gameserver(service_id).game
        if not game:
            raise NitradoApiError("Could not determine game short name for start command")

        payload = self._request(
            "POST",
            f"/services/{service_id}/gameservers/games/start",
            data={"game": game},
        )
        return str(payload.get("message") or "Game will be started now.")

    def stats(self, service_id: int | None = None, hours: int = 24) -> dict[str, Any]:
        service_id = self._service_id(service_id)
        payload = self._request(
            "GET",
            f"/services/{service_id}/gameservers/stats",
            params={"hours": str(hours)},
        )
        stats = payload.get("data", {}).get("stats", {})
        if not isinstance(stats, dict):
            raise NitradoApiError("Nitrado stats response was malformed")
        return stats

    def _service_id(self, service_id: int | None = None) -> int:
        chosen = service_id if service_id is not None else self.service_id
        if chosen is None:
            raise ValueError("Missing NITRADO_SERVICE_ID")
        return chosen

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self.api_token:
            raise ValueError("Missing NITRADO_API_TOKEN")

        url = self.base_url + "/" + path.lstrip("/")
        if params:
            url += "?" + urllib.parse.urlencode(params)

        body: bytes | None = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_token}",
            "User-Agent": "ArkLogBot/0.1",
        }
        if data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = _decode_response(response.read())
        except urllib.error.HTTPError as exc:
            payload = _decode_response(exc.read())
            message = _api_message(payload) if payload else exc.reason
            raise NitradoApiError(f"Nitrado API returned HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise NitradoApiError(f"Could not reach Nitrado API: {exc.reason}") from exc

        if payload.get("status") != "success":
            raise NitradoApiError(_api_message(payload))
        return payload


def _parse_service(value: dict[str, Any]) -> NitradoService:
    details = value.get("details", {})
    if not isinstance(details, dict):
        details = {}

    return NitradoService(
        id=int(value.get("id", 0)),
        status=str(value.get("status") or "unknown"),
        type=str(value.get("type") or "unknown"),
        name=_optional_string(details.get("name") or value.get("comment")),
        game=_optional_string(details.get("game")),
        address=_optional_string(details.get("address")),
        slots=_optional_int(details.get("slots") or details.get("game_slots")),
        folder_short=_optional_string(details.get("folder_short") or details.get("portlist_short")),
    )


def _parse_gameserver(value: dict[str, Any], fallback_service_id: int) -> NitradoGameserver:
    return NitradoGameserver(
        service_id=int(value.get("service_id") or fallback_service_id),
        status=str(value.get("status") or "unknown"),
        game=_optional_string(value.get("game")),
        game_human=_optional_string(value.get("game_human")),
        ip=_optional_string(value.get("ip")),
        port=_optional_int(value.get("port")),
        query_port=_optional_int(value.get("query_port")),
        rcon_port=_optional_int(value.get("rcon_port")),
        slots=_optional_int(value.get("slots")),
        raw=value,
    )


def _decode_response(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    decoded = raw.decode("utf-8", errors="replace")
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise NitradoApiError("Nitrado API returned non-JSON response") from exc
    if not isinstance(payload, dict):
        raise NitradoApiError("Nitrado API returned non-object response")
    return payload


def _api_message(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, str) and message:
        return message
    return "Nitrado API request failed"


def _clean_form(values: dict[str, str | None]) -> dict[str, str]:
    return {
        key: value.strip()
        for key, value in values.items()
        if value is not None and value.strip()
    }


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
