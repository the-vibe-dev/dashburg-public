from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator


class SSEBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict]] = set()

    def subscribe(self) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=200)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, message: dict) -> None:
        stale: list[asyncio.Queue[dict]] = []
        for q in self._subscribers:
            if q.full():
                stale.append(q)
                continue
            await q.put(message)
        for q in stale:
            self._subscribers.discard(q)

    async def stream(self) -> AsyncIterator[str]:
        queue = self.subscribe()
        try:
            yield "event: connected\ndata: {\"ok\": true}\n\n"
            while True:
                item = await queue.get()
                event_name = item.get("event", "message")
                payload = json.dumps(item.get("data", item), default=str)
                yield f"event: {event_name}\ndata: {payload}\n\n"
        finally:
            self.unsubscribe(queue)
