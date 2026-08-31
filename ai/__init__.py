"""Provider-neutral AI copilot interfaces and structured context builders."""

from ai.context_builder import build_analysis_context, build_analysis_history_record
from ai.copilot import AICopilot

__all__ = ["AICopilot", "build_analysis_context", "build_analysis_history_record"]
