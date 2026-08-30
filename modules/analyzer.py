# -*- coding: utf-8 -*-
"""
Technical Pattern & Quantitative Diagnostic Engine for StockPulse Studio.
Generates comprehensive health score, support/resistance levels, and action briefings.
"""
import pandas as pd
import numpy as np


class TechnicalAnalyzer:
    def __init__(self):
        pass

    def analyze(self, df: pd.DataFrame, stock_info: dict = None) -> dict:
        """
        对个股技术指标进行全方位形态诊断
        """
        if df is None or df.empty or len(df) < 5:
            return {
                "score": 50,
                "status": "数据不足",
                "summary": "历史K线数据量过少，无法形成有效技术面诊断结论。",
                "signals": [],
                "support_levels": [],
                "resistance_levels": []
            }

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        close = latest["close"]

        signals = []
        score = 50  # 初始中性分

        # 1. 均线形态诊断 (MA)
        ma_bullish = False
        if "MA_5" in latest and "MA_10" in latest and "MA_20" in latest:
            ma5 = latest["MA_5"]
            ma10 = latest["MA_10"]
            ma20 = latest["MA_20"]
            if close > ma5 > ma10 > ma20:
                signals.append({"type": "bullish", "tag": "均线多头", "desc": f"收盘价({close:.2f})站稳短期各均线，MA5/10/20呈标准多头排列，趋势向上。"})
                score += 15
                ma_bullish = True
            elif close < ma5 < ma10 < ma20:
                signals.append({"type": "bearish", "tag": "均线空头", "desc": f"收盘价({close:.2f})跌破短期各均线，MA5/10/20呈空头排列，短期承压。"})
                score -= 15
            elif close > ma20:
                signals.append({"type": "neutral", "tag": "中线向好", "desc": f"价格位于20日生命线(MA20: {ma20:.2f})上方运行，中线趋势尚可。"})
                score += 5

        # 2. MACD 诊断
        if "MACD_DIF" in latest and "MACD_DEA" in latest and "MACD_BAR" in latest:
            dif = latest["MACD_DIF"]
            dea = latest["MACD_DEA"]
            bar = latest["MACD_BAR"]
            prev_dif = prev["MACD_DIF"]
            prev_dea = prev["MACD_DEA"]

            # 金叉判定
            if prev_dif <= prev_dea and dif > dea:
                if dif > 0:
                    signals.append({"type": "bullish", "tag": "零上金叉", "desc": "MACD在零轴上方形成强势金叉，多头动能强劲加速。"})
                    score += 15
                else:
                    signals.append({"type": "bullish", "tag": "底部金叉", "desc": "MACD在零轴下方低位形成金叉反弹信号。"})
                    score += 10
            elif prev_dif >= prev_dea and dif < dea:
                signals.append({"type": "bearish", "tag": "MACD死叉", "desc": "MACD短期由强转弱，快线向下跌穿慢线，注意回调风险。"})
                score -= 10
            elif dif > dea and bar > 0:
                signals.append({"type": "bullish", "tag": "多头持仓区", "desc": "MACD处于多头发散状态，红柱持续放大。"})
                score += 5

        # 3. KDJ 随机指标诊断
        if "KDJ_K" in latest and "KDJ_D" in latest and "KDJ_J" in latest:
            k = latest["KDJ_K"]
            d = latest["KDJ_D"]
            j = latest["KDJ_J"]
            if j < 20 and k > d:
                signals.append({"type": "bullish", "tag": "KDJ超卖金叉", "desc": f"J值({j:.1f})处于低位超卖区且形成金叉，短期存在强烈超跌反弹动能。"})
                score += 10
            elif j > 90:
                signals.append({"type": "warning", "tag": "KDJ严重超买", "desc": f"J值({j:.1f})触及高位超买极值，短期需警惕冲高回落或技术性整理。"})
                score -= 5
            elif k > d and j > 50:
                signals.append({"type": "bullish", "tag": "KDJ强势区", "desc": "KDJ三线在50上方良性发散，处于多头掌控范围。"})
                score += 5

        # 4. RSI 强弱指标诊断
        if "RSI_6" in latest:
            rsi6 = latest["RSI_6"]
            if rsi6 > 80:
                signals.append({"type": "warning", "tag": "RSI超买预警", "desc": f"RSI(6)达到 {rsi6:.1f}，进入强超买区，谨防追高回撤。"})
            elif rsi6 < 25:
                signals.append({"type": "bullish", "tag": "RSI超卖反弹", "desc": f"RSI(6)降至 {rsi6:.1f}，进入深度超卖区，性价比较高。"})
                score += 8
            elif 50 <= rsi6 <= 75:
                signals.append({"type": "bullish", "tag": "RSI多头区间", "desc": f"RSI(6)为 {rsi6:.1f}，处于多头活跃温和上升区间。"})
                score += 5

        # 5. 成交量量能诊断
        if "VOL_MA_5" in latest and latest["VOL_MA_5"] > 0:
            vol_ratio = latest["volume"] / latest["VOL_MA_5"]
            if vol_ratio > 1.8 and latest["close"] >= latest["open"]:
                signals.append({"type": "bullish", "tag": "放量突破", "desc": f"今日成交量达5日均量的 {vol_ratio:.1f} 倍，且收阳线上攻，资金进场明显。"})
                score += 10
            elif vol_ratio < 0.6:
                signals.append({"type": "neutral", "tag": "缩量整理", "desc": f"成交量仅为5日均量的 {vol_ratio:.1f} 倍，市场交投较为清淡，观望情绪浓厚。"})

        # 6. 布林带 (BOLL) 诊断
        if "BOLL_UP" in latest and "BOLL_DOWN" in latest:
            b_up = latest["BOLL_UP"]
            b_down = latest["BOLL_DOWN"]
            b_mid = latest["BOLL_MID"]
            if close >= b_up:
                signals.append({"type": "warning", "tag": "触及布林上轨", "desc": f"价格突破布林线上轨({b_up:.2f})，短期进入超强通道，留意波段上压力。"})
            elif close <= b_down:
                signals.append({"type": "bullish", "tag": "触及布林下轨", "desc": f"价格回踩布林线下轨({b_down:.2f})，受到下轨通道支撑。"})
                score += 5

        # 7. 计算关键支撑位与阻力位 (Support / Resistance)
        recent_window = df.tail(30)
        recent_high = recent_window["high"].max()
        recent_low = recent_window["low"].min()
        ma20_val = latest.get("MA_20", close * 0.95)
        ma60_val = latest.get("MA_60", close * 0.90)
        boll_up_val = latest.get("BOLL_UP", close * 1.05)
        boll_down_val = latest.get("BOLL_DOWN", close * 0.95)

        resistance_levels = sorted(list(set([
            round(recent_high, 2),
            round(boll_up_val, 2)
        ])), reverse=True)

        support_levels = sorted(list(set([
            round(ma20_val, 2),
            round(recent_low, 2),
            round(boll_down_val, 2)
        ])))

        # 约束综合得分在 0 ~ 100
        score = max(5, min(98, score))

        # 状态文案判定
        if score >= 80:
            status_text = "🚀 极强多头主升"
            summary_advice = "该标的技术形态优异，多项指标共振多头，动能充沛。持股者可顺应趋势持有，突破前高可顺势跟进，设定移动止损保护利润。"
        elif score >= 65:
            status_text = "📈 稳健上升通道"
            summary_advice = "该标的中短期均线良性向上，量价配合平稳。可重点依托MA10或MA20支撑位逢低布局或持仓观察。"
        elif score >= 45:
            status_text = "⚖️ 箱体震荡蓄势"
            summary_advice = "目前多空力量相对均衡，处于区间震荡洗盘阶段。建议在箱体下沿支撑位附近低吸，在阻力位附近适度减仓，切忌追涨。"
        elif score >= 30:
            status_text = "📉 弱势回调整理"
            summary_advice = "近期走势受均线压制，短期动能不足。建议保持谨慎，多看少动，等待回踩关键支撑企稳并出现金叉反转信号再做决策。"
        else:
            status_text = "❄️ 弱势空头探底"
            summary_advice = "各项指标均处于空头或弱势区域，下行风险较大。建议严格控制仓位，规避左侧盲目抄底风险。"

        return {
            "score": score,
            "status": status_text,
            "summary": summary_advice,
            "signals": signals,
            "resistance_levels": [r for r in resistance_levels if r > close * 0.98][:2],
            "support_levels": [s for s in support_levels if s < close * 1.02][:2],
            "latest_close": close
        }
