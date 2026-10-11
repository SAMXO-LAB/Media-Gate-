"""Small TTL cache for analyze results (limits paid API reads, e.g. X pay-per-use)."""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    def __init__(self, ttl: float = 600, max_items: int = 2000) -> None:
        self.ttl = ttl
        self.max_items = max_items
        self._data: OrderedDict[Any, tuple[float, Any]] = OrderedDict()

    def get(self, key: Any) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        exp, value = item
        if exp < time.monotonic():
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: Any, value: Any) -> None:
        self._data[key] = (time.monotonic() + self.ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self.max_items:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()


resolve_cache = TTLCache()
