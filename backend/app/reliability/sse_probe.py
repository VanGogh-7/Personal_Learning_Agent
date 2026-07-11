from __future__ import annotations

import codecs
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(frozen=True)
class TimedSSEEvent:
    event: str
    sequence: int
    elapsed_ms: float
    network_chunk: int
    stage: str | None = None


@dataclass
class SSEDeliveryReport:
    base_url: str
    route: str
    status_code: int | None = None
    content_type: str | None = None
    cache_control: str | None = None
    accel_buffering: str | None = None
    events: list[TimedSSEEvent] = field(default_factory=list)
    network_chunk_count: int = 0
    heartbeat_count: int = 0
    cancelled_by_client: bool = False
    error: str | None = None

    def milestone_ms(self, event: str, *, stage: str | None = None) -> float | None:
        for item in self.events:
            if item.event == event and (stage is None or item.stage == stage):
                return item.elapsed_ms
        return None

    def validate(self) -> list[str]:
        errors: list[str] = []
        sequences = [event.sequence for event in self.events]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            errors.append("SSE sequence is not strictly increasing")
        event_types = [event.event for event in self.events]
        if not event_types or event_types[0] != "run_started":
            errors.append("run_started is not the first public event")
        first_status = self.milestone_ms("status")
        first_token = self.milestone_ms("token")
        done = self.milestone_ms("done")
        if not self.cancelled_by_client:
            if first_status is None or done is None or first_status >= done:
                errors.append("first status did not arrive before done")
            if first_token is None or done is None or first_token >= done:
                errors.append("first token did not arrive before done")
            required_tail = ["citations", "final", "done"]
            if event_types[-3:] != required_tail:
                errors.append("successful stream did not end with citations/final/done")
        return errors

    def appears_buffered(self) -> bool | None:
        token = next((event for event in self.events if event.event == "token"), None)
        done = next((event for event in self.events if event.event == "done"), None)
        if token is None or done is None:
            return None
        return token.network_chunk == done.network_chunk

    def safe_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "route": self.route,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "cache_control": self.cache_control,
            "x_accel_buffering": self.accel_buffering,
            "network_chunk_count": self.network_chunk_count,
            "heartbeat_count": self.heartbeat_count,
            "event_count": len(self.events),
            "first_status_ms": self.milestone_ms("status"),
            "first_token_ms": self.milestone_ms("token"),
            "citations_ready_ms": self.milestone_ms("citations"),
            "persisting_ms": self.milestone_ms("status", stage="persisting"),
            "done_ms": self.milestone_ms("done"),
            "appears_buffered": self.appears_buffered(),
            "cancelled_by_client": self.cancelled_by_client,
            "validation_errors": self.validate(),
            "error": self.error,
            "timeline": [
                {
                    "event": event.event,
                    "stage": event.stage,
                    "sequence": event.sequence,
                    "elapsed_ms": round(event.elapsed_ms, 2),
                    "network_chunk": event.network_chunk,
                }
                for event in self.events
                if event.event != "token"
            ],
            "token_event_count": sum(event.event == "token" for event in self.events),
        }


class TimedSSEParser:
    def __init__(self, report: SSEDeliveryReport, started_at: float) -> None:
        self.report = report
        self.started_at = started_at
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._buffer = ""
        self._event_name = "message"
        self._data_lines: list[str] = []

    def feed(self, chunk: bytes, network_chunk: int) -> None:
        self._buffer += self._decoder.decode(chunk)
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._line(line.removesuffix("\r"), network_chunk)

    def finish(self, network_chunk: int) -> None:
        self._buffer += self._decoder.decode(b"", final=True)
        if self._buffer:
            self._line(self._buffer.removesuffix("\r"), network_chunk)
            self._buffer = ""
        self._dispatch(network_chunk)

    def _line(self, line: str, network_chunk: int) -> None:
        if not line:
            self._dispatch(network_chunk)
            return
        if line.startswith(":"):
            self.report.heartbeat_count += 1
            return
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            self._event_name = value
        elif field == "data":
            self._data_lines.append(value)

    def _dispatch(self, network_chunk: int) -> None:
        if not self._data_lines:
            self._event_name = "message"
            return
        raw = "\n".join(self._data_lines)
        event_name = self._event_name
        self._event_name = "message"
        self._data_lines = []
        payload = json.loads(raw)
        sequence = payload.get("sequence")
        if not isinstance(sequence, int):
            raise ValueError(f"{event_name} event has no integer sequence")
        self.report.events.append(
            TimedSSEEvent(
                event=event_name,
                sequence=sequence,
                elapsed_ms=(time.perf_counter() - self.started_at) * 1000,
                network_chunk=network_chunk,
                stage=payload.get("stage")
                if isinstance(payload.get("stage"), str)
                else None,
            )
        )


async def probe_sse_delivery(
    *,
    base_url: str,
    route: str,
    conversation_id: str | None = None,
    library_item_ids: list[str] | None = None,
    timeout_seconds: float = 120.0,
    cancel_after_first_token: bool = False,
    client: httpx.AsyncClient | None = None,
) -> SSEDeliveryReport:
    if client is None:
        timeout = httpx.Timeout(
            connect=min(10.0, timeout_seconds),
            read=timeout_seconds,
            write=min(30.0, timeout_seconds),
            pool=min(10.0, timeout_seconds),
        )
        async with httpx.AsyncClient(timeout=timeout) as owned_client:
            return await probe_sse_delivery(
                base_url=base_url,
                route=route,
                conversation_id=conversation_id,
                library_item_ids=library_item_ids,
                timeout_seconds=timeout_seconds,
                cancel_after_first_token=cancel_after_first_token,
                client=owned_client,
            )
    report = SSEDeliveryReport(base_url=base_url.rstrip("/"), route=route)
    payload = _route_payload(
        route,
        conversation_id=conversation_id,
        library_item_ids=library_item_ids or [],
    )
    started_at = time.perf_counter()
    parser = TimedSSEParser(report, started_at)
    try:
        async with client.stream(
            "POST",
            f"{report.base_url}/api/agent/chat/stream",
            json=payload,
            headers={"Accept": "text/event-stream"},
        ) as response:
            report.status_code = response.status_code
            report.content_type = response.headers.get("content-type")
            report.cache_control = response.headers.get("cache-control")
            report.accel_buffering = response.headers.get("x-accel-buffering")
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                report.network_chunk_count += 1
                parser.feed(chunk, report.network_chunk_count)
                if cancel_after_first_token and any(
                    event.event == "token" for event in report.events
                ):
                    report.cancelled_by_client = True
                    return report
            parser.finish(report.network_chunk_count)
    except Exception as exc:
        report.error = type(exc).__name__
    return report


def _route_payload(
    route: str,
    *,
    conversation_id: str | None,
    library_item_ids: list[str],
) -> dict[str, Any]:
    questions = {
        "local_only": "What does my local library say about Banach spaces?",
        "web_only": "What are the latest official updates about Python?",
        "both": "Explain the closed graph theorem using my library if relevant.",
    }
    if route not in questions:
        raise ValueError("route must be local_only, web_only, or both")
    return {
        "message": questions[route],
        "selected_library_item_ids": library_item_ids,
        **({"conversation_id": conversation_id} if conversation_id else {}),
    }
