import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation_turn import ConversationTurn

DEFAULT_RECENT_TURNS_LIMIT = 5
MAX_RECENT_TURNS_LIMIT = 50


@dataclass
class ConversationTurnResult:
    turn_id: uuid.UUID
    session_id: str
    question: str
    answer: str
    created_at: datetime


def create_session_id() -> str:
    """Generate a new short-term memory session id."""
    return str(uuid.uuid4())


def _validate_session_id(session_id: str) -> None:
    if not session_id or not session_id.strip():
        raise ValueError("session_id must not be empty")


def _validate_limit(limit: int) -> None:
    if not (1 <= limit <= MAX_RECENT_TURNS_LIMIT):
        raise ValueError(f"limit must be between 1 and {MAX_RECENT_TURNS_LIMIT}, got {limit}")


def get_recent_turns(
    session: Session, session_id: str, limit: int = DEFAULT_RECENT_TURNS_LIMIT
) -> list[ConversationTurnResult]:
    """Return the most recent conversation turns for a session, oldest first.

    Bounded by `limit`; only turns belonging to `session_id` are returned.
    """
    _validate_session_id(session_id)
    _validate_limit(limit)

    stmt = (
        select(ConversationTurn)
        .where(ConversationTurn.session_id == session_id)
        .order_by(ConversationTurn.turn_index.desc())
        .limit(limit)
    )
    rows = session.execute(stmt).scalars().all()

    turns = [
        ConversationTurnResult(
            turn_id=row.id,
            session_id=row.session_id,
            question=row.question,
            answer=row.answer,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return list(reversed(turns))


def save_turn(
    session: Session,
    session_id: str,
    question: str,
    answer: str,
    metadata: dict | None = None,
) -> ConversationTurnResult:
    """Persist the current question/answer turn for a session.

    Does not commit; the caller controls the transaction boundary.
    """
    _validate_session_id(session_id)
    if not question or not question.strip():
        raise ValueError("question must not be empty")
    if not answer or not answer.strip():
        raise ValueError("answer must not be empty")

    next_turn_index = session.execute(
        select(func.count())
        .select_from(ConversationTurn)
        .where(ConversationTurn.session_id == session_id)
    ).scalar_one()

    turn = ConversationTurn(
        session_id=session_id,
        question=question,
        answer=answer,
        turn_index=next_turn_index,
        metadata_json=metadata,
    )
    session.add(turn)
    session.flush()

    return ConversationTurnResult(
        turn_id=turn.id,
        session_id=turn.session_id,
        question=turn.question,
        answer=turn.answer,
        created_at=turn.created_at,
    )


def build_memory_context(turns: list[ConversationTurnResult]) -> str:
    """Build a simple, deterministic textual summary of recent turns.

    Not an LLM summary: a bounded, human-readable listing of prior
    question/answer pairs, oldest first. Does not call any external API.
    """
    if not turns:
        return ""

    lines = [
        f"Turn {index}: Q: {turn.question.strip()} | A: {turn.answer.strip()}"
        for index, turn in enumerate(turns, start=1)
    ]
    return "\n".join(lines)
