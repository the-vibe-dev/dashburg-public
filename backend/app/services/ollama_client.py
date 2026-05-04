from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

import httpx


OllamaRequestType = Literal["chat", "generate", "embeddings", "pull", "tags", "version", "ps"]
OllamaStatus = Literal[
    "queued",
    "connecting",
    "loading_model",
    "generating",
    "streaming",
    "completed",
    "completed_with_warnings",
    "failed",
    "timed_out",
    "cancelled",
]


@dataclass
class OllamaEndpoint:
    endpoint_id: int | None
    label: str
    base_url: str
    api_key: str = ""


@dataclass
class OllamaEvent:
    event_type: str
    status: OllamaStatus
    ts_ms: int
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class OllamaTelemetry:
    request_type: OllamaRequestType
    status: OllamaStatus = "queued"
    endpoint_id: int | None = None
    endpoint_label: str = ""
    endpoint_url: str = ""
    fallback_endpoint_id: int | None = None
    fallback_endpoint_label: str = ""
    model: str = ""
    route: str = ""
    started_at_ms: int = 0
    first_token_at_ms: int | None = None
    completed_at_ms: int | None = None
    elapsed_ms: int = 0
    first_token_latency_ms: int | None = None
    stream_active: bool = False
    loading_detected: bool = False
    chunk_count: int = 0
    output_char_count: int = 0
    output_preview: str = ""
    output_text: str = ""
    finish_reason: str = ""
    total_duration_ns: int | None = None
    load_duration_ns: int | None = None
    prompt_eval_count: int | None = None
    prompt_eval_duration_ns: int | None = None
    eval_count: int | None = None
    eval_duration_ns: int | None = None
    tokens_per_second: float | None = None
    warning: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "request_type": self.request_type,
            "endpoint_id": self.endpoint_id,
            "endpoint_label": self.endpoint_label,
            "endpoint_url": self.endpoint_url,
            "fallback_endpoint_id": self.fallback_endpoint_id,
            "fallback_endpoint_label": self.fallback_endpoint_label,
            "model": self.model,
            "route": self.route,
            "started_at_ms": self.started_at_ms,
            "first_token_at_ms": self.first_token_at_ms,
            "completed_at_ms": self.completed_at_ms,
            "elapsed_ms": self.elapsed_ms,
            "first_token_latency_ms": self.first_token_latency_ms,
            "stream_active": self.stream_active,
            "loading_detected": self.loading_detected,
            "chunk_count": self.chunk_count,
            "output_char_count": self.output_char_count,
            "output_preview": self.output_preview,
            "finish_reason": self.finish_reason,
            "total_duration_ns": self.total_duration_ns,
            "load_duration_ns": self.load_duration_ns,
            "prompt_eval_count": self.prompt_eval_count,
            "prompt_eval_duration_ns": self.prompt_eval_duration_ns,
            "eval_count": self.eval_count,
            "eval_duration_ns": self.eval_duration_ns,
            "tokens_per_second": self.tokens_per_second,
            "warning": self.warning,
        }


