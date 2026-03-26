from __future__ import annotations

from statistics import mean
from typing import Any
import logging

from supabase import Client, create_client
from postgrest.exceptions import APIError

from app.config import get_settings
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
                logging.error(f"Failed to fetch stock {normalized} from Supabase: {e}")
        return {"symbol": normalized, "name": normalized, "sector": "Unknown", "market_cap": 0.0, "is_fno": False}

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
                logging.error(f"Failed to fetch pattern {pattern_name} for {normalized} from Supabase: {e}")
        return {
            "total_occurrences": 0,
            "successful_occurrences": 0,
            "success_rate": 0.0,
            "avg_return_pct": 0.0,
        }

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
                logging.error(f"Failed to fetch user portfolio {user_id} from Supabase: {e}")
        return {"user_id": user_id, "risk_profile": "moderate", "total_capital": 0.0, "holdings": []}

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
                logging.error(f"Failed to fetch setup memory from Supabase: {e}")
        
        return self._aggregate_setup_memory(
            normalized=normalized,
            pattern_name=pattern_name,
            market_condition=market_condition,
            signal_stack=signal_stack,
            rows=[],
            source="none",
        )

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
            "exit_reason": payload.get("exit_reason"),
            "is_stop_loss_hit": payload.get("is_stop_loss_hit", False),
        }
        if self._client:
            try:
                result = self._client.table("recommendation_outcomes").insert(body).execute()
                return result.data[0] if result.data else body
            except APIError as e:
                logging.error(f"Failed to record outcome to Supabase: {e}")
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
                success_rate=0.0,
                avg_return_pct=0.0,
                target_hits=0,
                stop_loss_hits=0,
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
        stop_loss_count = sum(1 for row in sample_rows if row.get("is_stop_loss_hit"))
        target_hit_count = len(sample_rows) - stop_loss_count if sample_rows else 0

        return SetupMemory(
            symbol=normalized,
            pattern_name=pattern_name,
            market_condition=market_condition,
            signal_stack=signal_stack,
            similar_setups=len(regime_rows) or len(rows),
            exact_matches=len(exact_rows),
            success_rate=round(win_rate, 2),
            avg_return_pct=round(avg_return, 2),
            target_hits=target_hit_count,
            stop_loss_hits=stop_loss_count,
            source=source,
        )
