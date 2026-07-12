import asyncio

import pytest

from app.core.config import Settings
from app.mcp.client import MCPError
from app.mcp.research import plan_research, run_mcp_research


class FakeGateway:
    def __init__(self, responses, failures=()):
        self.responses = responses
        self.failures = set(failures)
        self.calls: list[tuple[str, str]] = []

    async def call(self, server, tool, arguments):
        self.calls.append((server, tool))
        if (server, tool) in self.failures:
            raise MCPError("unavailable")
        return self.responses.get((server, tool), {})


def settings(**values) -> Settings:
    return Settings(
        mcp_enabled=True,
        mcp_max_fetch_urls=0,
        mcp_max_evidence=10,
        **values,
    )


@pytest.mark.anyio
async def test_tavily_search_and_brave_fallback() -> None:
    tavily = {
        "results": [
            {
                "title": "Tavily result",
                "url": "https://example.com/tavily",
                "content": "Useful Tavily evidence.",
            }
        ]
    }
    gateway = FakeGateway({("tavily", "tavily-search"): tavily})
    result = await run_mcp_research(
        "Explain Banach spaces", gateway=gateway, settings=settings()
    )
    assert result.sources[0].provider == "tavily"
    assert gateway.calls == [("tavily", "tavily-search")]

    brave = {
        "web": {
            "results": [
                {
                    "title": "Brave result",
                    "url": "https://example.com/brave",
                    "description": "Independent Brave evidence.",
                }
            ]
        }
    }
    gateway = FakeGateway(
        {("brave", "brave_web_search"): brave},
        failures={("tavily", "tavily-search")},
    )
    result = await run_mcp_research(
        "Explain Banach spaces", gateway=gateway, settings=settings()
    )
    assert result.sources[0].provider == "brave"
    assert "fallback" in result.warnings[0].lower()


@pytest.mark.anyio
async def test_latest_search_runs_tavily_and_brave_in_parallel() -> None:
    active = 0
    maximum = 0

    class ParallelGateway(FakeGateway):
        async def call(self, server, tool, arguments):
            nonlocal active, maximum
            self.calls.append((server, tool))
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {
                "results": [
                    {
                        "title": server,
                        "url": f"https://{server}.example/news",
                        "content": f"Latest evidence from {server}.",
                    }
                ]
            }

    gateway = ParallelGateway({})
    result = await run_mcp_research(
        "What is the latest Python news?", gateway=gateway, settings=settings()
    )
    assert maximum == 2
    assert {item.provider for item in result.sources} == {"tavily", "brave"}


@pytest.mark.anyio
async def test_latest_search_keeps_success_when_one_provider_fails() -> None:
    gateway = FakeGateway(
        {
            ("tavily", "tavily-search"): {
                "results": [
                    {
                        "title": "Available source",
                        "url": "https://example.com/news",
                        "content": "One provider still returned useful evidence.",
                    }
                ]
            }
        },
        failures={("brave", "brave_news_search")},
    )
    result = await run_mcp_research(
        "What is the latest news?", gateway=gateway, settings=settings()
    )
    assert [item.provider for item in result.sources] == ["tavily"]
    assert any("Brave" in warning for warning in result.warnings)


@pytest.mark.anyio
async def test_academic_search_doi_and_partial_failure() -> None:
    paper = {
        "items": [
            {
                "title": "A paper",
                "url": "https://doi.org/10.1000/test",
                "abstract": "Academic evidence.",
                "doi": "10.1000/test",
            }
        ]
    }
    gateway = FakeGateway({("academic", "lookup_doi"): paper})
    result = await run_mcp_research(
        "Find DOI 10.1000/test", gateway=gateway, settings=settings()
    )
    assert result.sources[0].source_type == "academic"
    assert gateway.calls == [("academic", "lookup_doi")]

    gateway = FakeGateway(
        {("academic", "search_arxiv"): paper},
        failures={("academic", "search_openalex")},
    )
    result = await run_mcp_research(
        "Find a research paper about Banach spaces",
        gateway=gateway,
        settings=settings(),
    )
    assert result.sources
    assert "partially" in result.warnings[0].lower()


@pytest.mark.anyio
async def test_fetch_failure_keeps_search_snippet() -> None:
    gateway = FakeGateway(
        {
            ("tavily", "tavily-search"): {
                "results": [
                    {
                        "title": "Search result",
                        "url": "https://example.com/page",
                        "content": "Snippet remains available.",
                    }
                ]
            }
        },
        failures={("fetch", "fetch")},
    )
    result = await run_mcp_research(
        "Explain this topic",
        gateway=gateway,
        settings=Settings(mcp_enabled=True, mcp_max_fetch_urls=1),
    )
    assert result.sources[0].excerpt == "Snippet remains available."
    assert result.sources[0].content is None
    assert any("snippet" in warning for warning in result.warnings)


def test_research_planner_selects_url_academic_and_latest_modes() -> None:
    url = plan_research("Read https://example.com/page")
    academic = plan_research("Find a recent arXiv paper")
    assert url.urls == ("https://example.com/page",)
    assert academic.academic is True
    assert academic.current_or_cross_check is True


@pytest.mark.anyio
async def test_cancellation_stops_research_before_fetch() -> None:
    started = asyncio.Event()

    class SlowGateway(FakeGateway):
        async def call(self, server, tool, arguments):
            self.calls.append((server, tool))
            started.set()
            await asyncio.Event().wait()

    gateway = SlowGateway({})
    task = asyncio.create_task(
        run_mcp_research(
            "Find a research paper about Banach spaces",
            gateway=gateway,
            settings=Settings(mcp_enabled=True, mcp_max_fetch_urls=3),
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gateway.calls
    assert all(server == "academic" for server, _ in gateway.calls)
