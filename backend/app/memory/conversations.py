import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.conversation import Conversation


@dataclass(frozen=True)
class ConversationIdentity:
    conversation_id: uuid.UUID
    thread_id: str
    session_id: str
    namespace: str


def resolve_conversation(
    session: Session,
    *,
    conversation_id: uuid.UUID | None = None,
    legacy_session_id: str | None = None,
) -> ConversationIdentity:
    """Resolve or create the product conversation and hidden graph thread."""
    conversation: Conversation | None = None
    if conversation_id is not None:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            raise ValueError("Conversation not found")
    elif legacy_session_id:
        conversation = session.execute(
            select(Conversation).where(
                Conversation.legacy_session_id == legacy_session_id.strip()
            )
        ).scalar_one_or_none()

    if conversation is None:
        generated_id = uuid.uuid4()
        conversation = Conversation(
            id=generated_id,
            thread_id=str(uuid.uuid4()),
            namespace=get_settings().memory_default_namespace,
            legacy_session_id=legacy_session_id.strip()
            if legacy_session_id
            else str(generated_id),
        )
        session.add(conversation)
        session.flush()

    return ConversationIdentity(
        conversation_id=conversation.id,
        thread_id=conversation.thread_id,
        session_id=conversation.legacy_session_id or str(conversation.id),
        namespace=conversation.namespace,
    )
