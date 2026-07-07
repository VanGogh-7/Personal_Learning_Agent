from app.core.config import Settings, get_settings


class DeepSeekClient:
    """Minimal DeepSeek configuration wrapper.

    Reads configuration only; does not perform any network calls on
    import or instantiation. The OpenAI-compatible provider performs
    completion calls only when selected explicitly by backend config.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self.api_key = settings.deepseek_api_key
        self.base_url = settings.deepseek_base_url
        self.model = settings.deepseek_model

    def is_configured(self) -> bool:
        return bool(self.api_key)
