"""Client for the Night Check service."""

from __future__ import annotations

import base64
from typing import Any

import aiohttp

from .const import DEFAULT_API_BASE


class NightCheckError(Exception):
    """The service could not be reached or answered badly."""


class NightCheckAuthError(NightCheckError):
    """The key is not valid."""


class NightCheckInactive(NightCheckError):
    """The subscription is not active."""


class NightCheckApi:
    """Thin wrapper over the two calls Home Assistant needs."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str, base: str = DEFAULT_API_BASE) -> None:
        self._session = session
        self._key = api_key
        self._base = base.rstrip("/")

    async def _call(self, method: str, path: str, json: Any = None, timeout: float = 30) -> dict[str, Any]:
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                json=json,
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                try:
                    body = await resp.json(content_type=None)
                except ValueError:
                    body = {}
                if resp.status == 401:
                    raise NightCheckAuthError(body.get("message", "invalid key"))
                if resp.status == 402:
                    raise NightCheckInactive(body.get("message", "subscription not active"))
                if resp.status >= 400:
                    raise NightCheckError(body.get("message", f"HTTP {resp.status}"))
                return body
        except (aiohttp.ClientError, TimeoutError) as err:
            raise NightCheckError(f"could not reach Night Check: {err}") from err

    async def account(self) -> dict[str, Any]:
        """Status of this key's account."""
        return await self._call("GET", "/ha/v1/account", timeout=15)

    async def check(self, cameras: list[dict[str, Any]]) -> dict[str, Any]:
        """Send pictures; cameras = [{name, item, image: bytes | None, error: str | None}]."""
        payload = []
        for cam in cameras:
            row: dict[str, Any] = {"name": cam["name"], "item": cam["item"]}
            if cam.get("image"):
                row["image"] = base64.b64encode(cam["image"]).decode()
            else:
                row["error"] = cam.get("error") or "no picture"
            payload.append(row)
        return await self._call("POST", "/ha/v1/check", json={"cameras": payload}, timeout=120)
