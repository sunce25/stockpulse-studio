"""Streamlit skeleton for the future real fund portfolio experience."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from funds.fund_adapter import get_demo_holdings
from funds.fund_analyzer import FundAnalyzer
from funds.portfolio_analyzer import PortfolioAnalyzer
from funds.yangjibao_client import YangJiBaoClient


def _currency(value: float) -> str:
    return f"¥{value:,.2f}"


def render_funds_page() -> None:
    """Render a demo-only page without accessing any external fund provider."""
    st.markdown("<div class='main-title'>💰 我的基金</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='sub-title'>统一基金数据模型与规则型组合分析骨架</div>",
        unsafe_allow_html=True,
    )
    st.warning("当前为示例数据，尚未连接养基宝。页面不会读取或上传真实持仓。")

    holdings = get_demo_holdings()
    portfolio = PortfolioAnalyzer().analyze(holdings)
    fund_analyzer = FundAnalyzer()
    analyses = {
        item["fund_code"]: fund_analyzer.analyze(item) for item in holdings
    }

    overview_tab, detail_tab, source_tab = st.tabs(["组合概览", "基金详情", "数据源"])
    with overview_tab:
        cols = st.columns(6)
        cols[0].metric("基金总资产", _currency(portfolio["total_assets"]))
        cols[1].metric(
            "累计收益",
            _currency(portfolio["total_profit"]),
            f"{portfolio['total_return_pct']:+.2f}%",
        )
        cols[2].metric("今日收益", _currency(portfolio["today_profit"]))
        cols[3].metric("基金数量", f"{portfolio['fund_count']} 只")
        cols[4].metric(
            "最大仓位", f"{portfolio['max_single_position_weight'] * 100:.1f}%"
        )
        cols[5].metric("结构风险", f"{portfolio['risk_score']}/100")

        rows = []
        for item in holdings:
            result = analyses[item["fund_code"]]
            rows.append(
                {
                    "基金": item["fund_name"],
                    "基金代码": item["fund_code"],
                    "市值": item["market_value"],
                    "仓位": item["portfolio_weight"] * 100,
                    "收益": item["holding_return_pct"],
                    "风险状态": result["risk_status"],
                    "数据状态": "已过期" if item["stale_data"] else "正常",
                }
            )
        st.dataframe(
            pd.DataFrame(rows),
            width="stretch",
            hide_index=True,
            column_config={
                "市值": st.column_config.NumberColumn(format="¥ %.2f"),
                "仓位": st.column_config.NumberColumn(format="%.1f%%"),
                "收益": st.column_config.NumberColumn(format="%.2f%%"),
            },
        )
        st.caption("组合结果由 Python 规则引擎生成；不构成投资建议，也不会触发交易。")

    with detail_tab:
        selected_code = st.selectbox(
            "选择示例基金",
            [item["fund_code"] for item in holdings],
            format_func=lambda code: next(
                item["fund_name"] for item in holdings if item["fund_code"] == code
            ),
        )
        selected = next(item for item in holdings if item["fund_code"] == selected_code)
        result = analyses[selected_code]
        left, right = st.columns(2)
        with left:
            st.markdown("#### 标准化持仓")
            st.json(selected)
        with right:
            st.markdown("#### 规则分析")
            st.json(result)
        if selected["is_qdii"]:
            st.info("该示例为 QDII：估算净值不等于最终确认净值，并可能受时区、汇率和净值延迟影响。")

    with source_tab:
        client = YangJiBaoClient()
        st.markdown("#### 养基宝连接状态")
        status_cols = st.columns(3)
        status_cols[0].metric("凭据配置", "已配置" if client.is_configured() else "未配置")
        status_cols[1].metric("接口状态", "未连接")
        status_cols[2].metric("当前数据源", "Demo")
        st.info("养基宝客户端目前仅为隔离接口骨架，不会发起真实请求。Token、Cookie 和账号 ID 不会显示在页面中。")
