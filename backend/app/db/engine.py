from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar, cast

import aiofiles
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonCollection(Generic[T]):
    """File-backed JSON collection: { \"items\": [ ... ] }."""

    def __init__(self, path: Path, model: type[T]) -> None:
        self._path = path
        self._model = model
        self._async_lock = asyncio.Lock()

    async def _read_raw(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"items": []}
        async with aiofiles.open(self._path, mode="r", encoding="utf-8") as f:
            text = await f.read()
        if not text.strip():
            return {"items": []}
        data = json.loads(text)
        if "items" not in data:
            data = {"items": []}
        return data

    async def _write_raw(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        async with aiofiles.open(tmp, mode="w", encoding="utf-8") as f:
            await f.write(payload)
        tmp.replace(self._path)

    async def list_items(self, filter_fn: Callable[[T], bool] | None = None) -> list[T]:
        async with self._async_lock:
            raw = await self._read_raw()
        items: list[T] = []
        for row in raw.get("items", []):
            obj = self._model.model_validate(row)
            if filter_fn is None or filter_fn(obj):
                items.append(obj)
        return items

    async def get(self, item_id: str) -> T | None:
        async with self._async_lock:
            raw = await self._read_raw()
        for row in raw.get("items", []):
            if str(row.get("id")) == str(item_id):
                return self._model.model_validate(row)
        return None

    async def create(self, data: dict[str, Any] | T) -> T:
        if isinstance(data, BaseModel):
            payload = data.model_dump()
        else:
            payload = dict(data)
        if not payload.get("id"):
            payload["id"] = str(uuid.uuid4())
        now = _utc_now_iso()
        payload.setdefault("created_at", now)
        payload["updated_at"] = now
        obj = self._model.model_validate(payload)

        async with self._async_lock:
            raw = await self._read_raw()
            items = raw.setdefault("items", [])
            items.append(obj.model_dump(mode="json"))
            await self._write_raw(raw)
        return obj

    async def update(self, item_id: str, partial: dict[str, Any]) -> T | None:
        async with self._async_lock:
            raw = await self._read_raw()
            items = raw.setdefault("items", [])
            for i, row in enumerate(items):
                if str(row.get("id")) == str(item_id):
                    merged = {**row, **partial}
                    merged["updated_at"] = _utc_now_iso()
                    obj = self._model.model_validate(merged)
                    items[i] = obj.model_dump(mode="json")
                    await self._write_raw(raw)
                    return obj
        return None

    async def delete(self, item_id: str) -> bool:
        async with self._async_lock:
            raw = await self._read_raw()
            items = raw.setdefault("items", [])
            new_items = [r for r in items if str(r.get("id")) != str(item_id)]
            if len(new_items) == len(items):
                return False
            raw["items"] = new_items
            await self._write_raw(raw)
            return True


class DatabaseManager:
    """Caches one JsonCollection per store name so all callers share the same file lock."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._collections: dict[str, JsonCollection[Any]] = {}

    def collection(self, name: str, model: type[T]) -> JsonCollection[T]:
        if name not in self._collections:
            path = self.base_dir / f"{name}.json"
            self._collections[name] = JsonCollection(path, model)
        return cast(JsonCollection[T], self._collections[name])
