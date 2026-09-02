"""OpenRouter-only investment copilot facade."""

from __future__ import annotations

from ai.prompts import (
    ASSET_ANALYSIS_PROMPT,
    PORTFOLIO_ANALYSIS_PROMPT,
    QUESTION_ANSWERING_PROMPT,
    SYSTEM_PROMPT,
)
from config.settings import get_setting
from services.openrouter import DEFAULT_OPENROUTER_MODEL, generate_ai_analysis


NOT_CONFIGURED_MESSAGE = "未配置 OPENROUTER_API_KEY，请在环境变量或 Streamlit Secrets 中配置。"
EMPTY_QUESTION_MESSAGE = "请先输入一个关于当前投资组合的问题。"


class AICopilot:
    """Keep business code independent from the OpenRouter HTTP response."""

    def __init__(self, api_key: str | None = None, model: str | None = None, client=None):
        self._api_key = api_key if api_key is not None else get_setting("OPENROUTER_API_KEY")
        self.model = (model if model is not None else get_setting("OPENROUTER_MODEL")) or DEFAULT_OPENROUTER_MODEL
        self._client = client

    def is_configured(self) -> bool:
        return bool(self._api_key and self.model)

    def configuration_status(self) -> dict[str, str]:
        return {
            "model_status": "已配置" if self.model else "未配置",
            "api_status": "已配置" if self._api_key else "未配置",
            "integration_status": "可用" if self.is_configured() else "未配置",
        }

    def _generate(self, context: dict, task_prompt: str) -> dict:
        if self._client is not None:
            return self._client(
                api_key=self._api_key,
                model=self.model,
                system_prompt=SYSTEM_PROMPT,
                task_prompt=task_prompt,
                context=dict(context or {}),
            )
        return generate_ai_analysis(
            api_key=self._api_key,
            model=self.model,
            system_prompt=SYSTEM_PROMPT,
            task_prompt=task_prompt,
            context=dict(context or {}),
        )

    def analyze_portfolio(self, context: dict) -> dict:
        return self._generate(context, PORTFOLIO_ANALYSIS_PROMPT)

    def analyze_asset(self, context: dict) -> dict:
        return self._generate(context, ASSET_ANALYSIS_PROMPT)

    def answer_question(self, context: dict, question: str) -> dict:
        normalized_question = str(question or "").strip()
        if not normalized_question:
            return {"success": False, "model": self.model, "content": None, "error": EMPTY_QUESTION_MESSAGE}
        enriched_context = dict(context or {})
        enriched_context["user_question"] = normalized_question
        return self._generate(enriched_context, QUESTION_ANSWERING_PROMPT)
