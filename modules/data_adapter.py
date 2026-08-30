# -*- coding: utf-8 -*-
"""
Multi-Market Data Adapter for StockPulse Studio.
Handles real-time quotes, historical K-lines, and symbol search for A-Shares, US Stocks, and ETFs.
"""
import os
import re
import json
import time
import requests
import pandas as pd
import numpy as np

# 热门/明星预置标的库 (支持快速检索与默认推荐)
POPULAR_STOCKS = [
    # 美股明星科技
    {"symbol": "NVDA", "name": "英伟达", "market": "美股", "category": "美股科技", "pinyin": "ywd"},
    {"symbol": "AAPL", "name": "苹果", "market": "美股", "category": "美股科技", "pinyin": "pg"},
    {"symbol": "TSLA", "name": "特斯拉", "market": "美股", "category": "美股科技", "pinyin": "tsl"},
    {"symbol": "MSFT", "name": "微软", "market": "美股", "category": "美股科技", "pinyin": "wr"},
    {"symbol": "GOOGL", "name": "谷歌-A", "market": "美股", "category": "美股科技", "pinyin": "gg"},
    {"symbol": "AMZN", "name": "亚马逊", "market": "美股", "category": "美股科技", "pinyin": "ymx"},
    {"symbol": "META", "name": "Meta", "market": "美股", "category": "美股科技", "pinyin": "meta"},
    {"symbol": "AMD", "name": "超微半导体", "market": "美股", "category": "美股科技", "pinyin": "amd"},
    {"symbol": "INTC", "name": "英特尔", "market": "美股", "category": "美股半导体", "pinyin": "yte"},
    {"symbol": "QCOM", "name": "高通", "market": "美股", "category": "美股半导体", "pinyin": "gt"},
    {"symbol": "TSM", "name": "台积电", "market": "美股", "category": "美股半导体", "pinyin": "tjd"},
    {"symbol": "PLTR", "name": "Palantir", "market": "美股", "category": "AI软件", "pinyin": "pltr"},
    {"symbol": "COIN", "name": "Coinbase", "market": "美股", "category": "加密概念", "pinyin": "coin"},
    # 美股知名中概
    {"symbol": "BABA", "name": "阿里巴巴", "market": "美股", "category": "知名中概", "pinyin": "albb"},
    {"symbol": "PDD", "name": "拼多多", "market": "美股", "category": "知名中概", "pinyin": "pdd"},
    {"symbol": "JD", "name": "京东", "market": "美股", "category": "知名中概", "pinyin": "jd"},
    {"symbol": "NTES", "name": "网易", "market": "美股", "category": "知名中概", "pinyin": "wy"},
    {"symbol": "BIDU", "name": "百度", "market": "美股", "category": "知名中概", "pinyin": "bd"},
    {"symbol": "NIO", "name": "蔚来汽车", "market": "美股", "category": "造车新势力", "pinyin": "wl"},
    {"symbol": "LI", "name": "理想汽车", "market": "美股", "category": "造车新势力", "pinyin": "lx"},
    {"symbol": "XPEV", "name": "小鹏汽车", "market": "美股", "category": "造车新势力", "pinyin": "xp"},
    {"symbol": "FUTU", "name": "富途控股", "market": "美股", "category": "知名中概", "pinyin": "ft"},
    # A股核心白马与成长
    {"symbol": "600519", "name": "贵州茅台", "market": "A股", "category": "消费白酒", "pinyin": "gzmt"},
    {"symbol": "300750", "name": "宁德时代", "market": "A股", "category": "新能源", "pinyin": "ndsd"},
    {"symbol": "002594", "name": "比亚迪", "market": "A股", "category": "新能源汽车", "pinyin": "byd"},
    {"symbol": "601318", "name": "中国平安", "market": "A股", "category": "金融蓝筹", "pinyin": "zgpa"},
    {"symbol": "000858", "name": "五粮液", "market": "A股", "category": "消费白酒", "pinyin": "wly"},
    {"symbol": "600036", "name": "招商银行", "market": "A股", "category": "金融蓝筹", "pinyin": "zsyh"},
    {"symbol": "688981", "name": "中芯国际", "market": "A股", "category": "芯片半导体", "pinyin": "zxgj"},
    {"symbol": "002230", "name": "科大讯飞", "market": "A股", "category": "AI算力", "pinyin": "kdxf"},
    {"symbol": "601138", "name": "工业富联", "market": "A股", "category": "AI服务器", "pinyin": "gyfl"},
    {"symbol": "300059", "name": "东方财富", "market": "A股", "category": "互联网券商", "pinyin": "dfcf"},
    {"symbol": "601857", "name": "中国石油", "market": "A股", "category": "中字头高股息", "pinyin": "zgsy"},
    {"symbol": "600900", "name": "长江电力", "market": "A股", "category": "高股息防御", "pinyin": "cjdl"},
    {"symbol": "000001", "name": "平安银行", "market": "A股", "category": "银行金融", "pinyin": "payh"},
    # 核心 ETF
    {"symbol": "510300", "name": "沪深300ETF", "market": "ETF", "category": "宽基指数", "pinyin": "hs300"},
    {"symbol": "510500", "name": "中证500ETF", "market": "ETF", "category": "宽基指数", "pinyin": "zz500"},
    {"symbol": "588000", "name": "科创50ETF", "market": "ETF", "category": "科技宽基", "pinyin": "kc50"},
    {"symbol": "159915", "name": "创业板ETF", "market": "ETF", "category": "成长宽基", "pinyin": "cyb"},
    {"symbol": "513100", "name": "纳指ETF", "market": "ETF", "category": "海外QDII", "pinyin": "nzetf"},
    {"symbol": "513500", "name": "标普500ETF", "market": "ETF", "category": "海外QDII", "pinyin": "bp500"},
    {"symbol": "513180", "name": "恒生科技ETF", "market": "ETF", "category": "港股互联", "pinyin": "hskj"},
    {"symbol": "512480", "name": "半导体ETF", "market": "ETF", "category": "行业ETF", "pinyin": "bdt"},
    {"symbol": "512010", "name": "医药ETF", "market": "ETF", "category": "行业ETF", "pinyin": "yy"},
    {"symbol": "518880", "name": "黄金ETF", "market": "ETF", "category": "商品避险", "pinyin": "hjetf"},
    {"symbol": "510880", "name": "红利ETF", "market": "ETF", "category": "高股息策略", "pinyin": "hletf"}
]


