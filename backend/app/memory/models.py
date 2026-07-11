from enum import StrEnum


class MemoryType(StrEnum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"


class MemorySubtype(StrEnum):
    USER_PREFERENCE = "user_preference"
    LEARNING_GOAL = "learning_goal"
    PROJECT_CONTEXT = "project_context"
    STABLE_PROFILE = "stable_profile"
    IMPORTANT_EVENT = "important_event"
    LEARNING_PROGRESS = "learning_progress"
    PROJECT_MILESTONE = "project_milestone"
    EVALUATION_RESULT = "evaluation_result"
    WORKFLOW_PREFERENCE = "workflow_preference"
    SUCCESSFUL_STRATEGY = "successful_strategy"
    FAILURE_AVOIDANCE_RULE = "failure_avoidance_rule"


SUBTYPES_BY_TYPE = {
    MemoryType.SEMANTIC: {
        MemorySubtype.USER_PREFERENCE,
        MemorySubtype.LEARNING_GOAL,
        MemorySubtype.PROJECT_CONTEXT,
        MemorySubtype.STABLE_PROFILE,
    },
    MemoryType.EPISODIC: {
        MemorySubtype.IMPORTANT_EVENT,
        MemorySubtype.LEARNING_PROGRESS,
        MemorySubtype.PROJECT_MILESTONE,
        MemorySubtype.EVALUATION_RESULT,
    },
    MemoryType.PROCEDURAL: {
        MemorySubtype.WORKFLOW_PREFERENCE,
        MemorySubtype.SUCCESSFUL_STRATEGY,
        MemorySubtype.FAILURE_AVOIDANCE_RULE,
    },
}


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    DELETED = "deleted"
    EXPIRED = "expired"


class MemoryAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    SUPERSEDE = "supersede"
    IGNORE = "ignore"
