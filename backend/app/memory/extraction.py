import re
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from app.memory.models import MemorySubtype, MemoryType, SUBTYPES_BY_TYPE


class MemoryCandidate(BaseModel):
    memory_type: MemoryType
    memory_subtype: MemorySubtype
    content: str = Field(min_length=1, max_length=2000)
    structured_data: dict = Field(default_factory=dict)
    importance: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    durability: float = Field(ge=0.0, le=1.0)
    scope: str | None = Field(default=None, max_length=200)
    sensitive: bool = False
    explicit: bool = False

    @model_validator(mode="after")
    def validate_subtype(self) -> "MemoryCandidate":
        if self.memory_subtype not in SUBTYPES_BY_TYPE[self.memory_type]:
            raise ValueError("memory_subtype is not valid for memory_type")
        self.content = self.content.strip()
        return self


class MemoryCandidateExtractor(Protocol):
    def extract(self, user_message: str) -> list[MemoryCandidate]: ...


class ConservativeMemoryCandidateExtractor:
    """Deterministic, allowlisted extraction for stable user instructions."""

    def extract(self, user_message: str) -> list[MemoryCandidate]:
        text = " ".join(user_message.strip().split())
        if not text or _looks_sensitive(text) or _is_temporary(text):
            return []

        explicit = _has_explicit_memory_intent(text)
        leetcode = re.search(
            r"(?:以后\s*)?(?:LeetCode|leetcode).*?(?:默认使用|改用|使用)\s*(Python|Rust|Java|C\+\+|Go)",
            text,
            re.IGNORECASE,
        )
        if leetcode:
            language = leetcode.group(1)
            return [
                _candidate(
                    MemoryType.SEMANTIC,
                    MemorySubtype.USER_PREFERENCE,
                    f"User prefers {language} for LeetCode.",
                    predicate="preferred_leetcode_language",
                    object_value=language,
                    scope="leetcode",
                    explicit=True,
                )
            ]

        if (
            ("数学定理" in text or "theorem" in text.lower())
            and ("定义" in text or "definition" in text.lower())
            and ("先" in text or "begin" in text.lower() or "start" in text.lower())
        ):
            return [
                _candidate(
                    MemoryType.SEMANTIC,
                    MemorySubtype.USER_PREFERENCE,
                    "When explaining mathematical theorems, begin with definitions.",
                    predicate="math_explanation_order",
                    object_value="definitions_first",
                    scope="mathematics",
                    explicit=explicit or "以后" in text,
                )
            ]

        preference = re.search(
            r"(?:我的偏好是|我偏好|I prefer)\s*[:：]?\s*(.+)", text, re.I
        )
        if preference and explicit:
            value = preference.group(1).strip("。.! ")[:500]
            return [
                _candidate(
                    MemoryType.SEMANTIC,
                    MemorySubtype.USER_PREFERENCE,
                    f"User preference: {value}",
                    predicate="general_preference",
                    object_value=value,
                    scope="general",
                    explicit=True,
                )
            ]

        avoid = re.search(r"(?:不要再|以后不要|do not|don't)\s*(.+)", text, re.I)
        if avoid and explicit:
            value = avoid.group(1).strip("。.! ")[:500]
            return [
                _candidate(
                    MemoryType.PROCEDURAL,
                    MemorySubtype.FAILURE_AVOIDANCE_RULE,
                    f"Avoid this workflow behavior: {value}",
                    predicate="workflow_avoidance",
                    object_value=value,
                    scope="workflow",
                    explicit=True,
                )
            ]
        return []


def _candidate(
    memory_type: MemoryType,
    subtype: MemorySubtype,
    content: str,
    *,
    predicate: str,
    object_value: str,
    scope: str,
    explicit: bool,
) -> MemoryCandidate:
    return MemoryCandidate(
        memory_type=memory_type,
        memory_subtype=subtype,
        content=content,
        structured_data={
            "subject": "user",
            "predicate": predicate,
            "object": object_value,
            "scope": scope,
        },
        importance=0.9 if explicit else 0.78,
        confidence=0.98 if explicit else 0.85,
        durability=0.92 if explicit else 0.78,
        scope=scope,
        sensitive=False,
        explicit=explicit,
    )


def _has_explicit_memory_intent(text: str) -> bool:
    normalized = text.lower()
    return any(
        marker in normalized
        for marker in (
            "记住",
            "以后",
            "从现在开始",
            "不要再",
            "我的偏好",
            "remember",
            "from now on",
            "i prefer",
        )
    )


def _is_temporary(text: str) -> bool:
    normalized = text.lower()
    return any(
        marker in normalized
        for marker in ("今天", "现在有点", "此刻", "today", "right now")
    )


def _looks_sensitive(text: str) -> bool:
    return bool(
        re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
        or re.search(r"\b(?:\+?\d[ -]?){8,15}\b", text)
        or re.search(r"(?:password|密码|api[_ -]?key|身份证)", text, re.I)
    )
