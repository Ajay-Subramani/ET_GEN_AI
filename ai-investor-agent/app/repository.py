from __future__ import annotations

from typing import Any

from supabase import Client, create_client

from app.config import get_settings
from app.demo_data import DEMO_PATTERN_SUCCESS, DEMO_STOCKS, DEMO_USER_PORTFOLIOS


class Repository:
    def __init__(self) -> None:
        settings = get_settings()
        self._client: Client | None = None
        if settings.supabase_url and settings.supabase_key:
            self._client = create_client(settings.supabase_url, settings.supabase_key)

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    def get_stock(self, symbol: str) -> dict[str, Any]:
        normalized = symbol.upper()
        if self._client:
            result = (
                self._client.table("stocks")
                .select("*")
                .eq("symbol", normalized)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
        return {"symbol": normalized, **DEMO_STOCKS.get(normalized, {
            "name": normalized,
            "sector": "Unknown",
            "market_cap": 0.0,
            "is_fno": False,
        })}

    def get_pattern_success(self, symbol: str, pattern_name: str) -> dict[str, Any]:
        normalized = symbol.upper()
        if self._client:
            result = (
                self._client.table("pattern_success_rates")
                .select("*")
                .eq("symbol", normalized)
                .eq("pattern_name", pattern_name)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
        return DEMO_PATTERN_SUCCESS.get(
            (normalized, pattern_name),
            {
                "total_occurrences": 10,
                "successful_occurrences": 6,
                "success_rate": 0.60,
                "avg_return_pct": 4.8,
            },
        )

    def get_user_portfolio(self, user_id: str) -> dict[str, Any]:
        if self._client:
            result = (
                self._client.table("user_portfolios")
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
        return {"user_id": user_id, **DEMO_USER_PORTFOLIOS.get(user_id, DEMO_USER_PORTFOLIOS["demo_moderate"])}
