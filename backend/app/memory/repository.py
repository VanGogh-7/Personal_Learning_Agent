import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.memory.models import MemoryStatus, MemorySubtype, MemoryType
from app.models.long_term_memory import LongTermMemory


def get_memory_record(
    session: Session, memory_id: uuid.UUID, *, include_deleted: bool = False
) -> LongTermMemory | None:
    memory = session.get(LongTermMemory, memory_id)
    if memory is None or (
        not include_deleted and memory.status == MemoryStatus.DELETED
    ):
        return None
    return memory


def list_memory_records(
    session: Session,
    *,
    namespace: str,
    memory_type: MemoryType | str | None = None,
    memory_subtype: MemorySubtype | str | None = None,
    status: MemoryStatus | str | None = MemoryStatus.ACTIVE,
    limit: int = 20,
    offset: int = 0,
) -> list[LongTermMemory]:
    stmt = select(LongTermMemory).where(LongTermMemory.namespace == namespace)
    if memory_type:
        stmt = stmt.where(LongTermMemory.memory_type == str(memory_type))
    if memory_subtype:
        stmt = stmt.where(LongTermMemory.memory_subtype == str(memory_subtype))
    if status:
        stmt = stmt.where(LongTermMemory.status == str(status))
    return list(
        session.execute(
            stmt.order_by(LongTermMemory.created_at.desc()).offset(offset).limit(limit)
        ).scalars()
    )


def find_active_related_records(
    session: Session,
    *,
    namespace: str,
    memory_type: str,
    memory_subtype: str,
) -> list[LongTermMemory]:
    return list(
        session.execute(
            select(LongTermMemory)
            .where(LongTermMemory.namespace == namespace)
            .where(LongTermMemory.status == MemoryStatus.ACTIVE)
            .where(LongTermMemory.memory_type == memory_type)
            .where(LongTermMemory.memory_subtype == memory_subtype)
            .order_by(LongTermMemory.created_at.desc())
            .limit(30)
        ).scalars()
    )


def soft_delete_memory(session: Session, memory_id: uuid.UUID) -> bool:
    memory = get_memory_record(session, memory_id, include_deleted=True)
    if memory is None:
        return False
    memory.status = MemoryStatus.DELETED
    memory.updated_at = datetime.now(timezone.utc)
    session.flush()
    return True
