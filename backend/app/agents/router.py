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
    "\u6211\u7684\u4e66",
    "\u4e66\u5e93",
    "\u6211\u7684 pdf",
    "\u6211\u7684pdf",
    "\u6839\u636e\u6211\u7684\u8d44\u6599",
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
    "\u6700\u65b0",
    "\u6700\u8fd1",
    "\u7f51\u7edc",
    "\u7f51\u4e0a",
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
