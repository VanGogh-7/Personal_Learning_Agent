from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_env_example_contains_llm_placeholders_only() -> None:
    content = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8")

    assert "LLM_PROVIDER=deterministic" in content
    assert "EMBEDDING_PROVIDER=mock" in content
    assert "WEB_RESEARCH_PROVIDER=none" in content
    assert "TAVILY_API_KEY=your_tavily_api_key_here" in content
    assert "TAVILY_BASE_URL=https://api.tavily.com/search" in content
    assert "DEEPSEEK_API_KEY=your_deepseek_api_key_here" in content
    assert "DEEPSEEK_MODEL=deepseek-chat" in content
    assert "DEEPSEEK_BASE_URL=https://api.deepseek.com" in content
    assert "ZHIPU_API_KEY=your_zhipu_api_key_here" in content
    assert "ZHIPU_EMBEDDING_MODEL=embedding-3" in content
    assert "ZHIPU_EMBEDDING_DIMENSION=2048" in content
    assert "sk-" not in content
