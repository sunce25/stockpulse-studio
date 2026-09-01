"""Provider-neutral AI facade for investment explanations and questions."""

from __future__ import annotations

from config.settings import get_setting
from ai.prompts import (
    ASSET_ANALYSIS_PROMPT,
    PORTFOLIO_ANALYSIS_PROMPT,
    QUESTION_ANSWERING_PROMPT,
    SYSTEM_PROMPT,
)
from ai.providers import GeminiProvider, GeminiProviderError


NOT_CONFIGURED_MESSAGE = "尚未配置 AI 模型，本页面当前仅展示规则分析结果。"
PLACEHOLDER_MESSAGE = "AI 模型配置已检测到，但当前版本尚未启用真实 API 调用，仅展示规则分析结果。"
UNSUPPORTED_PROVIDER_MESSAGE = "当前配置的 AI Provider 尚未接入，请选择 Gemini。"
EMPTY_QUESTION_MESSAGE = "请先输入一个关于当前投资组合的问题。"


class AICopilot:
    """Stable facade for future OpenAI, Gemini, Claude, or DeepSeek adapters."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        provider_client: object | None = None,
    ):
        self.provider = (
            provider if provider is not None else get_setting("LLM_PROVIDER")
        ).strip().lower()
        self._api_key = api_key if api_key is not None else (
            get_setting("GEMINI_API_KEY") or get_setting("LLM_API_KEY")
        )
        configured_model = model if model is not None else get_setting("LLM_MODEL")
        self.model = configured_model or (
            "gemini-3.7-flash" if self.provider == "gemini" else ""
        )
        self._provider_client = provider_client

    def is_configured(self) -> bool:
        return bool(self.provider and self._api_key and self.model)

    def configuration_status(self) -> dict[str, str]:
        """Expose status labels only; never return the API key."""
        return {
            "provider": self.provider or "未配置",
            "model_status": "已配置" if self.model else "未配置",
            "api_status": "已配置" if self._api_key else "未配置",
            "integration_status": (
                "可用"
                if self.is_configured() and self.provider == "gemini"
                else "Provider未支持"
                if self.is_configured()
                else "未配置"
            ),
        }

    def _placeholder_response(self) -> str:
        return PLACEHOLDER_MESSAGE if self.is_configured() else NOT_CONFIGURED_MESSAGE

    def _client(self):
        if self._provider_client is not None:
            return self._provider_client
        if self.provider == "gemini":
            return GeminiProvider(self._api_key, self.model)
        return None

    def _generate(self, context: dict, task_prompt: str) -> str:
        if not self.is_configured():
            return NOT_CONFIGURED_MESSAGE
        client = self._client()
        if client is None:
            return UNSUPPORTED_PROVIDER_MESSAGE
        try:
            return client.generate(
                system_prompt=SYSTEM_PROMPT,
                task_prompt=task_prompt,
                context=dict(context or {}),
            )
        except (GeminiProviderError, ValueError):
            raise

    def analyze_portfolio(self, context: dict) -> str:
        return self._generate(context, PORTFOLIO_ANALYSIS_PROMPT)

    def analyze_asset(self, context: dict) -> str:
        return self._generate(context, ASSET_ANALYSIS_PROMPT)

    def answer_question(self, context: dict, question: str) -> str:
        normalized_question = str(question or "").strip()
        if not normalized_question:
            return EMPTY_QUESTION_MESSAGE
        enriched_context = dict(context or {})
        enriched_context["user_question"] = normalized_question
        return self._generate(enriched_context, QUESTION_ANSWERING_PROMPT)
