"""HTTP client for new-api admin API."""

from __future__ import annotations

from typing import Any

import httpx


class NewApiClient:
    def __init__(self, base_url: str, admin_token: str, admin_user_id: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_token = admin_token.strip()
        self.admin_user_id = str(admin_user_id).strip()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.admin_token,
            "New-Api-User": self.admin_user_id,
            "Content-Type": "application/json",
        }

    def _check_api_success(self, data: dict[str, Any], raw_text: str) -> None:
        if data.get("success") is False:
            raise RuntimeError(str(data.get("message") or raw_text))

    async def list_channels(self, page: int = 1, page_size: int = 100) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(
                f"{self.base_url}/api/channel/",
                params={"p": page, "page_size": page_size},
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def search_channels(self, keyword: str, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(
                f"{self.base_url}/api/channel/search",
                params={"keyword": keyword, "p": page, "page_size": page_size},
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def get_channel(self, channel_id: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(
                f"{self.base_url}/api/channel/{channel_id}",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def create_channel(self, body: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{self.base_url}/api/channel/",
                json=body,
                headers=self._headers(),
            )
            text = r.text
            if r.status_code >= 400:
                raise RuntimeError(text)
            data = r.json() if text else {}
            if isinstance(data, dict):
                self._check_api_success(data, text)
            return data

    async def update_channel(self, body: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.put(
                f"{self.base_url}/api/channel/",
                json=body,
                headers=self._headers(),
            )
            text = r.text
            if r.status_code >= 400:
                raise RuntimeError(text)
            data = r.json() if text else {}
            if isinstance(data, dict):
                self._check_api_success(data, text)
            return data

    async def delete_channel(self, channel_id: int) -> None:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.delete(
                f"{self.base_url}/api/channel/{channel_id}",
                headers=self._headers(),
            )
            text = r.text
            if r.status_code >= 400 and r.status_code != 404:
                raise RuntimeError(text)
            if text:
                try:
                    data = r.json()
                    if isinstance(data, dict):
                        self._check_api_success(data, text)
                except Exception:
                    pass
