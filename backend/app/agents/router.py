from typing import Literal

AgentRoute = Literal["local_only", "web_only", "both"]

LOCAL_ROUTE_KEYWORDS = (
    "this book",
    "this pdf",
    "the book",
    "the pdf",
    "according to the book",
    "according to this book",
    "according to my book",
    "according to the pdf",
    "in my library",
    "in the library",
    "in the pdf",
    "my books",
    "my book",
    "my pdfs",
    "my pdf",
    "these pdfs",
    "these books",
    "selected pdfs",
    "selected books",
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
    "api",
    "version",
    "release",
    "released",
    "external",
    "web",
    "internet",
    "最新",
    "最近",
    "网络",
    "网上",
)

BOTH_ROUTE_KEYWORDS = (
    "use my book if relevant",
    "use the book if relevant",
    "use my pdf if relevant",
    "use the pdf if relevant",
    "if relevant",
)


def route_question(question: str) -> AgentRoute:
    """Route a question to fixed local/web agent paths using deterministic rules."""
    normalized = " ".join(question.strip().lower().split())
    wants_both = any(keyword in normalized for keyword in BOTH_ROUTE_KEYWORDS)
    wants_local = any(keyword in normalized for keyword in LOCAL_ROUTE_KEYWORDS)
    wants_web = any(keyword in normalized for keyword in WEB_ROUTE_KEYWORDS)

    if wants_both:
        return "both"
    if wants_local and wants_web:
        return "both"
    if wants_local:
        return "local_only"
    if wants_web:
        return "web_only"
    return "both"
