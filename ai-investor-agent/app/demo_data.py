from __future__ import annotations

from datetime import date, timedelta


DEMO_STOCKS = {
    "TATASTEEL": {
        "name": "Tata Steel Ltd",
        "sector": "Metals",
        "market_cap": 204000.0,
        "is_fno": True,
    },
    "RELIANCE": {
        "name": "Reliance Industries Ltd",
        "sector": "Energy",
        "market_cap": 1900000.0,
        "is_fno": True,
    },
    "HDFCBANK": {
        "name": "HDFC Bank Ltd",
        "sector": "Financials",
        "market_cap": 1350000.0,
        "is_fno": True,
    },
    "INFY": {
        "name": "Infosys Ltd",
        "sector": "Information Technology",
        "market_cap": 720000.0,
        "is_fno": True,
    },
    "SUNPHARMA": {
        "name": "Sun Pharmaceutical Industries Ltd",
        "sector": "Healthcare",
        "market_cap": 410000.0,
        "is_fno": True,
    },
}

DEMO_PATTERN_SUCCESS = {
    ("TATASTEEL", "breakout"): {
        "total_occurrences": 12,
        "successful_occurrences": 9,
        "success_rate": 0.72,
        "avg_return_pct": 8.5,
    },
    ("TATASTEEL", "support_bounce"): {
        "total_occurrences": 16,
        "successful_occurrences": 10,
        "success_rate": 0.63,
        "avg_return_pct": 5.4,
    },
    ("RELIANCE", "breakout"): {
        "total_occurrences": 14,
        "successful_occurrences": 9,
        "success_rate": 0.64,
        "avg_return_pct": 6.2,
    },
    ("HDFCBANK", "support_bounce"): {
        "total_occurrences": 18,
        "successful_occurrences": 13,
        "success_rate": 0.72,
        "avg_return_pct": 4.1,
    },
}

DEMO_USER_PORTFOLIOS = {
    "demo_moderate": {
        "risk_profile": "moderate",
        "total_capital": 1_000_000.0,
        "holdings": [
            {"symbol": "TATASTEEL", "quantity": 400, "avg_price": 146.0, "sector": "Metals"},
            {"symbol": "JSWSTEEL", "quantity": 220, "avg_price": 885.0, "sector": "Metals"},
            {"symbol": "HDFCBANK", "quantity": 80, "avg_price": 1585.0, "sector": "Financials"},
        ],
    },
    "demo_aggressive": {
        "risk_profile": "aggressive",
        "total_capital": 2_500_000.0,
        "holdings": [
            {"symbol": "RELIANCE", "quantity": 90, "avg_price": 2840.0, "sector": "Energy"},
            {"symbol": "INFY", "quantity": 120, "avg_price": 1650.0, "sector": "Information Technology"},
        ],
    },
}

DEMO_BULK_DEALS = [
    {
        "symbol": "TATASTEEL",
        "deal_date": str(date.today() - timedelta(days=1)),
        "buyer": "Demo Institutional Fund",
        "quantity": 1_250_000,
        "price": 132.4,
        "deal_value_cr": 16.55,
    }
]

SECTOR_PROXY_MAP = {
    "Metals": "XME",
    "Energy": "XLE",
    "Financials": "XLF",
    "Information Technology": "XLK",
    "Healthcare": "XLV",
}
