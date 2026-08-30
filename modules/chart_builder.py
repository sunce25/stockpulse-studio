# -*- coding: utf-8 -*-
"""
Interactive Financial Chart Builder using Plotly for StockPulse Studio.
Builds multi-pane Candlestick, Moving Averages, Bollinger Bands, Volume, and Sub-indicators.
"""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def create_stock_chart(
    df: pd.DataFrame,
    title: str = "股票走势图",
    color_convention: str = "A股 (红涨绿跌)",
    main_indicators: list = ["MA5", "MA10", "MA20", "MA60", "BOLL"],
    sub_indicator: str = "MACD",
    theme: str = "dark"
) -> go.Figure:
    """
    构建多副图联动的专业股票走势图
    """
    if df is None or df.empty or len(df) < 2:
        fig = go.Figure()
        fig.add_annotation(text="暂无可用的历史K线数据", showarrow=False, font=dict(size=18, color="#888"))
        return fig

    # 1. 颜色方案配置
    if "红涨绿跌" in color_convention:
        color_up = "#ef4444"    # 红
        color_down = "#22c55e"  # 绿
    else:
        color_up = "#22c55e"    # 绿
        color_down = "#ef4444"  # 红

    bg_color = "#131722" if theme == "dark" else "#ffffff"
    grid_color = "#2a2e39" if theme == "dark" else "#f0f3f6"
    text_color = "#d1d5db" if theme == "dark" else "#1f2937"

    # 2. 确定子图行数与高度分配
    # Row 1: 主图K线 (0.55)
    # Row 2: 成交量 (0.18)
    # Row 3: 副图指标 (0.27)
    row_heights = [0.55, 0.18, 0.27]
    subplot_titles = [f"{title} - 价格走势", "成交量 (Volume)", f"副图技术指标 - {sub_indicator}"]

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=row_heights,
        subplot_titles=subplot_titles
    )

    # 3. 主图：K线 (Candlestick)
    candlestick = go.Candlestick(
        x=df["date"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="K线",
        increasing_line_color=color_up,
        increasing_fillcolor=color_up,
        decreasing_line_color=color_down,
        decreasing_fillcolor=color_down,
        hoverinfo="all",
        showlegend=False
    )
    fig.add_trace(candlestick, row=1, col=1)

    # 4. 主图叠加指标
    ma_palette = {
        "MA5": ("MA_5", "#f59e0b", "MA5"),
        "MA10": ("MA_10", "#8b5cf6", "MA10"),
        "MA20": ("MA_20", "#3b82f6", "MA20"),
        "MA60": ("MA_60", "#ec4899", "MA60"),
        "MA120": ("MA_120", "#06b6d4", "MA120"),
        "MA250": ("MA_250", "#10b981", "MA250"),
        "EMA12": ("EMA_12", "#f97316", "EMA12"),
        "EMA26": ("EMA_26", "#a855f7", "EMA26")
    }

    for ind in main_indicators:
        if ind in ma_palette:
            col, line_color, lbl = ma_palette[ind]
            if col in df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df["date"],
                        y=df[col],
                        mode="lines",
                        name=lbl,
                        line=dict(color=line_color, width=1.3),
                        hoverinfo="name+y"
                    ),
                    row=1, col=1
                )

    # 布林带 (BOLL)
    if "BOLL" in main_indicators and "BOLL_MID" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["BOLL_UP"],
                mode="lines",
                name="BOLL上轨",
                line=dict(color="#64748b", width=1, dash="dot"),
                hoverinfo="name+y"
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["BOLL_MID"],
                mode="lines",
                name="BOLL中轨",
                line=dict(color="#94a3b8", width=1.2),
                hoverinfo="name+y"
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["BOLL_DOWN"],
                mode="lines",
                name="BOLL下轨",
                fill="tonexty",
                fillcolor="rgba(148, 163, 184, 0.05)",
                line=dict(color="#64748b", width=1, dash="dot"),
                hoverinfo="name+y"
            ),
            row=1, col=1
        )

    # 标注最高与最低价
    max_idx = df["high"].idxmax()
    min_idx = df["low"].idxmin()
    if pd.notna(max_idx) and pd.notna(min_idx):
        max_row = df.loc[max_idx]
        min_row = df.loc[min_idx]
        fig.add_annotation(
            x=max_row["date"],
            y=max_row["high"],
            text=f"最高: {max_row['high']:.2f}",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowcolor=color_up,
            font=dict(color=color_up, size=11),
            row=1, col=1
        )
        fig.add_annotation(
            x=min_row["date"],
            y=min_row["low"],
            text=f"最低: {min_row['low']:.2f}",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowcolor=color_down,
            font=dict(color=color_down, size=11),
            ay=30,
            row=1, col=1
        )

    # 5. Row 2: 成交量柱状图
    vol_colors = [
        color_up if c >= o else color_down
        for c, o in zip(df["close"], df["open"])
    ]
    fig.add_trace(
        go.Bar(
            x=df["date"],
            y=df["volume"],
            name="成交量",
            marker=dict(color=vol_colors, opacity=0.85),
            hoverinfo="x+y"
        ),
        row=2, col=1
    )
    if "VOL_MA_5" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["VOL_MA_5"],
                name="MA_VOL5",
                line=dict(color="#eab308", width=1.1),
                hoverinfo="name+y"
            ),
            row=2, col=1
        )
    if "VOL_MA_10" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["VOL_MA_10"],
                name="MA_VOL10",
                line=dict(color="#3b82f6", width=1.1),
                hoverinfo="name+y"
            ),
            row=2, col=1
        )

    # 6. Row 3: 副图指标
    if sub_indicator == "MACD" and "MACD_DIF" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["MACD_DIF"],
                name="DIF (快线)",
                line=dict(color="#38bdf8", width=1.5)
            ),
            row=3, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["MACD_DEA"],
                name="DEA (慢线)",
                line=dict(color="#f97316", width=1.5)
            ),
            row=3, col=1
        )
        macd_bar_colors = [color_up if val >= 0 else color_down for val in df["MACD_BAR"]]
        fig.add_trace(
            go.Bar(
                x=df["date"],
                y=df["MACD_BAR"],
                name="MACD柱",
                marker=dict(color=macd_bar_colors)
            ),
            row=3, col=1
        )

    elif sub_indicator == "KDJ" and "KDJ_K" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["KDJ_K"],
                name="K (快线)",
                line=dict(color="#eab308", width=1.3)
            ),
            row=3, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["KDJ_D"],
                name="D (慢线)",
                line=dict(color="#3b82f6", width=1.3)
            ),
            row=3, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df["KDJ_J"],
                name="J (敏感)",
                line=dict(color="#ec4899", width=1.4)
            ),
            row=3, col=1
        )
        # 超买超卖参考虚线
        fig.add_hline(y=80, line_dash="dot", line_color="#ef4444", opacity=0.5, row=3, col=1)
        fig.add_hline(y=20, line_dash="dot", line_color="#22c55e", opacity=0.5, row=3, col=1)

    elif sub_indicator == "RSI" and "RSI_6" in df.columns:
        fig.add_trace(
            go.Scatter(x=df["date"], y=df["RSI_6"], name="RSI(6)", line=dict(color="#f59e0b", width=1.3)),
            row=3, col=1
        )
        if "RSI_12" in df.columns:
            fig.add_trace(
                go.Scatter(x=df["date"], y=df["RSI_12"], name="RSI(12)", line=dict(color="#3b82f6", width=1.3)),
                row=3, col=1
            )
        if "RSI_24" in df.columns:
            fig.add_trace(
                go.Scatter(x=df["date"], y=df["RSI_24"], name="RSI(24)", line=dict(color="#8b5cf6", width=1.3)),
                row=3, col=1
            )
        fig.add_hline(y=80, line_dash="dot", line_color="#ef4444", opacity=0.5, row=3, col=1)
        fig.add_hline(y=20, line_dash="dot", line_color="#22c55e", opacity=0.5, row=3, col=1)

    elif sub_indicator == "ATR" and "ATR_14" in df.columns:
        fig.add_trace(
            go.Scatter(x=df["date"], y=df["ATR_14"], name="ATR(14) 真实波幅", line=dict(color="#06b6d4", width=1.5)),
            row=3, col=1
        )

    # 7. 全局图表布局微调
    fig.update_layout(
        height=720,
        margin=dict(l=40, r=40, t=50, b=30),
        plot_bgcolor=bg_color,
        paper_bgcolor=bg_color,
        font=dict(color=text_color, size=12),
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11)
        )
    )

    # 去除非交易日空隙并配置网格线
    fig.update_xaxes(
        gridcolor=grid_color,
        showgrid=True,
        type="category",
        categoryorder="category ascending",
        nticks=10
    )
    fig.update_yaxes(
        gridcolor=grid_color,
        showgrid=True,
        side="right"
    )

    return fig
