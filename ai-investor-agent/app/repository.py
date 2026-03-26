from __future__ import annotations

from statistics import mean
from typing import Any
import logging

from supabase import Client, create_client
from postgrest.exceptions import APIError

from app.config import get_settings
from app.demo_data import (
    DEMO_PATTERN_SUCCESS,
    DEMO_RECOMMENDATION_OUTCOMES,
    DEMO_SETUP_MEMORY,
    DEMO_STOCKS,
    DEMO_USER_PORTFOLIOS,
)
from app.models import SetupMemory


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
            try:
                result = (
                    self._client.table("stocks")
                    .select("*")
                    .eq("symbol", normalized)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    return result.data[0]
            except APIError as e:
                logging.warning(f"Failed to fetch stock {normalized} from Supabase: {e}")
        return {"symbol": normalized, **DEMO_STOCKS.get(normalized, {
            "name": normalized,
            "sector": "Unknown",
            "market_cap": 0.0,
            "is_fno": False,
        })}

    def get_pattern_success(self, symbol: str, pattern_name: str) -> dict[str, Any]:
        normalized = symbol.upper()
        if self._client:
            try:
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
            except APIError as e:
                logging.warning(f"Failed to fetch pattern {pattern_name} for {normalized} from Supabase: {e}")
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
            try:
                result = (
                    self._client.table("portfolios")
                    .select("*")
                    .eq("user_id", user_id)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    return result.data[0]
            except APIError as e:
                logging.warning(f"Failed to fetch user portfolio {user_id} from Supabase: {e}")
        return {"user_id": user_id, **DEMO_USER_PORTFOLIOS.get(user_id, DEMO_USER_PORTFOLIOS["demo_moderate"])}

    def get_setup_memory(
        self,
        symbol: str,
        pattern_name: str,
        market_condition: str,
        signal_stack: list[str],
    ) -> SetupMemory:
        normalized = symbol.upper()
        if self._client:
            try:
                result = (
                    self._client.table("recommendation_outcomes")
                    .select("*")
                    .eq("symbol", normalized)
                    .eq("pattern_name", pattern_name)
                    .execute()
                )
                rows = result.data or []
                if rows:
                    return self._aggregate_setup_memory(
                        normalized=normalized,
                        pattern_name=pattern_name,
                        market_condition=market_condition,
                        signal_stack=signal_stack,
                        rows=rows,
                        source="supabase",
                    )
            except APIError as e:
                logging.warning(f"Failed to fetch setup memory from Supabase: {e}")

        rows = [
            row
            for row in DEMO_RECOMMENDATION_OUTCOMES
            if row["symbol"] == normalized and row["pattern_name"] == pattern_name
        ]
        memory = self._aggregate_setup_memory(
            normalized=normalized,
            pattern_name=pattern_name,
            market_condition=market_condition,
            signal_stack=signal_stack,
            rows=rows,
            source="demo",
        )
        demo_key = (normalized, pattern_name, market_condition)
        if demo_key in DEMO_SETUP_MEMORY:
            seeded = DEMO_SETUP_MEMORY[demo_key]
            memory.similar_setups = max(memory.similar_setups, seeded["similar_setups"])
            memory.exact_matches = max(memory.exact_matches, seeded["exact_matches"])
            memory.success_rate = round((memory.success_rate + seeded["success_rate"]) / 2, 2)
            memory.avg_return_pct = round((memory.avg_return_pct + seeded["avg_return_pct"]) / 2, 2)
            if not memory.signal_stack:
                memory.signal_stack = seeded["signal_stack"]
        return memory

    def record_outcome(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = {
            "user_id": payload["user_id"],
            "symbol": payload["symbol"].upper(),
            "pattern_name": payload["pattern_name"],
            "action": payload["action"],
            "market_condition": payload["market_condition"],
            "signal_stack": payload["signal_stack"],
            "entry_price": payload["entry_price"],
            "target_price": payload["target_price"],
            "stop_loss": payload["stop_loss"],
            "outcome_return_pct": payload["outcome_return_pct"],
            "outcome_horizon_days": payload["outcome_horizon_days"],
            "outcome_label": payload["outcome_label"],
        }
        if self._client:
            try:
                result = self._client.table("recommendation_outcomes").insert(body).execute()
                return result.data[0] if result.data else body
            except APIError as e:
                logging.warning(f"Failed to record outcome to Supabase: {e}")
        DEMO_RECOMMENDATION_OUTCOMES.append(body)
        return body

    def _aggregate_setup_memory(
        self,
        normalized: str,
        pattern_name: str,
        market_condition: str,
        signal_stack: list[str],
        rows: list[dict[str, Any]],
        source: str,
    ) -> SetupMemory:
        if not rows:
            return SetupMemory(
                symbol=normalized,
                pattern_name=pattern_name,
                market_condition=market_condition,
                signal_stack=signal_stack,
                similar_setups=0,
                exact_matches=0,
                success_rate=0.5,
                avg_return_pct=0.0,
                source=source,
            )

        requested = set(signal_stack)
        exact_rows = []
        regime_rows = []
        for row in rows:
            row_stack = set(row.get("signal_stack") or [])
            if row.get("market_condition") == market_condition:
                regime_rows.append(row)
                if requested and requested.issubset(row_stack):
                    exact_rows.append(row)

        sample_rows = exact_rows or regime_rows or rows
        win_rate = mean(1.0 if row.get("outcome_label") == "win" else 0.0 for row in sample_rows)
        avg_return = mean(float(row.get("outcome_return_pct", 0.0)) for row in sample_rows)
        return SetupMemory(
            symbol=normalized,
            pattern_name=pattern_name,
            market_condition=market_condition,
            signal_stack=signal_stack,
            similar_setups=len(regime_rows) or len(rows),
            exact_matches=len(exact_rows),
            success_rate=round(win_rate, 2),
            avg_return_pct=round(avg_return, 2),
            source=source,
        )
