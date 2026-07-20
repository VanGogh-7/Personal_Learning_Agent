import asyncio
import json
import socket
import threading
import time

import uvicorn
from fastapi import FastAPI
from starlette.responses import StreamingResponse

from app.reliability.sse_probe import (
    SSEDeliveryReport,
    TimedSSEEvent,
    TimedSSEParser,
    probe_sse_delivery,
)
from scripts.verify_sse_delivery import summarize_reports


def _record(event: str, sequence: int, **values: object) -> bytes:
    payload = {
        "type": event,
        "request_id": "request-1",
        "conversation_id": "conversation-1",
        "run_id": "run-1",
        "sequence": sequence,
        "timestamp": "2026-07-12T00:00:00Z",
        **values,
    }
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode()


def test_timed_sse_parser_collects_split_events_and_milestones() -> None:
    report = SSEDeliveryReport(base_url="http://example", route="local_only")
    parser = TimedSSEParser(report, time.perf_counter())
    records = b"".join(
        [
            _record("run_started", 1),
            _record("status", 2, stage="loading_context", message="loading"),
            _record("token", 3, delta="answer"),
            _record("citations", 4, citations=[], web_sources=[]),
            _record("final", 5, message_id="message-1", response={}),
            _record("done", 6),
        ]
    )
    parser.feed(records[:31], 1)
    parser.feed(records[31:], 2)
    parser.finish(2)
    assert [event.event for event in report.events][-3:] == [
        "citations",
        "final",
        "done",
    ]
    assert report.validate() == []
    assert report.milestone_ms("token") is not None


def test_buffering_detection_uses_actual_network_chunk_boundaries() -> None:
    report = SSEDeliveryReport(base_url="http://example", route="local_only")
    report.events = [
        TimedSSEEvent("token", 1, 10, 2),
        TimedSSEEvent("done", 2, 20, 2),
    ]
    assert report.appears_buffered() is True
    report.events[-1] = TimedSSEEvent("done", 2, 20, 3)
    assert report.appears_buffered() is False


def test_http_probe_summary_excludes_failed_runs_from_percentiles() -> None:
    reports = [
        {
            "validation_errors": [],
            "error": None,
            "appears_buffered": False,
            "first_status_ms": 10.0,
            "first_token_ms": 20.0,
            "citations_ready_ms": 30.0,
            "persisting_ms": 25.0,
            "done_ms": 35.0,
        },
        {
            "validation_errors": ["broken"],
            "error": None,
            "appears_buffered": None,
            "first_status_ms": 1000.0,
            "first_token_ms": 1000.0,
            "citations_ready_ms": None,
            "persisting_ms": None,
            "done_ms": None,
        },
    ]
    summary = summarize_reports(reports)
    assert summary["success_count"] == 1
    assert summary["failure_count"] == 1
    assert summary["metrics"]["first_token_ms"]["p50"] == 20


def test_direct_fastapi_stream_arrives_in_multiple_network_chunks() -> None:
    app = FastAPI()

    @app.post("/api/agent/chat/stream")
    async def stream() -> StreamingResponse:
        async def generate():
            yield _record("run_started", 1)
            yield _record("status", 2, stage="loading_context", message="loading")
            await asyncio.sleep(0.03)
            yield _record("token", 3, delta="answer")
            await asyncio.sleep(0.03)
            yield _record("citations", 4, citations=[], web_sources=[])
            yield _record("final", 5, message_id="message-1", response={})
            yield _record("done", 6)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 3
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        report = asyncio.run(
            probe_sse_delivery(base_url=f"http://127.0.0.1:{port}", route="direct")
        )
        assert report.error is None
        assert report.validate() == []
        assert report.network_chunk_count >= 3
        assert report.appears_buffered() is False
    finally:
        server.should_exit = True
        thread.join(timeout=3)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
