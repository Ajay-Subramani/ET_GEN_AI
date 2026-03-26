from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from app.constants import SECTOR_PROXY_MAP

try:
    from nsepython import nse_get_bulk_deals, nse_optionchain_scrapper
except Exception:  # pragma: no cover
    nse_get_bulk_deals = None
    nse_optionchain_scrapper = None

try:
    import talib
except Exception:  # pragma: no cover
    talib = None


@dataclass
class DataFrameResult:
    data: pd.DataFrame
    source: str


class MarketDataService:
    def get_price_history(self, symbol: str, period: str = "6mo", interval: str = "1d") -> DataFrameResult:
        ticker = f"{symbol.upper()}.NS"
        try:
            history = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
            if not history.empty:
                history = history.rename(columns=str.lower)
                return DataFrameResult(data=history, source="yfinance")
        except Exception as e:
            logging.error(f"Failed to fetch price history for {symbol}: {e}")

        return DataFrameResult(data=pd.DataFrame(), source="failed")

    def get_sector_snapshot(self, sector: str) -> dict[str, Any]:
        proxy = SECTOR_PROXY_MAP.get(sector)
        if not proxy:
            return {"trend": "neutral", "strength": 0.5, "proxy": None, "source": "demo"}

        try:
            history = yf.Ticker(proxy).history(period="1mo", interval="1d", auto_adjust=False)
            if not history.empty:
                close = history["Close"]
                ret = float((close.iloc[-1] / close.iloc[0]) - 1)
                return {
                    "trend": "bullish" if ret > 0.02 else "bearish" if ret < -0.02 else "neutral",
                    "strength": min(max(abs(ret) * 10, 0.1), 1.0),
                    "proxy": proxy,
                    "source": "yfinance",
                }
        except Exception as e:
            logging.error(f"Failed to fetch sector snapshot for {sector}: {e}")

        return {"trend": "neutral", "strength": 0.0, "proxy": proxy, "source": "failed"}

    def get_market_breadth(self) -> dict[str, Any]:
        try:
            nifty = yf.Ticker("^NSEI").history(period="1mo", interval="1d", auto_adjust=False)
            vix = yf.Ticker("^INDIAVIX").history(period="1mo", interval="1d", auto_adjust=False)
            if not nifty.empty:
                close = nifty["Close"]
                trend = "uptrend" if close.iloc[-1] > close.tail(5).mean() else "sideways"
                vix_value = float(vix["Close"].iloc[-1]) if not vix.empty else 14.0
                return {
                    "breadth": 1.35 if trend == "uptrend" else 0.95,
                    "condition": "risk_on" if trend == "uptrend" and vix_value < 16 else "neutral",
                    "nifty_trend": trend,
                    "volatility_regime": "low" if vix_value < 14 else "elevated" if vix_value > 18 else "normal",
                    "source": "yfinance",
                }
        except Exception as e:
            logging.error(f"Failed to fetch market breadth: {e}")

        return {
            "breadth": 0.0,
            "condition": "neutral",
            "nifty_trend": "unknown",
            "volatility_regime": "unknown",
            "source": "failed",
        }

    def get_bulk_deals(self, symbol: str) -> tuple[list[dict[str, Any]], str]:
        if nse_get_bulk_deals:
            try:
                deals = nse_get_bulk_deals()
                filtered = [deal for deal in deals if str(deal.get("symbol", "")).upper() == symbol.upper()]
                if filtered:
                    for deal in filtered:
                        deal["deal_value_cr"] = (
                            float(deal.get("quantity", 0)) * float(deal.get("price", 0))
                        ) / 10_000_000
                    return filtered, "nsepython"
            except Exception as e:
                logging.error(f"Failed to fetch bulk deals from nsepython: {e}")

        return [], "failed"

    def get_delivery_pct(self, symbol: str, history: pd.DataFrame) -> tuple[float, float, str]:
        if history.empty:
            return 0.0, 0.0, "demo"

        recent_turnover = history["volume"].tail(20).mean()
        # Delivery data is strictly NSE-specific and often requires custom scrapers or local CSVs.
        # Returning 0.0 to signal no data in this implementation.
        return 0.0, 0.0, "none"

    def get_option_chain_support(self, symbol: str, price: float) -> tuple[float | None, str]:
        if nse_optionchain_scrapper:
            try:
                option_chain = nse_optionchain_scrapper(symbol.upper())
                records = option_chain.get("records", {}).get("data", [])
                puts = [
                    row["PE"]
                    for row in records
                    if isinstance(row, dict) and row.get("PE") and row["PE"].get("openInterest")
                ]
                if puts:
                    max_put = max(puts, key=lambda row: row.get("openInterest", 0))
                    return float(max_put.get("strikePrice", price)), "nsepython"
            except Exception as e:
                logging.error(f"Failed to fetch option chain for {symbol}: {e}")

        return None, "failed"

    def compute_pattern_indicators(self, history: pd.DataFrame) -> dict[str, Any]:
        if history.empty:
            return {}

        close = history["close"].astype(float)
        volume = history["volume"].astype(float)
        high = history["high"].astype(float)
        low = history["low"].astype(float)

        indicators: dict[str, Any] = {
            "close": close,
            "volume": volume,
            "20d_high": float(high.tail(20).max()),
            "20d_low": float(low.tail(20).min()),
            "prev_20d_high": float(high.iloc[:-1].tail(20).max()) if len(high) > 20 else float(high.max()),
            "prev_20d_low": float(low.iloc[:-1].tail(20).min()) if len(low) > 20 else float(low.min()),
            "20d_vol_avg": float(volume.tail(20).mean()),
            "prev_20d_vol_avg": float(volume.iloc[:-1].tail(20).mean()) if len(volume) > 20 else float(volume.mean()),
        }

        if talib:
            indicators["rsi"] = float(talib.RSI(close, timeperiod=14).iloc[-1])
        else:
            deltas = close.diff().fillna(0)
            gains = deltas.clip(lower=0).rolling(14).mean()
            losses = (-deltas.clip(upper=0)).rolling(14).mean().replace(0, np.nan)
            rs = gains / losses
            indicators["rsi"] = float((100 - (100 / (1 + rs))).fillna(50).iloc[-1])

        return indicators


