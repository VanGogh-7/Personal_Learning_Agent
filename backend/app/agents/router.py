from typing import Literal

AgentRoute = Literal["local_only", "web_only", "both"]

LOCAL_ROUTE_KEYWORDS = (
    "my books",
    "my book",
    "my pdfs",
    "my pdf",
    "library",
    "imported documents",
    "imported document",
    "我的书",
    "书库",
    "我的 pdf",
    "我的pdf",
    "根据我的资料",
)

WEB_ROUTE_KEYWORDS = (
    "latest",
    "recent",
    "current",
    "news",
    "web",
    "internet",
    "最新",
    "最近",
    "网络",
    "网上",
)


def route_question(question: str) -> AgentRoute:
    """Route a question to fixed local/web agent paths using deterministic rules."""
    normalized = " ".join(question.strip().lower().split())
    wants_local = any(keyword in normalized for keyword in LOCAL_ROUTE_KEYWORDS)
    wants_web = any(keyword in normalized for keyword in WEB_ROUTE_KEYWORDS)

    if wants_local and wants_web:
        return "both"
    if wants_local:
        return "local_only"
    if wants_web:
        return "web_only"
    return "both"

