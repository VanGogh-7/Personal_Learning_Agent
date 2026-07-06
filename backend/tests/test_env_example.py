from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_env_example_contains_llm_placeholders_only() -> None:
    content = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8")

    assert "LLM_PROVIDER=deterministic" in content
    assert "DEEPSEEK_API_KEY=your_deepseek_api_key_here" in content
    assert "DEEPSEEK_MODEL=deepseek-chat" in content
    assert "DEEPSEEK_BASE_URL=https://api.deepseek.com" in content
    assert "sk-" not in content