class OllamaClient:
    def __init__(self, timeout_seconds: float = 120.0) -> None:
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _headers(endpoint: OllamaEndpoint) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if endpoint.api_key:
            headers["Authorization"] = f"Bearer {endpoint.api_key}"
        return headers

    @staticmethod
    def _url(endpoint: OllamaEndpoint, path: str) -> str:
        return f"{endpoint.base_url.rstrip('/')}{path}"

    def request_json(
        self,
        endpoint: OllamaEndpoint,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        body = payload if payload is not None else None
        with httpx.Client(timeout=timeout or self.timeout_seconds) as client:
            resp = client.request(
                method.upper(),
                self._url(endpoint, path),
                headers=self._headers(endpoint),
                json=body,
            )
            resp.raise_for_status()
            if not resp.text:
                return {}
            return resp.json()

    async def stream_json_lines(
        self,
        endpoint: OllamaEndpoint,
        path: str,
        *,
        payload: dict[str, Any],
        timeout: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=timeout or self.timeout_seconds) as client:
            async with client.stream(
                "POST",
                self._url(endpoint, path),
                headers=self._headers(endpoint),
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        obj = json.loads(text)
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        yield obj

    async def run_streaming_generation(
        self,
        *,
        endpoint: OllamaEndpoint,
        request_type: Literal["chat", "generate"],
        model: str,
        payload: dict[str, Any],
        route: str = "",
        timeout: float | None = None,
        on_event: Any | None = None,
        on_chunk: Any | None = None,
    ) -> OllamaTelemetry:
        started_ms = int(time.time() * 1000)
        now_ms = lambda: int(time.time() * 1000)
        telemetry = OllamaTelemetry(
            request_type=request_type,
            status="queued",
            endpoint_id=endpoint.endpoint_id,
            endpoint_label=endpoint.label,
            endpoint_url=endpoint.base_url,
            model=model,
            route=route,
            started_at_ms=started_ms,
        )

        async def emit(event_type: str, status: OllamaStatus, data: dict[str, Any] | None = None) -> None:
            telemetry.status = status
            telemetry.elapsed_ms = max(0, now_ms() - telemetry.started_at_ms)
            if on_event:
                evt = OllamaEvent(event_type=event_type, status=status, ts_ms=now_ms(), data=data or {})
                maybe = on_event(evt, telemetry)
                if asyncio.iscoroutine(maybe):
                    await maybe

        await emit("ollama_request_started", "queued")
        await emit("ollama_connected", "connecting")

        stream_payload = dict(payload)
        stream_payload["model"] = model
        stream_payload["stream"] = True
        path = "/api/chat" if request_type == "chat" else "/api/generate"

        try:
            async for chunk in self.stream_json_lines(endpoint, path, payload=stream_payload, timeout=timeout):
                if not telemetry.stream_active:
                    telemetry.stream_active = True
                    await emit("ollama_streaming", "streaming")

                done = bool(chunk.get("done"))
                status_hint = str(chunk.get("status", "")).strip().lower()
                if status_hint and "load" in status_hint:
                    telemetry.loading_detected = True
                    await emit("ollama_loading_model", "loading_model", {"status_hint": status_hint})

                if request_type == "chat":
                    message = chunk.get("message") if isinstance(chunk.get("message"), dict) else {}
                    text_piece = str(message.get("content", "") or "")
                else:
                    text_piece = str(chunk.get("response", "") or "")

                if text_piece:
                    if telemetry.first_token_at_ms is None:
                        telemetry.first_token_at_ms = now_ms()
                        telemetry.first_token_latency_ms = telemetry.first_token_at_ms - telemetry.started_at_ms
                        await emit("ollama_first_token", "generating", {"first_token_latency_ms": telemetry.first_token_latency_ms})
                    telemetry.chunk_count += 1
                    telemetry.output_text += text_piece
                    telemetry.output_char_count = len(telemetry.output_text)
                    telemetry.output_preview = telemetry.output_text[-240:]
                    await emit(
                        "ollama_stream_chunk",
                        "streaming",
                        {
                            "chunk_count": telemetry.chunk_count,
                            "output_char_count": telemetry.output_char_count,
                            "preview": telemetry.output_preview,
                        },
                    )
                    if on_chunk:
                        maybe = on_chunk(text_piece, telemetry)
                        if asyncio.iscoroutine(maybe):
                            await maybe

                if done:
                    telemetry.finish_reason = str(chunk.get("done_reason", "") or chunk.get("finish_reason", "") or "")
                    telemetry.total_duration_ns = _int_or_none(chunk.get("total_duration"))
                    telemetry.load_duration_ns = _int_or_none(chunk.get("load_duration"))
                    telemetry.prompt_eval_count = _int_or_none(chunk.get("prompt_eval_count"))
                    telemetry.prompt_eval_duration_ns = _int_or_none(chunk.get("prompt_eval_duration"))
                    telemetry.eval_count = _int_or_none(chunk.get("eval_count"))
                    telemetry.eval_duration_ns = _int_or_none(chunk.get("eval_duration"))
                    if telemetry.load_duration_ns and telemetry.load_duration_ns > 0:
                        telemetry.loading_detected = True
                    if telemetry.eval_count and telemetry.eval_duration_ns and telemetry.eval_duration_ns > 0:
                        telemetry.tokens_per_second = round(float(telemetry.eval_count) / (float(telemetry.eval_duration_ns) / 1_000_000_000.0), 3)

            telemetry.completed_at_ms = now_ms()
            telemetry.elapsed_ms = telemetry.completed_at_ms - telemetry.started_at_ms
            if telemetry.status not in {"failed", "timed_out", "cancelled"}:
                telemetry.status = "completed"
            await emit("ollama_request_completed", telemetry.status, telemetry.to_json())
            return telemetry
        except httpx.TimeoutException as exc:
            telemetry.completed_at_ms = now_ms()
            telemetry.elapsed_ms = telemetry.completed_at_ms - telemetry.started_at_ms
            telemetry.status = "timed_out"
            telemetry.warning = str(exc)
            await emit("ollama_request_failed", "timed_out", {"error": str(exc)})
            raise
        except asyncio.CancelledError:
            telemetry.completed_at_ms = now_ms()
            telemetry.elapsed_ms = telemetry.completed_at_ms - telemetry.started_at_ms
            telemetry.status = "cancelled"
            await emit("ollama_request_failed", "cancelled", {"error": "cancelled"})
            raise
        except Exception as exc:
            telemetry.completed_at_ms = now_ms()
            telemetry.elapsed_ms = telemetry.completed_at_ms - telemetry.started_at_ms
            telemetry.status = "failed"
            telemetry.warning = str(exc)
            await emit("ollama_request_failed", "failed", {"error": str(exc)})
            raise


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None
