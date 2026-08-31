# -*- coding: utf-8 -*-
"""
StockPulse Studio - 智能股票趋势可视化与多维选股系统
Main Streamlit Application
"""
import streamlit as st
import pandas as pd
import numpy as np
import datetime
import hmac
import plotly.graph_objects as go

try:
    from st_aggrid import AgGrid, DataReturnMode, GridOptionsBuilder
except ImportError:
    AgGrid = DataReturnMode = GridOptionsBuilder = None

# 导入自定义模块
from modules.data_adapter import DataAdapter, POPULAR_STOCKS
from modules.indicators import add_all_indicators
from modules.chart_builder import create_stock_chart
from modules.cloud_storage import create_watchlist_manager
from modules.screener import StockScreener
from modules.analyzer import TechnicalAnalyzer
from modules.watchlist import has_active_position
from config.settings import get_setting
from funds.page import render_funds_page
from ai.page import render_ai_copilot_page

# 页面基础配置
st.set_page_config(
    page_title="StockPulse - 股票趋势可视化与多维选股系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义现代金融 UI 样式
st.markdown("""
<style>
    /* 全局主字体优化 */
    .stApp {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    
    /* 标题与副标题 */
    .main-title {
        font-size: 26px;
        font-weight: 700;
        margin-bottom: 2px;
        color: #1e293b;
    }
    .sub-title {
        font-size: 14px;
        color: #64748b;
        margin-bottom: 16px;
    }
    
    /* KPI 核心指标卡片 */
    .metric-card {
        background: rgba(248, 250, 252, 0.8);
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 12px 16px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }
    .metric-label {
        font-size: 12px;
        color: #64748b;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 20px;
        font-weight: 700;
    }
    
    /* 涨跌颜色标签 */
    .up-tag {
        color: #ef4444;
        font-weight: 600;
    }
    .down-tag {
        color: #22c55e;
        font-weight: 600;
    }
    
    /* 诊断信号标签 */
    .signal-pill-bullish {
        background-color: rgba(239, 68, 68, 0.1);
        color: #ef4444;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
        display: inline-block;
        margin: 2px;
    }
    .signal-pill-bearish {
        background-color: rgba(34, 197, 94, 0.1);
        color: #22c55e;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
        display: inline-block;
        margin: 2px;
    }
    .signal-pill-warning {
        background-color: rgba(245, 158, 11, 0.1);
        color: #f59e0b;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
        display: inline-block;
        margin: 2px;
    }
</style>
""", unsafe_allow_html=True)


def require_app_password() -> None:
    """Protect portfolio data when APP_PASSWORD is configured in the cloud."""
    expected_password = get_setting("APP_PASSWORD")
    if not expected_password or st.session_state.get("app_access_granted", False):
        return

    st.markdown("<div class='main-title'>🔒 StockPulse 私有访问</div>", unsafe_allow_html=True)
    st.caption("请输入部署时设置的访问密码。")
    with st.form("stockpulse_access_form"):
        entered_password = st.text_input("访问密码", type="password")
        submitted = st.form_submit_button("进入应用", use_container_width=True)
    if submitted:
        if hmac.compare_digest(entered_password, expected_password):
            st.session_state["app_access_granted"] = True
            st.rerun()
        st.error("访问密码不正确。")
    st.stop()


require_app_password()


# 初始化单例服务
SERVICE_CACHE_VERSION = "2026-08-31-live-quotes-v4"


@st.cache_resource
def get_services(cache_version: str):
    # The version participates in Streamlit's cache key so service API changes
    # never reuse an instance created from an older class definition.
    _ = cache_version
    adapter = DataAdapter()
    screener = StockScreener(adapter)
    analyzer = TechnicalAnalyzer()
    return adapter, screener, analyzer

adapter, screener, analyzer = get_services(SERVICE_CACHE_VERSION)
supabase_url = get_setting("SUPABASE_URL")
supabase_secret_key = get_setting("SUPABASE_SECRET_KEY")
watchlist_record_id = get_setting("WATCHLIST_RECORD_ID", "primary")
cloud_config_incomplete = bool(supabase_url) != bool(supabase_secret_key)
watchlist_mgr = create_watchlist_manager(
    supabase_url=supabase_url,
    supabase_secret_key=supabase_secret_key,
    record_id=watchlist_record_id,
)
watchlist_mgr.reload()


def set_watchlist_symbols_hidden(symbols, hidden: bool = True) -> int:
    """Hide/restore symbols even if hot reload left a legacy manager instance alive."""
    normalized_symbols = {
        str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()
    }
    if not normalized_symbols:
        return 0

    manager_setter = getattr(watchlist_mgr, "set_stocks_hidden", None)
    if callable(manager_setter):
        return manager_setter(list(normalized_symbols), hidden=hidden)

    # Compatibility path for Streamlit sessions that imported the class before
    # set_stocks_hidden was added. This can be removed after all servers restart.
    watchlist_mgr.reload()
    changed_count = 0
    for item in watchlist_mgr.data.get("items", []):
        if str(item.get("symbol", "")).upper() not in normalized_symbols:
            continue
        current_value = bool(item.get("hidden_from_portfolio", False))
        if current_value == hidden:
            continue
        if hidden:
            item["hidden_from_portfolio"] = True
        else:
            item.pop("hidden_from_portfolio", None)
        changed_count += 1

    if changed_count:
        watchlist_mgr.save()
    return changed_count


def reorder_watchlist_symbols(ordered_symbols) -> bool:
    """Persist a subset order, including compatibility with a hot-reloaded old manager."""
    normalized_order = []
    seen = set()
    for symbol in ordered_symbols:
        normalized = str(symbol).strip().upper()
        if normalized and normalized not in seen:
            normalized_order.append(normalized)
            seen.add(normalized)
    if len(normalized_order) < 2:
        return False

    manager_reorder = getattr(watchlist_mgr, "reorder_stocks", None)
    if callable(manager_reorder):
        return manager_reorder(normalized_order)

    watchlist_mgr.reload()
    item_by_symbol = {
        str(item.get("symbol", "")).upper(): item
        for item in watchlist_mgr.data.get("items", [])
    }
    if any(symbol not in item_by_symbol for symbol in normalized_order):
        return False

    selected_set = set(normalized_order)
    reordered_selected = iter(item_by_symbol[symbol] for symbol in normalized_order)
    reordered_items = [
        next(reordered_selected) if str(item.get("symbol", "")).upper() in selected_set else item
        for item in watchlist_mgr.data.get("items", [])
    ]
    old_symbols = [str(item.get("symbol", "")).upper() for item in watchlist_mgr.data.get("items", [])]
    new_symbols = [str(item.get("symbol", "")).upper() for item in reordered_items]
    if old_symbols == new_symbols:
        return False

    watchlist_mgr.data["items"] = reordered_items
    for index, item in enumerate(watchlist_mgr.data["items"], start=1):
        item["sort_order"] = index
    watchlist_mgr.save()
    return True


def rename_watchlist_group(old_name: str, new_name: str) -> bool:
    """Rename a group even when hot reload retained a legacy manager class."""
    manager_rename = getattr(watchlist_mgr, "rename_group", None)
    if callable(manager_rename):
        return manager_rename(old_name, new_name)

    watchlist_mgr.reload()
    old_name = str(old_name).strip()
    new_name = str(new_name).strip()
    groups_data = watchlist_mgr.data.setdefault("groups", ["全部"])
    if (
        not old_name
        or old_name == "全部"
        or old_name not in groups_data
        or not new_name
        or new_name in groups_data
    ):
        return False
    groups_data[groups_data.index(old_name)] = new_name
    for item in watchlist_mgr.data.get("items", []):
        if item.get("group") == old_name:
            item["group"] = new_name
    watchlist_mgr.save()
    return True


def get_usd_cny_reference_rate() -> float:
    """Remain usable while a running Streamlit session still holds a legacy adapter."""
    rate_getter = getattr(adapter, "get_usd_cny_rate", None)
    if not callable(rate_getter):
        return 6.745925
    try:
        rate = float(rate_getter())
        return rate if 5.0 <= rate <= 10.0 else 6.745925
    except (AttributeError, TypeError, ValueError):
        return 6.745925

# 初始化 session_state
if "current_symbol" not in st.session_state:
    st.session_state.current_symbol = "NVDA"
if "current_market" not in st.session_state:
    st.session_state.current_market = "美股"

SYMBOL_SEARCH_KEY = "symbol_search_input"
SIDEBAR_SYMBOL_KEY = "sidebar_watchlist_symbol"


def select_current_symbol(symbol: str, market: str = None) -> None:
    """Update the selected symbol from a widget callback without stale-state rewrites."""
    normalized_symbol = str(symbol).strip().upper()
    if not normalized_symbol:
        return
    st.session_state.current_symbol = normalized_symbol
    st.session_state.current_market = market or adapter.detect_market(normalized_symbol)
    # Callbacks may safely synchronize a different widget before the next script run.
    st.session_state[SYMBOL_SEARCH_KEY] = normalized_symbol


def select_symbol_from_search() -> None:
    """Promote the search widget value to the single current-symbol state."""
    select_current_symbol(st.session_state.get(SYMBOL_SEARCH_KEY, ""))

# -------------------------------------------------------------
# 侧边栏 (Sidebar)
# -------------------------------------------------------------
with st.sidebar:
    st.markdown("### 📊 **StockPulse Studio**")
    st.caption("A股 · 美股 · ETF 趋势与多维智能选股")
    st.markdown("---")

    nav_option = st.radio(
        "功能导航",
        [
            "📈 个股深度走势",
            "🔍 多维策略选股",
            "⭐ 自选股与组合",
            "💰 我的基金",
            "🤖 智能形态诊断",
            "🧠 AI 投资助手",
            "ℹ️ 帮助与说明"
        ],
        index=0
    )

    st.markdown("---")
    st.markdown("#### ⚙️ 图表偏好设置")
    color_pref = st.selectbox(
        "涨跌颜色习惯",
        ["A股 (红涨绿跌)", "国际 (绿涨红跌)"],
        index=0
    )
    chart_theme = st.selectbox(
        "图表主题风格",
        ["dark (科技黑)", "light (专业白)"],
        index=0
    )
    theme_val = "dark" if "dark" in chart_theme else "light"

    st.markdown("---")
    # 侧边栏快速自选股小组件 (实时动态同步)
    st.markdown("#### ⭐ **我的自选标的快速跳转**")
    side_wl_items = watchlist_mgr.get_items()
    if side_wl_items:
        side_symbols = [it["symbol"].strip().upper() for it in side_wl_items]
        side_item_map = {it["symbol"].strip().upper(): it for it in side_wl_items}
        current_symbol = st.session_state.current_symbol.upper()
        if current_symbol in side_item_map:
            # This runs before the selectbox is instantiated, so external button
            # selections can update its display without triggering its callback.
            st.session_state[SIDEBAR_SYMBOL_KEY] = current_symbol
        elif st.session_state.get(SIDEBAR_SYMBOL_KEY) not in side_item_map:
            st.session_state[SIDEBAR_SYMBOL_KEY] = side_symbols[0]

        def select_symbol_from_sidebar() -> None:
            selected = st.session_state[SIDEBAR_SYMBOL_KEY]
            item = side_item_map[selected]
            select_current_symbol(selected, item.get("market"))

        st.selectbox(
            "选择自选股",
            options=side_symbols,
            key=SIDEBAR_SYMBOL_KEY,
            format_func=lambda symbol: (
                f"{symbol} - {side_item_map[symbol].get('name', '')} "
                f"({side_item_map[symbol].get('market', '')})"
            ),
            on_change=select_symbol_from_sidebar,
            label_visibility="collapsed"
        )
    else:
        st.caption("暂无自选股，可在「⭐ 自选股与组合」页面添加。")

    st.markdown("---")
    st.caption("💡 提示：支持直接输入美股代码 (如 `NVDA`、`AAPL`)、A股代码 (`600519`) 或 ETF (`510300`)。")


# -------------------------------------------------------------
# 页面 1：📈 个股深度走势看板
# -------------------------------------------------------------
if nav_option == "📈 个股深度走势":
    st.markdown("<div class='main-title'>📈 个股深度走势与技术指标看板</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-title'>支持多市场（A股/美股/ETF）多周期 K 线、主副图技术指标自由叠加与区间量价分析</div>", unsafe_allow_html=True)

    # 1. 动态自选股快速切换栏 (实时同步最新添加/删除的自选股)
    wl_all_items = watchlist_mgr.get_items()
    st.markdown("**⭐ 我的自选股快速切换 (实时联动)：**")
    if wl_all_items:
        display_wl = wl_all_items[:12]
        cols_count = min(len(display_wl), 6)
        wl_cols = st.columns(cols_count)
        for idx, it in enumerate(display_wl):
            col_idx = idx % cols_count
            with wl_cols[col_idx]:
                sym = it["symbol"]
                name = it.get("name", sym)
                mkt = it.get("market", adapter.detect_market(sym))
                is_active = (sym.upper() == st.session_state.current_symbol.upper())
                btn_label = f"🔥 {name}" if is_active else f"{name}"
                btn_type = "primary" if is_active else "secondary"
                st.button(
                    btn_label,
                    key=f"wl_btn_{sym}_{idx}",
                    type=btn_type,
                    use_container_width=True,
                    on_click=select_current_symbol,
                    args=(sym, mkt),
                )
    else:
        st.info("💡 您的自选股池目前为空。可以在下方输入代码并点击「⭐ 加入自选」，或前往「⭐ 自选股与组合」页面添加。")

    # 市场热门参考标的折叠栏
    with st.expander("🌐 **浏览/快速点选市场热门参考标的 (A股 · 美股 · ETF)**", expanded=False):
        pop_cols = st.columns(9)
        popular_picks = [
            ("NVDA", "英伟达", "美股"),
            ("AAPL", "苹果", "美股"),
            ("TSLA", "特斯拉", "美股"),
            ("BABA", "阿里巴巴", "美股"),
            ("600519", "贵州茅台", "A股"),
            ("300750", "宁德时代", "A股"),
            ("002594", "比亚迪", "A股"),
            ("510300", "沪深300", "ETF"),
            ("513100", "纳指ETF", "ETF")
        ]
        for idx, (sym, name, mkt) in enumerate(popular_picks):
            with pop_cols[idx]:
                st.button(
                    f"{name}",
                    key=f"pop_{sym}",
                    use_container_width=True,
                    on_click=select_current_symbol,
                    args=(sym, mkt),
                )

    # 2. 搜索与控制栏
    search_col1, search_col2, search_col3, search_col4 = st.columns([2.2, 1.2, 1.2, 1.8])
    with search_col1:
        if SYMBOL_SEARCH_KEY not in st.session_state:
            st.session_state[SYMBOL_SEARCH_KEY] = st.session_state.current_symbol
        st.text_input(
            "🔍 搜索或输入股票代码/名称",
            key=SYMBOL_SEARCH_KEY,
            on_change=select_symbol_from_search,
        )

    curr_sym = st.session_state.current_symbol
    curr_mkt = st.session_state.current_market
    is_in_watchlist = watchlist_mgr.has_stock(curr_sym)

    with search_col2:
        period_choice = st.selectbox("K线周期", ["日K (Daily)", "周K (Weekly)", "月K (Monthly)"], index=0)
        period_code = "daily" if "日K" in period_choice else ("weekly" if "周K" in period_choice else "monthly")

    with search_col3:
        range_choice = st.selectbox("时间范围", ["近3个月", "近半年", "近1年", "近3年", "全部数据"], index=2)
        limit_map = {"近3个月": 65, "近半年": 130, "近1年": 260, "近3年": 750, "全部数据": 1200}
        kline_limit = limit_map[range_choice]

    # 获取最新行情
    quote = adapter.get_realtime_quote(curr_sym, curr_mkt)

    with search_col4:
        st.write("")
        st.write("")
        act_col1, act_col2 = st.columns(2)
        with act_col1:
            if is_in_watchlist:
                if st.button("✏️ 更新自选", key="btn_update_wl", use_container_width=True):
                    existing_stock = watchlist_mgr.get_stock(curr_sym) or {}
                    watchlist_mgr.add_stock(
                        symbol=curr_sym,
                        name=quote.get("name", curr_sym),
                        market=curr_mkt,
                        group=existing_stock.get("group", "全部"),
                        cost_price=existing_stock.get("cost_price", 0.0),
                        shares=existing_stock.get("shares", 0.0),
                        note=existing_stock.get("note", ""),
                    )
                    st.toast(f"✅ 已刷新 {curr_sym} 的名称与市场信息，持仓数据保持不变！", icon="⭐")
                    st.rerun()
            else:
                if st.button("⭐ 加入自选", key="btn_add_wl", type="primary", use_container_width=True):
                    watchlist_mgr.add_stock(
                        symbol=curr_sym,
                        name=quote.get("name", curr_sym),
                        market=curr_mkt,
                        cost_price=quote.get("price", 0.0),
                        note="看板快速添加"
                    )
                    st.toast(f"✅ 已成功将 {quote.get('name', curr_sym)} ({curr_sym}) 加入自选！", icon="⭐")
                    st.rerun()

        with act_col2:
            if is_in_watchlist:
                if st.button("🗑️ 移出自选", key="btn_del_wl", type="secondary", use_container_width=True):
                    watchlist_mgr.remove_stock(curr_sym)
                    st.toast(f"🗑️ 已将 {curr_sym} 从自选股中移除！", icon="🗑️")
                    st.rerun()
            else:
                if st.button("🤖 智能诊断", key="btn_goto_diag", use_container_width=True):
                    st.session_state.current_symbol = curr_sym
                    st.toast("💡 可在左侧导航栏切换至「🤖 智能形态诊断」查看完整报告！", icon="🤖")

    # 3. 核心行情指标卡片横幅
    m_col1, m_col2, m_col3, m_col4, m_col5, m_col6 = st.columns(6)
    pct_chg = quote.get("pct_chg", 0.0)
    chg_val = quote.get("change", 0.0)
    price_color_cls = "up-tag" if pct_chg >= 0 else "down-tag"
    chg_sign = "+" if pct_chg > 0 else ""
    wl_badge = " [⭐已在自选]" if is_in_watchlist else ""

    with m_col1:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>{quote.get('name', curr_sym)} ({curr_sym}) · {curr_mkt}{wl_badge}</div>
            <div class='metric-value {price_color_cls}'>{quote.get('price', 0.0):.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    with m_col2:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>今日涨跌幅</div>
            <div class='metric-value {price_color_cls}'>{chg_sign}{pct_chg:.2f}%</div>
        </div>
        """, unsafe_allow_html=True)

    with m_col3:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>今日涨跌额</div>
            <div class='metric-value {price_color_cls}'>{chg_sign}{chg_val:.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    with m_col4:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>最高 / 最低</div>
            <div class='metric-value' style='font-size:16px; color:#475569;'>{quote.get('high', 0.0):.2f} / {quote.get('low', 0.0):.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    with m_col5:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>今开 / 昨收</div>
            <div class='metric-value' style='font-size:16px; color:#475569;'>{quote.get('open', 0.0):.2f} / {quote.get('prev_close', 0.0):.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    with m_col6:
        turnover_text = f"{quote.get('turnover', 0.0):.2f}%" if quote.get('turnover') else "--"
        pe_text = f"{quote.get('pe', 0.0):.1f}" if quote.get('pe') else "--"
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>换手率 / 市盈率PE</div>
            <div class='metric-value' style='font-size:16px; color:#475569;'>{turnover_text} / {pe_text}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 指标勾选控制条
    ctl_col1, ctl_col2 = st.columns([3, 1])
    with ctl_col1:
        main_inds = st.multiselect(
            "主图叠加技术指标",
            ["MA5", "MA10", "MA20", "MA60", "MA120", "MA250", "BOLL", "EMA12", "EMA26"],
            default=["MA5", "MA10", "MA20", "MA60", "BOLL"]
        )
    with ctl_col2:
        sub_ind = st.selectbox("副图技术指标", ["MACD", "KDJ", "RSI", "ATR"], index=0)

    # 拉取 K 线数据并计算指标
    with st.spinner("正在加载K线与技术指标数据..."):
        k_df = adapter.get_kline_data(curr_sym, curr_mkt, period=period_code, limit=kline_limit)
        k_df = add_all_indicators(k_df)

    if k_df is not None and not k_df.empty:
        # 绘制专业 Plotly 图表
        fig = create_stock_chart(
            df=k_df,
            title=f"{quote.get('name', curr_sym)} ({curr_sym})",
            color_convention=color_pref,
            main_indicators=main_inds,
            sub_indicator=sub_ind,
            theme=theme_val
        )
        st.plotly_chart(fig, use_container_width=True)

        # 底部简版形态诊断卡片
        diag = analyzer.analyze(k_df, quote)
        st.markdown("#### 🤖 技术形态快览与支撑阻力")
        d_col1, d_col2 = st.columns([1.5, 2.5])
        with d_col1:
            st.metric(label="技术健康度评分 (0-100)", value=f"{diag['score']} 分", delta=diag["status"])
            st.caption(f"当前技术状态：**{diag['status']}**")
            
            res_str = " / ".join([f"{r:.2f}" for r in diag["resistance_levels"]]) if diag["resistance_levels"] else "暂无强压力"
            sup_str = " / ".join([f"{s:.2f}" for s in diag["support_levels"]]) if diag["support_levels"] else "暂无强支撑"
            st.write(f"🛑 **预估阻力位**：`{res_str}`")
            st.write(f"🛡️ **预估支撑位**：`{sup_str}`")

        with d_col2:
            st.write("**形态信号检测：**")
            for sig in diag["signals"]:
                pill_class = f"signal-pill-{sig['type']}"
                st.markdown(f"<span class='{pill_class}'>{sig['tag']}</span> {sig['desc']}", unsafe_allow_html=True)
            st.info(f"💡 **操盘建议参考**：{diag['summary']}")

    else:
        st.warning(f"未能获取到标的 `{curr_sym}` 的历史行情数据，请检查代码拼写或网络连接。")


# -------------------------------------------------------------
# 页面 2：🔍 多维策略智能选股
# -------------------------------------------------------------
elif nav_option == "🔍 多维策略选股":
    st.markdown("<div class='main-title'>🔍 多维自定义智能选股器</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-title'>支持按财务指标、行情异动及经典技术形态（均线多头/MACD金叉/放量突破）跨市场实时选股</div>", unsafe_allow_html=True)

    with st.expander("🛠️ **选股策略与筛选条件配置面板**", expanded=True):
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            screener_market = st.selectbox("选股标的池市场", ["A股", "美股", "ETF"], index=0)
            screener_preset = st.selectbox(
                "预置量化/形态策略",
                ["全部候选", "均线多头精选", "MACD金叉反弹", "放量突破", "低估值蓝筹"],
                index=0
            )

        with f_col2:
            price_min, price_max = st.slider("股价区间 (元/$)", 0.0, 500.0, (0.0, 500.0), step=1.0)
            chg_min, chg_max = st.slider("今日涨跌幅区间 (%)", -15.0, 20.0, (-10.0, 15.0), step=0.5)

        with f_col3:
            pe_max = st.slider("市盈率 PE 上限 (0为不限)", 0, 200, 100, step=5)
            pe_upper = 500.0 if pe_max == 0 else float(pe_max)
            mktcap_min = st.slider("市值门槛 (亿元)", 0, 500, 0, step=10)

    # 运行选股按钮
    if st.button("🚀 执行策略筛选", type="primary", use_container_width=True):
        with st.spinner("正在多维扫描市场数据与形态结构..."):
            res_df = screener.screen(
                market_type=screener_market,
                preset_strategy=screener_preset,
                min_price=price_min,
                max_price=price_max,
                min_pct_chg=chg_min,
                max_pct_chg=chg_max,
                min_pe=0.0,
                max_pe=pe_upper,
                min_mktcap=float(mktcap_min)
            )
            st.session_state.screener_results = res_df

    if "screener_results" in st.session_state and not st.session_state.screener_results.empty:
        results = st.session_state.screener_results
        st.success(f"🎉 筛选完成！共命中 **{len(results)}** 只符合条件的标的：")

        # 导出工具条
        exp_col1, exp_col2, _ = st.columns([1.2, 1.2, 3])
        with exp_col1:
            excel_data = screener.export_to_excel(results)
            st.download_button(
                label="📥 导出 Excel 表格",
                data=excel_data,
                file_name=f"选股结果_{datetime.date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        with exp_col2:
            csv_data = screener.export_to_csv(results)
            st.download_button(
                label="📥 导出 CSV 文本",
                data=csv_data,
                file_name=f"选股结果_{datetime.date.today()}.csv",
                mime="text/csv",
                use_container_width=True
            )

        # 格式化表格显示
        display_df = results.copy()
        if "pct_chg" in display_df.columns:
            display_df["涨跌幅"] = display_df["pct_chg"].apply(lambda x: f"{x:+.2f}%")
        if "price" in display_df.columns:
            display_df["最新价"] = display_df["price"].apply(lambda x: f"{x:.2f}")
        if "pe" in display_df.columns:
            display_df["市盈率PE"] = display_df["pe"].apply(lambda x: f"{x:.1f}" if x > 0 else "--")
        if "mktcap" in display_df.columns:
            display_df["总市值(亿)"] = display_df["mktcap"].apply(lambda x: f"{x:.1f}" if x > 0 else "--")

        col_order = ["symbol", "name", "market", "最新价", "涨跌幅", "市盈率PE", "总市值(亿)"]
        valid_cols = [c for c in col_order if c in display_df.columns]
        
        st.dataframe(display_df[valid_cols].rename(columns={"symbol": "代码", "name": "名称", "market": "市场"}), use_container_width=True)

    elif "screener_results" in st.session_state:
        st.info("💡 未找到符合当前严苛条件的标的，请适当放宽价格、市盈率或涨跌幅范围重新筛选。")
    else:
        st.info("👆 请配置上方的筛选条件并点击「执行策略筛选」开始选股。")


# -------------------------------------------------------------
# 页面 3：⭐ 跨市场自选股与组合管理
# -------------------------------------------------------------
elif nav_option == "⭐ 自选股与组合":
    st.markdown(
        """
        <style>
            [data-testid="stMain"] .main-title { font-size: 34px; }
            [data-testid="stMain"] .sub-title { font-size: 18px; }
            [data-testid="stMain"] .metric-card { padding: 16px 18px; }
            [data-testid="stMain"] .metric-label { font-size: 16px; }
            [data-testid="stMain"] .metric-value { font-size: 26px; }
            [data-testid="stMain"] [data-testid="stWidgetLabel"] p,
            [data-testid="stMain"] [data-testid="stCaptionContainer"] p,
            [data-testid="stMain"] .stMarkdown p,
            [data-testid="stMain"] .stButton button p,
            [data-testid="stMain"] .stDownloadButton button p,
            [data-testid="stMain"] .stFormSubmitButton button p,
            [data-testid="stMain"] [data-testid="stRadio"] label p,
            [data-testid="stMain"] [data-testid="stCheckbox"] label p,
            [data-testid="stMain"] [data-baseweb="select"] span {
                font-size: 18px !important;
            }
            [data-testid="stMain"] .stButton button,
            [data-testid="stMain"] .stDownloadButton button,
            [data-testid="stMain"] .stFormSubmitButton button,
            [data-testid="stMain"] [data-baseweb="input"],
            [data-testid="stMain"] [data-baseweb="select"] > div {
                min-height: 3rem;
            }
            [data-testid="stMain"] input,
            [data-testid="stMain"] textarea {
                font-size: 18px !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div class='main-title'>⭐ 跨市场自选股与组合追踪</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-title'>本地持久化安全存储，支持 A股、美股、ETF 混合持仓管理、实时刷新与浮动盈亏测算</div>", unsafe_allow_html=True)

    if getattr(watchlist_mgr, "persistence_mode", "local") == "cloud":
        remote_error = getattr(watchlist_mgr, "remote_error", "")
        if remote_error:
            st.warning(f"☁️ 云端数据暂时无法同步，当前使用本地缓存：{remote_error}")
        else:
            st.caption("☁️ 持仓、自选分组和排序已启用云端持久化。")
    elif cloud_config_incomplete:
        st.warning("云端存储配置不完整，当前暂时使用本地数据。")

    quick_hide_notice = st.session_state.pop("portfolio_quick_hide_notice", None)
    if quick_hide_notice:
        st.toast(quick_hide_notice, icon="🙈")

    groups = watchlist_mgr.get_groups()
    group_col, currency_col, rate_col = st.columns([2.2, 1.2, 1.2])
    with group_col:
        selected_group = st.selectbox(
            "📁 选择自选分组",
            ["全部"] + [g for g in groups if g != "全部"],
            index=0,
        )
    with currency_col:
        display_currency = st.radio(
            "💱 组合显示币种",
            ["人民币 CNY", "美元 USD"],
            horizontal=True,
        )
    with rate_col:
        automatic_usd_cny_rate = get_usd_cny_reference_rate()
        usd_cny_rate = st.number_input(
            "USD/CNY 参考汇率",
            min_value=1.0,
            max_value=20.0,
            value=automatic_usd_cny_rate,
            step=0.0001,
            format="%.6f",
            help="自动获取参考汇率，也可以手动调整；表示 1 美元可兑换多少人民币。",
        )
        rate_source = getattr(adapter, "usd_cny_rate_source", "内置参考（2026-08-30）")
        st.caption(f"汇率来源：{rate_source}；1 USD ≈ {automatic_usd_cny_rate:.6f} CNY")

    if st.button("🔄 立即刷新行情", key="refresh_portfolio_quotes"):
        clear_quote_cache = getattr(adapter, "clear_quote_cache", None)
        if callable(clear_quote_cache):
            clear_quote_cache()
        st.toast("正在重新获取最新行情。", icon="🔄")

    with st.expander("📁 自定义分组管理", expanded=False):
        create_group_col, rename_group_col = st.columns(2)
        with create_group_col:
            with st.form("create_watchlist_group_form", clear_on_submit=True):
                st.markdown("**新建分组**")
                new_group_name = st.text_input(
                    "分组名称",
                    max_chars=30,
                    placeholder="例如：AI 核心、短线观察",
                )
                create_group_submitted = st.form_submit_button(
                    "➕ 创建分组",
                    use_container_width=True,
                )
                if create_group_submitted:
                    if watchlist_mgr.add_group(new_group_name):
                        st.success(f"已创建分组「{new_group_name.strip()}」。")
                        st.rerun()
                    else:
                        st.warning("分组名称不能为空或已存在。")

        with rename_group_col:
            custom_groups = [group for group in groups if group != "全部"]
            if custom_groups:
                with st.form("rename_watchlist_group_form", clear_on_submit=True):
                    st.markdown("**重命名分组**")
                    group_to_rename = st.selectbox("选择分组", custom_groups)
                    renamed_group_name = st.text_input(
                        "新的分组名称",
                        max_chars=30,
                        placeholder="输入新名称",
                    )
                    rename_group_submitted = st.form_submit_button(
                        "✏️ 确认重命名",
                        use_container_width=True,
                    )
                    if rename_group_submitted:
                        if rename_watchlist_group(group_to_rename, renamed_group_name):
                            st.success(
                                f"已将分组「{group_to_rename}」重命名为「{renamed_group_name.strip()}」。"
                            )
                            st.rerun()
                        else:
                            st.warning("新名称不能为空、已存在，或该分组不可重命名。")
            else:
                st.info("创建第一个自定义分组后，可在这里重命名。")

    display_in_cny = display_currency == "人民币 CNY"
    display_currency_code = "CNY" if display_in_cny else "USD"
    display_currency_symbol = "¥" if display_in_cny else "$"

    def convert_position_currency(amount: float, market: str) -> float:
        """Convert a position amount from its market currency to the selected display currency."""
        amount = float(amount or 0.0)
        is_us_market = market == "美股"
        if display_in_cny:
            return amount * usd_cny_rate if is_us_market else amount
        return amount if is_us_market else amount / usd_cny_rate

    # 获取当前分组，并将隐藏标的排除在组合列表及汇总指标之外
    all_group_items = watchlist_mgr.get_items(group=selected_group)
    hidden_items = [item for item in all_group_items if item.get("hidden_from_portfolio", False)]
    items = [item for item in all_group_items if not item.get("hidden_from_portfolio", False)]

    if hidden_items:
        hidden_symbols = [item["symbol"] for item in hidden_items]
        restore_label = (
            f"👁️ 一键恢复当前分组全部隐藏（{len(hidden_items)} 只）"
        )
        if st.button(
            restore_label,
            key=f"quick_restore_all_{selected_group}",
            type="primary",
            use_container_width=True,
        ):
            restored_count = set_watchlist_symbols_hidden(hidden_symbols, hidden=False)
            st.session_state["portfolio_quick_hide_notice"] = (
                f"已恢复 {restored_count} 只股票，组合指标已重新计算。"
            )
            st.rerun()

    with st.expander(
        f"🙈 批量隐藏与恢复（已隐藏 {len(hidden_items)} 只）",
        expanded=False,
    ):
        st.caption("隐藏不会删除自选股；被隐藏标的不参与下方市值、盈亏、收益率和数量统计。")
        hide_col, restore_col = st.columns(2)

        with hide_col:
            st.markdown("**批量隐藏当前显示的股票**")
            visible_label_map = {
                f"{item['symbol']} - {item.get('name', item['symbol'])}": item["symbol"]
                for item in items
            }
            selected_to_hide = st.multiselect(
                "选择需要隐藏的股票",
                options=list(visible_label_map),
                key=f"hide_watchlist_{selected_group}_{len(items)}",
                placeholder="可多选",
            )
            if st.button(
                f"🙈 隐藏选中的 {len(selected_to_hide)} 只",
                key=f"apply_hide_watchlist_{selected_group}",
                disabled=not selected_to_hide,
                use_container_width=True,
            ):
                hidden_count = set_watchlist_symbols_hidden(
                    [visible_label_map[label] for label in selected_to_hide],
                    hidden=True,
                )
                st.success(f"已隐藏 {hidden_count} 只股票，组合指标已按剩余股票重新计算。")
                st.rerun()

        with restore_col:
            st.markdown("**批量恢复已隐藏的股票**")
            hidden_label_map = {
                f"{item['symbol']} - {item.get('name', item['symbol'])}": item["symbol"]
                for item in hidden_items
            }
            selected_to_restore = st.multiselect(
                "选择需要恢复的股票",
                options=list(hidden_label_map),
                key=f"restore_watchlist_{selected_group}_{len(hidden_items)}",
                placeholder="可多选",
            )
            if st.button(
                f"👁️ 恢复选中的 {len(selected_to_restore)} 只",
                key=f"apply_restore_watchlist_{selected_group}",
                disabled=not selected_to_restore,
                use_container_width=True,
            ):
                restored_count = set_watchlist_symbols_hidden(
                    [hidden_label_map[label] for label in selected_to_restore],
                    hidden=False,
                )
                st.success(f"已恢复 {restored_count} 只股票，组合指标已重新计算。")
                st.rerun()

    # 批量拉取实时行情并计算组合盈亏
    enriched_items = []
    total_val = 0.0
    total_cost = 0.0
    total_day_gain = 0.0
    active_position_count = sum(has_active_position(item) for item in items)

    if items:
        quotes = adapter.get_batch_quotes(items)
        for it, q in zip(items, quotes):
            curr_p = q.get("price", 0.0)
            cost_p = it.get("cost_price", 0.0)
            shares = it.get("shares", 0.0)
            pct_chg = q.get("pct_chg", 0.0)
            item_market = it.get("market", "A股")

            local_mkt_val = curr_p * shares
            local_cost_val = cost_p * shares
            mkt_val = convert_position_currency(local_mkt_val, item_market)
            cost_val = convert_position_currency(local_cost_val, item_market)
            profit_val = mkt_val - cost_val if (cost_p > 0 and shares > 0) else 0.0
            profit_pct = (profit_val / cost_val * 100) if cost_val > 0 else 0.0

            total_val += mkt_val
            total_cost += cost_val

            enriched_items.append({
                "代码": it["symbol"],
                "名称": it.get("name", q.get("name", it["symbol"])),
                "市场": item_market,
                "原币": "USD" if item_market == "美股" else "CNY",
                "分组": it.get("group", "默认"),
                "状态": "持仓" if has_active_position(it) else "自选观察",
                "现价": curr_p,
                "今日涨跌": f"{pct_chg:+.2f}%",
                "行情时段": q.get("session", "未知"),
                "行情时间": q.get("time", ""),
                "行情源": q.get("source", "未知"),
                "持仓成本": cost_p,
                "持仓数量": shares,
                f"持仓市值({display_currency_code})": round(mkt_val, 2),
                f"浮动盈亏({display_currency_code})": round(profit_val, 2),
                "盈亏比例": f"{profit_pct:+.2f}%",
                "备注": it.get("note", "")
            })

    # 资产概览卡片
    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    total_profit = total_val - total_cost
    total_profit_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0.0
    p_cls = "up-tag" if total_profit >= 0 else "down-tag"

    with p_col1:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>折合{display_currency}总市值</div>
            <div class='metric-value'>{display_currency_symbol}{total_val:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
    with p_col2:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>累计浮动盈亏 ({display_currency_code})</div>
            <div class='metric-value {p_cls}'>{display_currency_symbol}{total_profit:+,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
    with p_col3:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>组合收益率</div>
            <div class='metric-value {p_cls}'>{total_profit_pct:+.2f}%</div>
        </div>
        """, unsafe_allow_html=True)
    with p_col4:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-label'>实际持仓 / 当前自选</div>
            <div class='metric-value' style='color:#3b82f6;'>{active_position_count} / {len(items)} 只</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("美股现价优先采用最新分钟行情，包含盘前/盘后；行情时间与来源可在表格中核对。")

    # 自选股列表表格
    if enriched_items:
        df_wl = pd.DataFrame(enriched_items)
        # Force a floating dtype so Streamlit accepts fractional shares (e.g. 0.5).
        df_wl["持仓成本"] = pd.to_numeric(df_wl["持仓成本"], errors="coerce").fillna(0.0).astype(float)
        df_wl["持仓数量"] = pd.to_numeric(df_wl["持仓数量"], errors="coerce").fillna(0.0).astype(float)
        # The rightmost checkbox remains the one-click hide action.
        df_wl["🙈 快速隐藏"] = False
        original_symbols = df_wl["代码"].astype(str).str.upper().tolist()
        grid_signature = abs(hash(tuple(original_symbols)))

        if AgGrid is None:
            st.error("缺少表格拖拽组件，请运行：pip install -r requirements.txt")
            edited_wl = df_wl.copy()
        else:
            grid_builder = GridOptionsBuilder.from_dataframe(df_wl)
            grid_builder.configure_default_column(
                editable=False,
                sortable=False,
                filter=False,
                resizable=True,
                suppressMovable=True,
            )
            grid_builder.configure_column(
                "代码",
                header_name="↕ 拖动 / 代码",
                rowDrag=True,
                pinned="left",
                width=135,
            )
            grid_builder.configure_column("名称", pinned="left", width=120)
            group_choices = list(
                dict.fromkeys(
                    [str(group) for group in groups]
                    + df_wl["分组"].dropna().astype(str).tolist()
                )
            )
            grid_builder.configure_column(
                "分组",
                editable=True,
                cellEditor="agSelectCellEditor",
                cellEditorParams={"values": group_choices},
                minWidth=120,
            )
            grid_builder.configure_column(
                "持仓成本",
                editable=True,
                type=["numericColumn"],
                cellEditor="agNumberCellEditor",
                cellEditorParams={"min": 0, "step": 0.001, "precision": 3},
                minWidth=110,
            )
            grid_builder.configure_column(
                "持仓数量",
                editable=True,
                type=["numericColumn"],
                cellEditor="agNumberCellEditor",
                cellEditorParams={"min": 0, "step": 0.000000001, "precision": 9},
                minWidth=140,
            )
            grid_builder.configure_column("备注", editable=True, minWidth=150)
            grid_builder.configure_column(
                "🙈 快速隐藏",
                editable=True,
                cellEditor="agCheckboxCellEditor",
                cellRenderer="agCheckboxCellRenderer",
                pinned="right",
                width=125,
            )
            grid_builder.configure_grid_options(
                rowDragManaged=True,
                animateRows=True,
                suppressMoveWhenRowDragging=False,
                suppressRowClickSelection=True,
                ensureDomOrder=True,
                rowHeight=52,
                headerHeight=54,
            )
            grid_response = AgGrid(
                df_wl,
                gridOptions=grid_builder.build(),
                height=min(700, 58 + 52 * len(df_wl)),
                theme="streamlit",
                custom_css={
                    ".ag-root-wrapper": {"font-size": "18px"},
                    ".ag-header-cell-label": {"font-size": "18px"},
                },
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                update_on=["cellValueChanged", "rowDragEnd"],
                server_sync_strategy="client_wins",
                show_search=False,
                show_download_button=False,
                key=f"portfolio_grid_v1_{selected_group}_{grid_signature}",
            )
            edited_wl = pd.DataFrame(grid_response.data).copy()

            hidden_symbols = [
                str(row.get("代码", "")).strip().upper()
                for row in edited_wl.to_dict("records")
                if bool(row.get("🙈 快速隐藏", False))
            ]
            if hidden_symbols:
                hidden_count = set_watchlist_symbols_hidden(hidden_symbols, hidden=True)
                if hidden_count:
                    st.session_state["portfolio_quick_hide_notice"] = (
                        f"已快速隐藏 {hidden_count} 只股票，组合指标已重新计算。"
                    )
                    st.rerun()

            dragged_symbols = edited_wl["代码"].astype(str).str.upper().tolist()
            if dragged_symbols != original_symbols and set(dragged_symbols) == set(original_symbols):
                if reorder_watchlist_symbols(dragged_symbols):
                    st.session_state["portfolio_quick_hide_notice"] = "股票拖拽顺序已自动保存。"
                    st.rerun()

        st.caption(
            "↕️ 第一列可拖动整行；分组、成本、数量和备注可直接编辑并保存；最右侧可快速隐藏。"
        )

        if st.button(
            "💾 保存持仓修改",
            key=f"save_watchlist_positions_{selected_group}",
            type="primary",
            use_container_width=True,
        ):
            original_by_symbol = {item["symbol"].upper(): item for item in items}
            updated_count = 0
            for row in edited_wl.to_dict("records"):
                symbol = str(row["代码"]).strip().upper()
                original = original_by_symbol.get(symbol)
                if original is None:
                    continue

                new_cost = float(row.get("持仓成本", 0.0) or 0.0)
                new_shares = round(float(row.get("持仓数量", 0.0) or 0.0), 9)
                new_note = str(row.get("备注", "") or "").strip()
                new_group = str(row.get("分组", original.get("group", "全部")) or "全部").strip()
                changed = (
                    not np.isclose(new_cost, float(original.get("cost_price", 0.0) or 0.0))
                    or new_shares != round(float(original.get("shares", 0.0) or 0.0), 9)
                    or new_note != str(original.get("note", "") or "").strip()
                    or new_group != str(original.get("group", "全部") or "全部").strip()
                )
                if not changed:
                    continue

                watchlist_mgr.add_stock(
                    symbol=symbol,
                    name=original.get("name", symbol),
                    market=original.get("market", "A股"),
                    group=new_group,
                    cost_price=new_cost,
                    shares=new_shares,
                    note=new_note,
                )
                updated_count += 1

            if updated_count:
                st.success(f"✅ 已保存 {updated_count} 只标的的持仓修改，收益数据已重新计算。")
                st.rerun()
            else:
                st.info("没有检测到需要保存的修改。")
    else:
        if hidden_items:
            st.info("当前分组的股票已全部隐藏，可在上方「批量隐藏与恢复」中恢复显示。")
        else:
            st.info("当前分组暂无自选股，您可以通过下方表单添加。")

    st.markdown("---")
    # 自选股管理面板（双栏：添加标的 vs 批量删除管理）
    mgt_col1, mgt_col2 = st.columns(2)
    with mgt_col1:
        with st.expander("➕ **添加新标的到自选股池**", expanded=True):
            with st.form("add_stock_form", clear_on_submit=True):
                in_sym = st.text_input("股票代码 (如 NVDA, AAPL, 600519, 510300)")
                in_name = st.text_input("股票名称 (可选，留空自动匹配)")
                in_mkt = st.selectbox("所属市场", ["A股", "美股", "ETF"], index=0)
                in_grp = st.selectbox("归属分组", groups)
                in_cost = st.number_input("持仓成本价 (元/$)", value=0.0, min_value=0.0, step=1.0)
                share_step = 0.000000001 if in_mkt == "美股" else 1.0
                share_format = "%.9f" if in_mkt == "美股" else "%.4f"
                in_shares = st.number_input(
                    "持仓数量/股数",
                    value=0.0,
                    min_value=0.0,
                    step=share_step,
                    format=share_format,
                    help="美股支持输入小数点后 9 位的碎股数量",
                )
                in_note = st.text_input("投资笔记/备忘")
                submit_add = st.form_submit_button("确认添加 / 更新", type="primary")
                if submit_add and in_sym:
                    watchlist_mgr.add_stock(
                        symbol=in_sym,
                        name=in_name,
                        market=in_mkt,
                        group=in_grp,
                        cost_price=in_cost,
                        shares=in_shares,
                        note=in_note
                    )
                    st.success(f"✅ 已成功添加/更新标的 {in_sym.upper()}！")
                    st.rerun()

    with mgt_col2:
        with st.expander("🗑️ **批量管理与移除自选股**", expanded=True):
            if items:
                all_option_labels = [f"{it['symbol']} - {it.get('name', '')} ({it.get('market', '')})" for it in items]
                
                # 批量多选
                select_all = st.checkbox("☑️ 全选当前列表中的所有标的")
                default_selected = all_option_labels if select_all else []

                selected_to_delete = st.multiselect(
                    "勾选要移除的股票 (支持多选批量删除)",
                    options=all_option_labels,
                    default=default_selected
                )

                del_col1, del_col2 = st.columns(2)
                with del_col1:
                    if st.button(f"❌ 确认批量删除 ({len(selected_to_delete)} 只)", type="primary", disabled=(len(selected_to_delete) == 0), use_container_width=True):
                        symbols_to_del = [s.split(" - ")[0].strip() for s in selected_to_delete]
                        cnt = watchlist_mgr.remove_stocks(symbols_to_del)
                        st.success(f"✅ 已成功批量移除 {cnt} 只标的！")
                        st.rerun()

                with del_col2:
                    confirm_clear = st.checkbox(f"确认清空「{selected_group}」分组")
                    if st.button("⚠️ 一键清空分组", type="secondary", disabled=not confirm_clear, use_container_width=True):
                        cnt = watchlist_mgr.clear_group(selected_group)
                        st.success(f"已清空该分组中的 {cnt} 只股票！")
                        st.rerun()
            else:
                st.info("当前分组暂无任何股票可供删除。")


# -------------------------------------------------------------
# 页面 4：💰 我的基金（示例数据骨架）
# -------------------------------------------------------------
elif nav_option == "💰 我的基金":
    render_funds_page()


# -------------------------------------------------------------
# 页面 5：🤖 智能形态诊断（Python / Quant 规则引擎）
# -------------------------------------------------------------
elif nav_option == "🤖 智能形态诊断":
    st.markdown("<div class='main-title'>🤖 智能形态诊断与量化技术简报</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub-title'>自动扫描均线排列、量价配合、MACD/KDJ/RSI超买超卖状态，生成结构化技术评级与操作指引</div>", unsafe_allow_html=True)

    # 快捷从自选股或输入代码选择
    d_sel_col1, d_sel_col2 = st.columns([2, 2])
    with d_sel_col1:
        diag_sym = st.text_input("输入待诊断股票代码 (如 AAPL, TSLA, 600519)", value=st.session_state.current_symbol)
    
    with d_sel_col2:
        wl_items_for_diag = watchlist_mgr.get_items()
        if wl_items_for_diag:
            diag_options = ["(从自选股快速选择)"] + [f"{it['symbol']} - {it.get('name', '')}" for it in wl_items_for_diag]
            selected_wl_diag = st.selectbox("🎯 或从自选股直接点选", diag_options, index=0)
            if selected_wl_diag and selected_wl_diag != "(从自选股快速选择)":
                pick_sym = selected_wl_diag.split(" - ")[0].strip().upper()
                if pick_sym != diag_sym:
                    diag_sym = pick_sym
                    st.session_state.current_symbol = diag_sym

    diag_mkt = adapter.detect_market(diag_sym)

    with st.spinner("正在进行多维度技术形态扫描..."):
        diag_k = adapter.get_kline_data(diag_sym, diag_mkt, limit=120)
        diag_k = add_all_indicators(diag_k)
        quote_info = adapter.get_realtime_quote(diag_sym, diag_mkt)

    if diag_k is not None and not diag_k.empty:
        report = analyzer.analyze(diag_k, quote_info)

        # 核心评级大卡片
        score_val = report["score"]
        score_color = "#ef4444" if score_val >= 70 else ("#f59e0b" if score_val >= 50 else "#22c55e")
        
        st.markdown(f"""
        <div style='background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); color: white; padding: 24px; border-radius: 12px; margin-bottom: 20px;'>
            <div style='display: flex; justify-content: space-between; align-items: center;'>
                <div>
                    <h2 style='margin:0; color: white;'>{quote_info.get('name', diag_sym)} ({diag_sym}) · {diag_mkt}</h2>
                    <p style='color: #94a3b8; margin: 4px 0 0 0;'>现价：{quote_info.get('price', 0.0):.2f} | 涨跌幅：{quote_info.get('pct_chg', 0.0):+.2f}%</p>
                </div>
                <div style='text-align: right;'>
                    <div style='font-size: 32px; font-weight: 800; color: {score_color};'>{score_val} <span style='font-size:16px;'>分</span></div>
                    <div style='font-size: 14px; font-weight: 600; color: #cbd5e1;'>{report['status']}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_left, col_right = st.columns([1.5, 1])
        with col_left:
            st.markdown("#### 📑 逐项指标技术诊断报告")
            for sig in report["signals"]:
                p_cls = f"signal-pill-{sig['type']}"
                st.markdown(f"""
                <div style='margin-bottom: 12px; padding: 10px 14px; background: #f8fafc; border-left: 4px solid {score_color}; border-radius: 4px;'>
                    <span class='{p_cls}'>{sig['tag']}</span>
                    <span style='color: #334155; font-size: 14px;'>{sig['desc']}</span>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("#### 💡 操盘策略与风险提示")
            st.info(report["summary"])

        with col_right:
            st.markdown("#### 🎯 关键技术阻力位与支撑位")
            res_list = report.get("resistance_levels", [])
            sup_list = report.get("support_levels", [])

            st.markdown("**🛑 阻力位（上行目标/压力）：**")
            if res_list:
                for idx, r in enumerate(res_list):
                    st.warning(f"阻力位 {idx+1}：**{r:.2f}** (距现价 {(r - report['latest_close'])/report['latest_close']*100:+.1f}%)")
            else:
                st.write("已创出近期新高，上方处于历史无套牢盘真空区。")

            st.markdown("**🛡️ 支撑位（防守底线/回踩）：**")
            if sup_list:
                for idx, s in enumerate(sup_list):
                    st.success(f"支撑位 {idx+1}：**{s:.2f}** (距现价 {(s - report['latest_close'])/report['latest_close']*100:+.1f}%)")
            else:
                st.write("未检测到密集均线支撑。")

    else:
        st.error(f"无法获取 `{diag_sym}` 的有效数据进行诊断。")


# -------------------------------------------------------------
# 页面 6：🧠 AI 投资助手（LLM 占位接口）
# -------------------------------------------------------------
elif nav_option == "🧠 AI 投资助手":
    render_ai_copilot_page()


# -------------------------------------------------------------
# 页面 7：ℹ️ 帮助与说明
# -------------------------------------------------------------
elif nav_option == "ℹ️ 帮助与说明":
    st.markdown("<div class='main-title'>ℹ️ 系统架构说明与使用指南</div>", unsafe_allow_html=True)
    st.markdown("""
    ### 🌟 系统特色与功能架构
    
    1. **多市场统一数据引擎**：
       - **美股**：直连纳斯达克、纽交所行情，支持 `AAPL`、`NVDA`、`TSLA`、`BABA` 等中概及科技巨头历史全量日K与实时报价。
       - **A股**：支持沪深京所有A股代码，自动计算前复权 (QFQ) 价格与均线簇。
       - **ETF基金**：覆盖沪深300、科创50、纳指ETF、黄金ETF等核心宽基与行业ETF。
    
    2. **专业级交互金融图表**：
       - 基于 **Plotly Graph Objects** 深度构建，支持十字光标、自由缩放平移、红绿涨跌风格切换。
       - 包含 **MA5/10/20/60/120/250**、**BOLL布林带**、**EMA**、**MACD**、**KDJ**、**RSI**、**ATR** 等全套经典量化指标。
    
    3. **多维策略选股器**：
       - 支持按股价区间、涨跌幅、市盈率、市值门槛以及“均线多头”、“MACD金叉”、“放量突破”等典型技术形态快速筛选。
       - 支持一键导出筛选结果为 **Excel** 或 **CSV**。
    
    4. **跨市场混合自选池**：
       - 支持将 A股、美股与 ETF 集中在同一个看板进行跟踪，实时试算持仓浮动盈亏。
       - 本地模式保存到 `data/watchlist.json`；配置 Supabase 后会自动切换为云端持久化，并保留本地缓存。
    
    5. **智能形态诊断**：
       - 自动根据均线排列、量价结构、超买超卖状态计算技术健康度评分，并预估关键支撑与阻力位。
    """)
