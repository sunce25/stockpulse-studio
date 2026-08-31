"""Streamlit skeleton for the future real fund portfolio experience."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from config.settings import is_configured as setting_is_configured
from funds.fund_adapter import get_demo_holdings
from funds.fund_analyzer import FundAnalyzer
from funds.portfolio_analyzer import PortfolioAnalyzer
from funds.yangjibao_client import YangJiBaoClient, YangJiBaoError


def _currency(value: float) -> str:
    return f"¥{value:,.2f}"


def _qr_png(content: str) -> bytes:
    """Render QR content locally so authorization data is not sent elsewhere."""
    import qrcode

    image = qrcode.make(content)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _clear_yangjibao_session() -> None:
    for key in (
        "_yjb_qr_id",
        "_yjb_qr_url",
        "_yjb_session_token",
        "_yjb_accounts",
        "_yjb_holdings",
        "_yjb_holdings_updated_at",
    ):
        st.session_state.pop(key, None)


def _load_yangjibao_accounts(client: YangJiBaoClient) -> None:
    accounts = client.get_accounts()
    st.session_state["_yjb_accounts"] = accounts


def render_funds_page() -> None:
    """Render normalized real holdings when explicitly synchronized, else Demo."""
    st.markdown("<div class='main-title'>💰 我的基金</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='sub-title'>统一基金数据模型与规则型组合分析骨架</div>",
        unsafe_allow_html=True,
    )
    session_holdings = st.session_state.get("_yjb_holdings")
    using_real_holdings = isinstance(session_holdings, list) and bool(session_holdings)
    if using_real_holdings:
        holdings = session_holdings
        updated_at = st.session_state.get("_yjb_holdings_updated_at", "")
        st.success(
            "当前展示养基宝只读同步数据。"
            + (f" 同步时间：{updated_at}" if updated_at else "")
        )
    else:
        holdings = get_demo_holdings()
        st.warning("当前为示例数据，尚未同步养基宝真实持仓。")
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
            "选择基金" if using_real_holdings else "选择示例基金",
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
        session_token = st.session_state.get("_yjb_session_token")
        client = YangJiBaoClient(token=session_token) if session_token else YangJiBaoClient()
        config_status = client.configuration_status()
        st.markdown("#### 养基宝连接状态")
        status_cols = st.columns(3)
        status_cols[0].metric(
            "连接参数", "已配置" if config_status["signing_configured"] else "未配置"
        )
        status_cols[1].metric(
            "安全传输", "HTTPS" if config_status["secure_transport"] else "已阻止"
        )
        status_cols[2].metric(
            "授权状态",
            "本次会话已授权"
            if session_token
            else "已配置" if config_status["token_configured"] else "未授权",
        )

        st.warning(
            "实验性只读连接：只读取账户和基金持仓，不会新增、删除、修改持仓，也不会执行交易。"
        )
        if not setting_is_configured("APP_PASSWORD"):
            st.error("为防止公开页面被他人扫码，必须先配置 APP_PASSWORD 才能启用养基宝授权。")
        elif not config_status["secure_transport"]:
            st.error("当前接口地址不是 HTTPS，StockPulse 已阻止发送任何授权信息。")
        elif not config_status["signing_configured"]:
            st.info(
                "连接测试尚未启用：请先在 Streamlit Secrets 中配置 "
                "YANGJIBAO_SIGNING_SECRET。页面不会显示其内容。"
            )
        else:
            action_left, action_right = st.columns(2)
            with action_left:
                if st.button("生成养基宝登录二维码", use_container_width=True):
                    _clear_yangjibao_session()
                    try:
                        challenge = client.create_qr_login()
                        st.session_state["_yjb_qr_id"] = challenge["id"]
                        st.session_state["_yjb_qr_url"] = challenge["url"]
                        st.rerun()
                    except YangJiBaoError as exc:
                        st.error(str(exc))
            with action_right:
                if st.button("清除本次授权", use_container_width=True):
                    _clear_yangjibao_session()
                    st.rerun()

            qr_id = st.session_state.get("_yjb_qr_id")
            qr_url = st.session_state.get("_yjb_qr_url")
            if qr_id and qr_url:
                st.markdown("##### 使用养基宝 App 扫码")
                try:
                    st.image(_qr_png(qr_url), width=260)
                except ImportError:
                    st.error("二维码组件尚未安装，请等待应用完成依赖更新。")
                st.caption("二维码只在服务器本地生成；授权会话不会写入 GitHub。")
                if st.button("我已扫码，检查授权状态", type="primary"):
                    try:
                        login = client.poll_qr_login(qr_id)
                        if login["state"] == "authorized":
                            token = login["token"]
                            authorized_client = YangJiBaoClient(token=token)
                            _load_yangjibao_accounts(authorized_client)
                            st.session_state["_yjb_session_token"] = token
                            st.session_state.pop("_yjb_qr_id", None)
                            st.session_state.pop("_yjb_qr_url", None)
                            st.rerun()
                        elif login["state"] == "pending":
                            st.info("尚未完成扫码，请在养基宝 App 中确认后再检查。")
                        else:
                            st.warning("二维码已失效，请重新生成。")
                    except YangJiBaoError as exc:
                        st.error(str(exc))

            if config_status["token_configured"] and not session_token:
                if st.button("验证 Secrets 中已配置的 Token"):
                    try:
                        _load_yangjibao_accounts(client)
                        st.success("连接成功，已读取账户列表。")
                    except YangJiBaoError as exc:
                        st.error(str(exc))

        accounts = st.session_state.get("_yjb_accounts", [])
        if accounts:
            st.success(f"养基宝连接测试成功，共发现 {len(accounts)} 个基金账户。")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "账户": item["display_name"],
                            "基金数量": item["holding_count"],
                            "状态": "可读取",
                        }
                        for item in accounts
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
            st.caption("账户 ID 和 Token 不在页面显示。")

            selected_account_index = st.selectbox(
                "选择需要同步的基金账户",
                options=list(range(len(accounts))),
                format_func=lambda index: (
                    f"{accounts[index]['display_name']}"
                    f"（{accounts[index]['holding_count']} 只）"
                ),
            )
            if st.button(
                "只读同步该账户持仓",
                type="primary",
                use_container_width=True,
            ):
                selected_account = accounts[selected_account_index]
                try:
                    synchronized = client.get_holdings(
                        selected_account["account_id"]
                    )
                    if not synchronized:
                        st.warning("该账户没有返回有效基金持仓，请检查养基宝账户。")
                    else:
                        st.session_state["_yjb_holdings"] = synchronized
                        st.session_state["_yjb_holdings_updated_at"] = max(
                            (
                                str(item.get("updated_at") or "")
                                for item in synchronized
                            ),
                            default="",
                        )
                        st.rerun()
                except YangJiBaoError as exc:
                    st.error(str(exc))