class DataAdapter:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://finance.sina.com.cn"
        }
        self.cache = {}
        self.cache_ttl = 30  # 秒

    @staticmethod
    def _to_float(value, default: float = 0.0) -> float:
        """Parse numeric API fields without letting one malformed field drop a quote."""
        if value is None or value == "":
            return default
        try:
            return float(str(value).strip().strip('";'))
        except (TypeError, ValueError):
            return default

    def detect_market(self, symbol: str) -> str:
        """自动推测股票所属市场"""
        sym = symbol.strip().upper()
        if sym.startswith(("51", "15", "58", "56", "16")):
            return "ETF"
        elif sym.startswith(("60", "68", "00", "30", "92", "83", "87", "43")):
            return "A股"
        elif any(c.isalpha() for c in sym):
            return "美股"
        return "A股"

    def get_tencent_code(self, symbol: str, market: str = None) -> str:
        """将股票代码转换为腾讯接口格式"""
        sym = symbol.strip().upper()
        if not market or market == "auto":
            market = self.detect_market(sym)

        if market == "美股":
            return f"us{sym}"
        elif market in ["A股", "ETF"]:
            if sym.startswith(("6", "5", "9")):
                return f"sh{sym}"
            else:
                return f"sz{sym}"
        return sym

    def get_realtime_quote(self, symbol: str, market: str = "auto") -> dict:
        """获取单个标的的实时行情数据"""
        sym = symbol.strip().upper()
        if market == "auto":
            market = self.detect_market(sym)
        
        tc_code = self.get_tencent_code(sym, market)
        url = f"http://qt.gtimg.cn/q={tc_code}"
        
        try:
            r = requests.get(url, headers=self.headers, timeout=4)
            text = r.content.decode("gbk", errors="ignore")
            if not text or "~" not in text:
                return self._fallback_quote(sym, market)
            
            parts = text.split("~")
            if len(parts) < 35:
                return self._fallback_quote(sym, market)
            
            name = parts[1] if parts[1] else sym
            price = self._to_float(parts[3])
            prev_close = self._to_float(parts[4], price)
            open_price = self._to_float(parts[5], price)
            volume = self._to_float(parts[6])
            high = self._to_float(parts[33], price) if len(parts) > 33 else price
            low = self._to_float(parts[34], price) if len(parts) > 34 else price
            pct_chg = self._to_float(parts[32]) if len(parts) > 32 else 0.0
            change = self._to_float(parts[31], round(price - prev_close, 3)) if len(parts) > 31 else round(price - prev_close, 3)
            turnover = self._to_float(parts[38]) if len(parts) > 38 else 0.0
            pe = self._to_float(parts[39]) if len(parts) > 39 else 0.0
            mktcap = self._to_float(parts[45]) if len(parts) > 45 else 0.0

            return {
                "symbol": sym,
                "name": name,
                "market": market,
                "price": price,
                "prev_close": prev_close,
                "open": open_price,
                "high": high,
                "low": low,
                "change": change,
                "pct_chg": pct_chg,
                "volume": volume,
                "turnover": turnover,
                "pe": pe,
                "mktcap": mktcap,
                "time": parts[30] if len(parts) > 30 else ""
            }
        except Exception as e:
            return self._fallback_quote(sym, market)

    def _fallback_quote(self, symbol: str, market: str) -> dict:
        """兜底行情对象"""
        # 尝试匹配预置库名称
        found_name = symbol
        for item in POPULAR_STOCKS:
            if item["symbol"].upper() == symbol.upper():
                found_name = item["name"]
                market = item["market"]
                break
        return {
            "symbol": symbol,
            "name": found_name,
            "market": market,
            "price": 0.0,
            "prev_close": 0.0,
            "open": 0.0,
            "high": 0.0,
            "low": 0.0,
            "change": 0.0,
            "pct_chg": 0.0,
            "volume": 0.0,
            "turnover": 0.0,
            "pe": 0.0,
            "mktcap": 0.0,
            "time": ""
        }

    def get_batch_quotes(self, items: list) -> list:
        """批量获取实时行情列表 (items 为 [{'symbol': 'NVDA', 'market': '美股'}, ...])"""
        if not items:
            return []
        
        tc_codes = []
        item_map = {}
        for it in items:
            sym = it["symbol"].strip().upper()
            mkt = it.get("market", self.detect_market(sym))
            tc = self.get_tencent_code(sym, mkt)
            tc_codes.append(tc)
            item_map[tc.lower()] = it

        url = f"http://qt.gtimg.cn/q={','.join(tc_codes)}"
        results_by_code = {}
        try:
            r = requests.get(url, headers=self.headers, timeout=5)
            text = r.content.decode("gbk", errors="ignore")
            lines = [l for l in text.split(";") if l.strip()]
            for line in lines:
                raw_tag = line.split("=", 1)[0].replace("v_", "").strip().lower()
                parts = line.split("~")
                if len(parts) > 34 and raw_tag in item_map:
                    orig_item = item_map.get(raw_tag, {})
                    sym = orig_item.get("symbol", parts[2].split(".")[0])
                    mkt = orig_item.get("market", self.detect_market(sym))
                    name = orig_item.get("name", parts[1]) or parts[1]
                    price = self._to_float(parts[3])
                    prev_close = self._to_float(parts[4], price)
                    open_price = self._to_float(parts[5], price)
                    high = self._to_float(parts[33], price)
                    low = self._to_float(parts[34], price)
                    pct_chg = self._to_float(parts[32])
                    change = self._to_float(parts[31], round(price - prev_close, 3))
                    volume = self._to_float(parts[6])
                    
                    results_by_code[raw_tag] = {
                        "symbol": sym,
                        "name": name,
                        "market": mkt,
                        "price": price,
                        "prev_close": prev_close,
                        "open": open_price,
                        "high": high,
                        "low": low,
                        "change": change,
                        "pct_chg": pct_chg,
                        "volume": volume,
                        "extra": orig_item
                    }
        except (requests.RequestException, UnicodeError, ValueError, TypeError):
            # Missing or malformed entries are filled below in the original order.
            pass

        results = []
        for item, tc_code in zip(items, tc_codes):
            quote = results_by_code.get(tc_code.lower())
            if quote is None:
                quote = self.get_realtime_quote(item["symbol"], item.get("market", "auto"))
                quote["extra"] = item
            results.append(quote)
        return results

    def get_usd_cny_rate(self) -> float:
        """Return a cached USD/CNY rate with Tencent and public-API fallbacks."""
        cache_key = "usd_cny_rate"
        cached = self.cache.get(cache_key)
        if cached and time.time() - cached[0] < 3600:
            self.usd_cny_rate_source = cached[2] if len(cached) > 2 else "缓存汇率"
            return cached[1]

        # Last verified public reference on 2026-08-30. It is shown as a dated
        # fallback in the UI and remains manually editable by the user.
        rate = 6.745925
        source = "内置参考（2026-08-30）"

        # Tencent is already used for quotes by this app and is usually more
        # reachable in the same network environment.
        try:
            response = requests.get(
                "http://qt.gtimg.cn/q=fx_usr",
                headers=self.headers,
                timeout=4,
            )
            text = response.content.decode("gbk", errors="ignore")
            parts = text.split("~")
            fetched_rate = float(parts[3]) if len(parts) > 3 and parts[3] else 0.0
            if 5.0 <= fetched_rate <= 10.0:
                rate = fetched_rate
                source = "腾讯财经实时汇率"
        except (requests.RequestException, ValueError, TypeError, AttributeError, IndexError):
            pass

        # Secondary public source when Tencent is unavailable.
        if source.startswith("内置参考"):
            try:
                response = requests.get(
                    "https://open.er-api.com/v6/latest/USD",
                    headers=self.headers,
                    timeout=4,
                )
                payload = response.json()
                fetched_rate = float(payload.get("rates", {}).get("CNY", 0.0) or 0.0)
                if 5.0 <= fetched_rate <= 10.0:
                    rate = fetched_rate
                    source = "ExchangeRate-API 每日汇率"
            except (requests.RequestException, ValueError, TypeError, AttributeError):
                pass

        self.usd_cny_rate_source = source
        self.cache[cache_key] = (time.time(), rate, source)
        return rate

    def get_kline_data(self, symbol: str, market: str = "auto", period: str = "daily", limit: int = 360) -> pd.DataFrame:
        """
        获取历史K线数据
        period: 'daily' (日K), 'weekly' (周K), 'monthly' (月K)
        返回包含 date, open, close, high, low, volume 的 DataFrame
        """
        sym = symbol.strip().upper()
        if market == "auto":
            market = self.detect_market(sym)

        # 1. 美股历史 K 线 (优先新浪超全接口，兼容腾讯与备用)
        if market == "美股":
            df = self._get_us_kline_sina(sym)
            if df is not None and not df.empty:
                if period == "weekly":
                    df = self._resample_kline(df, "W")
                elif period == "monthly":
                    df = self._resample_kline(df, "M")
                return df.tail(limit).reset_index(drop=True)
            
            # 备用：yfinance
            try:
                import yfinance as yf
                yf_ticker = yf.Ticker(sym)
                yf_period = "2y" if period == "daily" else "5y"
                yf_df = yf_ticker.history(period=yf_period)
                if not yf_df.empty:
                    yf_df = yf_df.reset_index()
                    yf_df["date"] = yf_df["Date"].dt.strftime("%Y-%m-%d")
                    yf_df = yf_df.rename(columns={"Open": "open", "Close": "close", "High": "high", "Low": "low", "Volume": "volume"})
                    return yf_df[["date", "open", "close", "high", "low", "volume"]].tail(limit).reset_index(drop=True)
            except Exception:
                pass

        # 2. A股 / ETF 历史 K 线
        period_map = {"daily": "day", "weekly": "week", "monthly": "month"}
        p_str = period_map.get(period, "day")
        tc_code = self.get_tencent_code(sym, market)
        url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={tc_code},{p_str},,,{limit},qfq"

        try:
            r = requests.get(url, headers=self.headers, timeout=5)
            data = r.json()
            if "data" in data and tc_code in data["data"]:
                stock_data = data["data"][tc_code]
                k_key = f"qfq{p_str}" if f"qfq{p_str}" in stock_data else p_str
                if k_key in stock_data:
                    raw_k = stock_data[k_key]
                    rows = []
                    for item in raw_k:
                        # item: [date, open, close, high, low, volume, ...]
                        if len(item) >= 6:
                            rows.append({
                                "date": str(item[0]),
                                "open": float(item[1]),
                                "close": float(item[2]),
                                "high": float(item[3]),
                                "low": float(item[4]),
                                "volume": float(item[5])
                            })
                    if rows:
                        df = pd.DataFrame(rows)
                        return df.tail(limit).reset_index(drop=True)
        except Exception as e:
            pass

        # 3. 备用新浪 A 股 K 线接口
        try:
            sina_code = tc_code
            sina_url = f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_code}&scale=240&ma=no&datalen={limit}"
            r = requests.get(sina_url, headers=self.headers, timeout=5)
            data = r.json()
            if data and isinstance(data, list):
                rows = []
                for item in data:
                    rows.append({
                        "date": str(item["day"]),
                        "open": float(item["open"]),
                        "close": float(item["close"]),
                        "high": float(item["high"]),
                        "low": float(item["low"]),
                        "volume": float(item["volume"])
                    })
                df = pd.DataFrame(rows)
                return df.tail(limit).reset_index(drop=True)
        except Exception:
            pass

        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "volume"])

    def _get_us_kline_sina(self, symbol: str) -> pd.DataFrame:
        """从新浪获取美股完整日K线"""
        url = f"https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var_k=/US_MinKService.getDailyK?symbol={symbol}"
        try:
            r = requests.get(url, headers=self.headers, timeout=6)
            m = re.search(r"var_k=\((.*)\);", r.text)
            if m:
                raw_json = json.loads(m.group(1))
                rows = []
                for item in raw_json:
                    rows.append({
                        "date": str(item["d"]),
                        "open": float(item["o"]),
                        "close": float(item["c"]),
                        "high": float(item["h"]),
                        "low": float(item["l"]),
                        "volume": float(item["v"])
                    })
                df = pd.DataFrame(rows)
                return df
        except Exception:
            pass
        return None

    def _resample_kline(self, df: pd.DataFrame, freq: str) -> pd.DataFrame:
        """将日K重采样为周K或月K"""
        if df is None or df.empty:
            return df
        df = df.copy()
        df["datetime"] = pd.to_datetime(df["date"])
        df = df.set_index("datetime")
        resampled = df.resample(freq).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "date": "last"
        }).dropna().reset_index(drop=True)
        return resampled

    def search_symbols(self, query: str) -> list:
        """根据关键字（代码、中文名称、拼音）搜索标的"""
        q = query.strip().lower()
        if not q:
            return POPULAR_STOCKS[:10]

        matches = []
        for item in POPULAR_STOCKS:
            if (q in item["symbol"].lower() or 
                q in item["name"].lower() or 
                q in item.get("pinyin", "").lower() or
                q in item.get("category", "").lower()):
                matches.append(item)

        # 如果没有在预置库中找到，且输入看起来像有效代码，动态生成一条
        if not matches and (q.isalnum() or "." in q):
            mkt = self.detect_market(q)
            matches.append({
                "symbol": q.upper(),
                "name": q.upper(),
                "market": mkt,
                "category": f"自定义{mkt}",
                "pinyin": q
            })
        return matches

    def get_market_spot_pool(self, market_type: str = "A股", top_n: int = 80) -> pd.DataFrame:
        """获取指定市场的行情池（供选股器筛选）"""
        if market_type == "美股":
            # 美股精选标的池实时行情
            quotes = self.get_batch_quotes([item for item in POPULAR_STOCKS if item["market"] == "美股"])
            df = pd.DataFrame(quotes)
            return df

        elif market_type == "ETF":
            # ETF精选池
            quotes = self.get_batch_quotes([item for item in POPULAR_STOCKS if item["market"] == "ETF"])
            df = pd.DataFrame(quotes)
            return df

        else:
            # A股主板与热门股池 (拉取新浪 A 股列表前 top_n)
            url = f"http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num={top_n}&sort=amount&asc=0&node=hs_a&symbol=&_s_r_a=init"
            try:
                r = requests.get(url, headers=self.headers, timeout=5)
                data = r.json()
                rows = []
                for item in data:
                    rows.append({
                        "symbol": item["code"],
                        "name": item["name"],
                        "market": "A股",
                        "price": float(item.get("trade", 0) or 0),
                        "pct_chg": float(item.get("changepercent", 0) or 0),
                        "change": float(item.get("pricechange", 0) or 0),
                        "open": float(item.get("open", 0) or 0),
                        "high": float(item.get("high", 0) or 0),
                        "low": float(item.get("low", 0) or 0),
                        "prev_close": float(item.get("settlement", 0) or 0),
                        "volume": float(item.get("volume", 0) or 0),
                        "turnover": float(item.get("turnoverratio", 0) or 0),
                        "pe": float(item.get("per", 0) or 0),
                        "pb": float(item.get("pb", 0) or 0),
                        "mktcap": float(item.get("mktcap", 0) or 0) / 10000.0  # 亿元
                    })
                return pd.DataFrame(rows)
            except Exception:
                # 降级使用预置 A 股
                quotes = self.get_batch_quotes([item for item in POPULAR_STOCKS if item["market"] == "A股"])
                return pd.DataFrame(quotes)
