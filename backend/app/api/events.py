from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services.sse import SSEBroker

router = APIRouter(prefix="/api/events", tags=["events"])


def attach_router(broker: SSEBroker) -> APIRouter:
    @router.get("/stream")
    async def stream_events(request: Request):
        async def event_generator():
            async for chunk in broker.stream():
                if await request.is_disconnected():
                    break
                yield chunk

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    return router
