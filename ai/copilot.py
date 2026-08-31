"""Provider-neutral AI interface. This release intentionally calls no LLM API."""

from __future__ import annotations

from config.settings import get_setting


NOT_CONFIGURED_MESSAGE = "尚未配置 AI 模型，本页面当前仅展示规则分析结果。"
PLACEHOLDER_MESSAGE = "AI 模型配置已检测到，但当前版本尚未启用真实 API 调用，仅展示规则分析结果。"


class AICopilot:
    """Stable facade for future OpenAI, Gemini, Claude, or DeepSeek adapters."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.provider = provider if provider is not None else get_setting("LLM_PROVIDER")
        self._api_key = api_key if api_key is not None else get_setting("LLM_API_KEY")
        self.model = model if model is not None else get_setting("LLM_MODEL")

    def is_configured(self) -> bool:
        return bool(self.provider and self._api_key and self.model)

    def configuration_status(self) -> dict[str, str]:
        """Expose status labels only; never return the API key."""
        return {
            "provider": self.provider or "未配置",
            "model_status": "已配置" if self.model else "未配置",
            "api_status": "已配置" if self._api_key else "未配置",
            "integration_status": "占位模式",
        }

    def _placeholder_response(self) -> str:
        return PLACEHOLDER_MESSAGE if self.is_configured() else NOT_CONFIGURED_MESSAGE

    def analyze_portfolio(self, context: dict) -> str:
        _ = context
        return self._placeholder_response()

    def analyze_asset(self, context: dict) -> str:
        _ = context
        return self._placeholder_response()

    def answer_question(self, context: dict, question: str) -> str:
        _ = (context, question)
        return self._placeholder_response()
