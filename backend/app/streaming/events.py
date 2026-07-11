from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.agents.router import AgentRoute
from app.graphs.schemas import AgentChatResponse, WebSource
from app.rag.schemas import RagCitation

AgentActivityStage = Literal[
    "loading_context",
    "retrieving_memory",
    "routing",
    "retrieving_local",
    "searching_web",
    "processing_sources",
    "synthesizing",
    "streaming",
    "persisting",
]


class AgentStreamEventBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    request_id: str
    conversation_id: str
    run_id: str
    sequence: int = Field(ge=1)
    timestamp: datetime


class RunStartedEvent(AgentStreamEventBase):
    type: Literal["run_started"] = "run_started"
    ui_flush_interval_ms: int = Field(ge=30, le=80)


class StatusEvent(AgentStreamEventBase):
    type: Literal["status"] = "status"
    stage: AgentActivityStage
    message: str


class RouteSelectedEvent(AgentStreamEventBase):
    type: Literal["route_selected"] = "route_selected"
    route: AgentRoute


class RetrievalCompletedEvent(AgentStreamEventBase):
    type: Literal["retrieval_completed"] = "retrieval_completed"
    source: Literal["local", "web"]
    result_count: int = Field(ge=0)


class TokenEvent(AgentStreamEventBase):
    type: Literal["token"] = "token"
    delta: str


class CitationsEvent(AgentStreamEventBase):
    type: Literal["citations"] = "citations"
    citations: list[RagCitation]
    web_sources: list[WebSource]


class WarningEvent(AgentStreamEventBase):
    type: Literal["warning"] = "warning"
    message: str


class FinalEvent(AgentStreamEventBase):
    type: Literal["final"] = "final"
    message_id: str
    response: AgentChatResponse


class DoneEvent(AgentStreamEventBase):
    type: Literal["done"] = "done"


class CancelledEvent(AgentStreamEventBase):
    type: Literal["cancelled"] = "cancelled"
    partial_output_preserved: bool = True


class ErrorEvent(AgentStreamEventBase):
    type: Literal["error"] = "error"
    code: str
    message: str
    recoverable: bool
    partial_output_preserved: bool


AgentStreamEvent = Annotated[
    RunStartedEvent
    | StatusEvent
    | RouteSelectedEvent
    | RetrievalCompletedEvent
    | TokenEvent
    | CitationsEvent
    | WarningEvent
    | FinalEvent
    | DoneEvent
    | CancelledEvent
    | ErrorEvent,
    Field(discriminator="type"),
]

EventModel = TypeVar("EventModel", bound=AgentStreamEventBase)


class AgentStreamEventFactory:
    def __init__(
        self,
        *,
        request_id: str,
        conversation_id: str,
        run_id: str | None = None,
    ) -> None:
        self.request_id = request_id
        self.conversation_id = conversation_id
        self.run_id = run_id or str(uuid.uuid4())
        self._sequence = 0

    def create(self, model: type[EventModel], **values: object) -> EventModel:
        self._sequence += 1
        return model(
            request_id=self.request_id,
            conversation_id=self.conversation_id,
            run_id=self.run_id,
            sequence=self._sequence,
            timestamp=datetime.now(timezone.utc),
            **values,
        )


def encode_sse_event(event: AgentStreamEventBase) -> bytes:
    """Encode one public event as a UTF-8 SSE record."""
    data = event.model_dump_json(exclude_none=True)
    return f"event: {event.type}\ndata: {data}\n\n".encode("utf-8")


def encode_sse_heartbeat() -> bytes:
    return b": ping\n\n"
