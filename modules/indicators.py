# -*- coding: utf-8 -*-
"""
Technical Indicators Calculation Engine for StockPulse Studio.
Supports: MA, EMA, BOLL, MACD, KDJ, RSI, ATR and composite metrics.
"""
import pandas as pd
import numpy as np


def _validate_periods(periods, name: str = "periods") -> tuple[int, ...]:
    """Normalize indicator periods and reject values pandas cannot handle."""
    normalized = tuple(int(period) for period in periods)
    if not normalized or any(period <= 0 for period in normalized):
        raise ValueError(f"{name} must contain positive integers")
    return normalized


def add_ma(df: pd.DataFrame, periods=(5, 10, 20, 60, 120, 250)) -> pd.DataFrame:
    """计算简单移动平均线 (Moving Average)"""
    for p in _validate_periods(periods):
        df[f'MA_{p}'] = df['close'].rolling(window=p, min_periods=1).mean().round(3)
    return df


def add_ema(df: pd.DataFrame, periods=(12, 26)) -> pd.DataFrame:
    """计算指数移动平均线 (Exponential Moving Average)"""
    for p in _validate_periods(periods):
        df[f'EMA_{p}'] = df['close'].ewm(span=p, adjust=False).mean().round(3)
    return df


def add_boll(df: pd.DataFrame, period: int = 20, std_dev: int = 2) -> pd.DataFrame:
    """计算布林带指标 (Bollinger Bands)"""
    period = _validate_periods((period,), "period")[0]
    if std_dev < 0:
        raise ValueError("std_dev must be non-negative")
    mid = df['close'].rolling(window=period, min_periods=1).mean()
    std = df['close'].rolling(window=period, min_periods=1).std(ddof=0).fillna(0)
    df['BOLL_MID'] = mid.round(3)
    df['BOLL_UP'] = (mid + (std_dev * std)).round(3)
    df['BOLL_DOWN'] = (mid - (std_dev * std)).round(3)
    denom = (df['BOLL_UP'] - df['BOLL_DOWN']).replace(0, np.nan)
    df['BOLL_PCT_B'] = (((df['close'] - df['BOLL_DOWN']) / denom) * 100).fillna(50).round(2)
    return df


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """计算 MACD 指标 (DIF, DEA, BAR)"""
    fast, slow, signal = _validate_periods((fast, slow, signal))
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    df['MACD_DIF'] = (ema_fast - ema_slow).round(3)
    df['MACD_DEA'] = df['MACD_DIF'].ewm(span=signal, adjust=False).mean().round(3)
    df['MACD_BAR'] = ((df['MACD_DIF'] - df['MACD_DEA']) * 2).round(3)
    return df


def add_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """计算 KDJ 随机指标"""
    n, m1, m2 = _validate_periods((n, m1, m2))
    low_n = df['low'].rolling(window=n, min_periods=1).min()
    high_n = df['high'].rolling(window=n, min_periods=1).max()
    
    diff = high_n - low_n
    diff = diff.replace(0, np.nan)
    rsv = ((df['close'] - low_n) / diff * 100).fillna(50)

    k_vals, d_vals = [], []
    k_prev, d_prev = 50.0, 50.0

    for r in rsv:
        k_curr = (1 / m1) * r + ((m1 - 1) / m1) * k_prev
        d_curr = (1 / m2) * k_curr + ((m2 - 1) / m2) * d_prev
        k_vals.append(k_curr)
        d_vals.append(d_curr)
        k_prev, d_prev = k_curr, d_curr

    df['KDJ_K'] = pd.Series(k_vals, index=df.index).round(2)
    df['KDJ_D'] = pd.Series(d_vals, index=df.index).round(2)
    df['KDJ_J'] = (3 * df['KDJ_K'] - 2 * df['KDJ_D']).round(2)
    return df


def add_rsi(df: pd.DataFrame, periods=(6, 12, 24)) -> pd.DataFrame:
    """计算 RSI 相对强弱指标"""
    change = df['close'].diff()
    gain = change.clip(lower=0)
    loss = -1 * change.clip(upper=0)

    for p in _validate_periods(periods):
        avg_gain = gain.ewm(com=p - 1, min_periods=p).mean()
        avg_loss = loss.ewm(com=p - 1, min_periods=p).mean()
        denominator = avg_gain + avg_loss
        rsi = 100 * avg_gain / denominator.replace(0, np.nan)
        # No movement is neutral; a one-sided rising series must remain 100.
        neutral = (avg_gain == 0) & (avg_loss == 0)
        rsi = rsi.mask(neutral, 50)
        df[f'RSI_{p}'] = rsi.fillna(50).round(2)
    return df


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """计算 ATR 真实波幅指标"""
    period = _validate_periods((period,), "period")[0]
    high = df['high']
    low = df['low']
    close_prev = df['close'].shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df[f'ATR_{period}'] = tr.rolling(window=period, min_periods=1).mean().round(3)
    return df


def add_volume_ma(df: pd.DataFrame, periods=(5, 10, 20)) -> pd.DataFrame:
    """计算成交量均线"""
    for p in _validate_periods(periods):
        df[f'VOL_MA_{p}'] = df['volume'].rolling(window=p, min_periods=1).mean().round(0)
    return df


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """批量计算所有常用技术指标"""
    if df is None or df.empty or len(df) < 2:
        return df
    
    df = df.copy()
    rename_dict = {}
    for col in df.columns:
        c_lower = str(col).lower()
        if 'date' in c_lower or '日期' in c_lower or 'time' in c_lower:
            rename_dict[col] = 'date'
        elif 'open' in c_lower or '开盘' in c_lower:
            rename_dict[col] = 'open'
        elif 'close' in c_lower or '收盘' in c_lower:
            rename_dict[col] = 'close'
        elif 'high' in c_lower or '最高' in c_lower:
            rename_dict[col] = 'high'
        elif 'low' in c_lower or '最低' in c_lower:
            rename_dict[col] = 'low'
        elif 'volume' in c_lower or '成交量' in c_lower or 'vol' in c_lower:
            rename_dict[col] = 'volume'
    
    df = df.rename(columns=rename_dict)

    required_columns = {'date', 'open', 'close', 'high', 'low', 'volume'}
    missing_columns = sorted(required_columns.difference(df.columns))
    if missing_columns:
        raise ValueError(f"K-line data missing required columns: {', '.join(missing_columns)}")
    
    for col in ['open', 'close', 'high', 'low', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = (
        df.dropna(subset=['date', 'open', 'close', 'high', 'low', 'volume'])
        .sort_values('date')
        .drop_duplicates(subset=['date'], keep='last')
        .reset_index(drop=True)
    )
    if df.empty:
        return df
    
    df = add_ma(df)
    df = add_ema(df)
    df = add_boll(df)
    df = add_macd(df)
    df = add_kdj(df)
    df = add_rsi(df)
    df = add_atr(df)
    df = add_volume_ma(df)
    
    return df
