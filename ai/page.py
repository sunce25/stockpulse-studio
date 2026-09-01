"""Streamlit UI for the provider-neutral investment copilot."""

from __future__ import annotations

import streamlit as st

from ai.context_builder import build_analysis_context, build_analysis_history_record
from ai.copilot import AICopilot
from ai.providers import GeminiProviderError
from config.settings import get_setting
from funds.fund_adapter import get_demo_holdings
from funds.portfolio_analyzer import PortfolioAnalyzer
from funds.snapshot_store import FundSnapshotError, SupabaseFundSnapshotStore


def _load_portfolio_holdings() -> tuple[list[dict], bool, str]:
    """Use session holdings first, then the provider-neutral private snapshot."""
    session_holdings = st.session_state.get("_yjb_holdings")
    if isinstance(session_holdings, list) and session_holdings:
        return session_holdings, True, "当前会话中的养基宝标准化持仓"

    project_url = get_setting("SUPABASE_URL")
    secret_key = get_setting("SUPABASE_SECRET_KEY")
    if project_url and secret_key:
        record_id = get_setting(
            "FUND_SNAPSHOT_RECORD_ID",
            f"{get_setting('WATCHLIST_RECORD_ID', 'primary')}-funds",
        )
        try:
            snapshot = SupabaseFundSnapshotStore(
                project_url, secret_key, record_id
            ).load()
        except (FundSnapshotError, ValueError) as exc:
            st.session_state["_ai_snapshot_error"] = str(exc)
        else:
            if snapshot and snapshot.get("holdings"):
                holdings = snapshot["holdings"]
                st.session_state["_yjb_holdings"] = holdings
                st.session_state["_yjb_holdings_updated_at"] = snapshot.get(
                    "updated_at", ""
                )
                return holdings, True, "Supabase中的最近养基宝标准化快照"

    return get_demo_holdings(), False, "明确标记的示例数据"


def _record_response(copilot: AICopilot, portfolio: dict, answer: str) -> None:
    record = build_analysis_history_record(
        portfolio_snapshot=portfolio,
        rule_version="portfolio-rules-v1",
        risk_score=portfolio.get("risk_score"),
        recommendation="观察",
        llm_provider=copilot.provider,
        llm_model=copilot.model,
        ai_explanation=answer,
    )
    history = st.session_state.get("_ai_analysis_history", [])
    st.session_state["_ai_analysis_history"] = [record, *history][:20]
    st.session_state["_ai_last_response"] = answer


def render_ai_copilot_page() -> None:
    """Render rule results and optional, explicitly authorized Gemini analysis."""
    st.markdown("<div class='main-title'>🧠 AI 投资助手</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='sub-title'>Python 规则分析 + Gemini 解释与持仓问答</div>",
        unsafe_allow_html=True,
    )

    copilot = AICopilot()
    status = copilot.configuration_status()
    status_cols = st.columns(4)
    status_cols[0].metric("AI Provider", status["provider"])
    status_cols[1].metric("模型状态", status["model_status"])
    status_cols[2].metric("API 配置状态", status["api_status"])
    status_cols[3].metric("运行状态", status["integration_status"])

    holdings, using_real_holdings, source_label = _load_portfolio_holdings()
    portfolio = PortfolioAnalyzer().analyze(holdings)
    if using_real_holdings:
        st.success(f"AI上下文数据源：{source_label}。")
    else:
        st.warning("AI当前只能使用示例数据；请先同步养基宝或配置基金快照。")
    snapshot_error = st.session_state.pop("_ai_snapshot_error", "")
    if snapshot_error:
        st.warning(snapshot_error)

    st.markdown("#### Python规则分析摘要")
    summary_cols = st.columns(4)
    summary_cols[0].metric("组合资产", f"¥{portfolio['total_assets']:,.2f}")
    summary_cols[1].metric(
        "最大仓位", f"{portfolio['max_single_position_weight'] * 100:.1f}%"
    )
    summary_cols[2].metric("集中度评分", f"{portfolio['concentration_score']:.1f}")
    summary_cols[3].metric("结构风险评分", f"{portfolio['risk_score']}/100")

    if not copilot.is_configured():
        st.info("尚未配置 Gemini。配置完成前，本页面只展示上方规则分析结果。")
    elif copilot.provider != "gemini":
        st.warning("当前只启用了 Gemini Provider，请将 LLM_PROVIDER 设置为 gemini。")
    else:
        st.warning(
            "隐私提示：勾选授权并提交后，标准化基金名称、仓位、市值、收益、规则评分和数据时间"
            "会发送给 Google Gemini；Token、Cookie、账户 ID、Supabase Secret 和 API Key 不会进入上下文。"
        )

    with st.form("ai_copilot_form", clear_on_submit=False):
        question = st.text_area(
            "向投资助手提问",
            placeholder=(
                "例如：我的科技基金仓位是不是太高？\n"
                "为什么最近组合回撤比较大？\n"
                "现在组合最大的风险是什么？\n"
                "哪些基金的风险敞口可能重复？"
            ),
            height=120,
        )
        consent = st.checkbox(
            "我确认本次可将上述标准化投资组合数据发送给 Gemini 进行分析。"
        )
        action_cols = st.columns(2)
        analyze_clicked = action_cols[0].form_submit_button(
            "生成组合解读", use_container_width=True
        )
        ask_clicked = action_cols[1].form_submit_button(
            "回答我的问题", type="primary", use_container_width=True
        )

    if analyze_clicked or ask_clicked:
        if not copilot.is_configured():
            st.info("Gemini尚未配置，因此没有发送任何数据。")
        elif not using_real_holdings:
            st.warning("当前是示例数据。为避免误导，本次没有调用 Gemini。")
        elif not consent:
            st.warning("请先确认数据发送授权；本次没有调用 Gemini。")
        else:
            context = build_analysis_context(
                portfolio_summary=portfolio,
                holdings=holdings,
                risk_summary={
                    "risk_score": portfolio["risk_score"],
                    "concentration_score": portfolio["concentration_score"],
                    "largest_position": portfolio.get("largest_position", {}),
                    "stale_data": portfolio["stale_data"],
                },
                market_context={"status": "本次未提供市场环境数据"},
                user_question=question,
            )
            try:
                with st.spinner("Gemini正在解释规则分析结果…"):
                    answer = (
                        copilot.answer_question(context, question)
                        if ask_clicked
                        else copilot.analyze_portfolio(context)
                    )
            except (GeminiProviderError, ValueError) as exc:
                st.error(str(exc))
            else:
                _record_response(copilot, portfolio, answer)

    answer = st.session_state.get("_ai_last_response", "")
    if answer:
        st.markdown("#### Gemini分析结果")
        st.markdown(answer)
        st.caption(
            f"Provider：{copilot.provider} · 模型：{copilot.model} · "
            "仅供决策参考，不构成投资建议，不会执行交易。"
        )

    history = st.session_state.get("_ai_analysis_history", [])
    if history:
        with st.expander(f"本次会话分析记录（{len(history)} 条）"):
            for item in history:
                st.caption(
                    f"{item['timestamp']} · {item['llm_provider']} · {item['llm_model']} · "
                    f"风险分 {item['risk_score']}"
                )

    st.caption("客观指标由Python规则引擎计算；Gemini只负责解释、总结和问答。")
