"""Streamlit placeholder UI for the provider-neutral investment copilot."""

from __future__ import annotations

import streamlit as st

from ai.context_builder import build_analysis_context
from ai.copilot import AICopilot
from funds.fund_adapter import get_demo_holdings
from funds.portfolio_analyzer import PortfolioAnalyzer


def render_ai_copilot_page() -> None:
    """Render configuration status and rule results without calling an LLM."""
    st.markdown("<div class='main-title'>🧠 AI 投资助手</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='sub-title'>基于真实持仓与量化结果进行解释、总结和问答的占位架构</div>",
        unsafe_allow_html=True,
    )
    st.warning("当前为架构占位模式：不会调用任何 LLM API，也不会执行交易。")

    copilot = AICopilot()
    status = copilot.configuration_status()
    status_cols = st.columns(4)
    status_cols[0].metric("AI Provider", status["provider"])
    status_cols[1].metric("模型状态", status["model_status"])
    status_cols[2].metric("API 配置状态", status["api_status"])
    status_cols[3].metric("运行状态", status["integration_status"])

    holdings = get_demo_holdings()
    portfolio = PortfolioAnalyzer().analyze(holdings)
    st.markdown("#### 当前规则分析摘要（示例数据）")
    summary_cols = st.columns(4)
    summary_cols[0].metric("组合资产", f"¥{portfolio['total_assets']:,.2f}")
    summary_cols[1].metric("最大仓位", f"{portfolio['max_single_position_weight'] * 100:.1f}%")
    summary_cols[2].metric("集中度评分", f"{portfolio['concentration_score']:.1f}")
    summary_cols[3].metric("结构风险评分", f"{portfolio['risk_score']}/100")

    question = st.text_area(
        "向投资助手提问",
        placeholder=(
            "例如：我的科技基金仓位是不是太高？\n"
            "为什么最近组合回撤比较大？\n"
            "现在组合最大的风险是什么？\n"
            "哪些基金相关性可能过高？"
        ),
        height=120,
    )
    if st.button("分析问题", type="primary", width="stretch"):
        context = build_analysis_context(
            portfolio_summary=portfolio,
            holdings=holdings,
            risk_summary={
                "risk_score": portfolio["risk_score"],
                "concentration_score": portfolio["concentration_score"],
                "stale_data": portfolio["stale_data"],
            },
            market_context={"status": "未接入", "stale_data": True},
            user_question=question,
        )
        st.info(copilot.answer_question(context, question))

    st.caption("AI 未来只解释 Python/Quant 引擎生成的结构化结果；客观指标保持只读。")
