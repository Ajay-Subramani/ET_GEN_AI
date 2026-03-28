from __future__ import annotations

from statistics import mean
from typing import Any
import logging

from supabase import Client, create_client
from postgrest.exceptions import APIError

from app.config import get_settings
from app.models import SetupMemory


class Repository:
    _demo_outcomes: list[dict[str, Any]] = []
    _demo_monitored: list[dict[str, Any]] = []  # in-memory fallback for monitored symbols

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
            except Exception as e:
                logging.error(f"Failed to fetch stock {normalized} from Supabase: {e}")
        
        sector = "Information Technology" if normalized in ["INFY", "TCS", "WIPRO"] else "Metals" if normalized in ["TATASTEEL", "HINDALCO"] else "Financials"
        return {
            "symbol": normalized, 
            "name": normalized, 
            "sector": sector, 
            "market_cap": 250000.0, 
            "is_fno": True,
            "source": "demo",
        }

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
            except Exception as e:
                logging.error(f"Failed to fetch pattern {pattern_name} for {normalized} from Supabase: {e}")
        
        win_rate = 0.55 + (len(symbol) % 3) * 0.05
        total_occ = 24 + len(symbol)
        return {
            "total_occurrences": total_occ,
            "successful_occurrences": int(total_occ * win_rate),
            "success_rate": round(win_rate, 2),
            "avg_return_pct": 2.5 + (len(symbol) % 4),
            "source": "demo"
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
            except Exception as e:
                logging.error(f"Failed to fetch user portfolio {user_id} from Supabase: {e}")
        
        return {
            "user_id": user_id, 
            "risk_profile": "aggressive", 
            "total_capital": 500000.0, 
            "holdings": [
                {"symbol": "INFY", "quantity": 50, "avg_price": 1400.0, "sector": "Information Technology"},
                {"symbol": "RELIANCE", "quantity": 25, "avg_price": 2800.0, "sector": "Energy"}
            ],
            "source": "demo",
        }

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
            except Exception as e:
                logging.error(f"Failed to fetch setup memory from Supabase: {e}")
        
        dummy_rows = [
            {"signal_stack": signal_stack, "market_condition": market_condition, "outcome_label": "win", "outcome_return_pct": 4.5, "is_stop_loss_hit": False},
            {"signal_stack": signal_stack, "market_condition": market_condition, "outcome_label": "win", "outcome_return_pct": 2.1, "is_stop_loss_hit": False},
            {"signal_stack": signal_stack, "market_condition": market_condition, "outcome_label": "loss", "outcome_return_pct": -1.5, "is_stop_loss_hit": True},
            {"signal_stack": signal_stack, "market_condition": "neutral", "outcome_label": "win", "outcome_return_pct": 3.0, "is_stop_loss_hit": False},
            {"signal_stack": [], "market_condition": market_condition, "outcome_label": "loss", "outcome_return_pct": -2.0, "is_stop_loss_hit": True},
        ] + [
            row
            for row in self._demo_outcomes
            if row.get("symbol") == normalized and row.get("pattern_name") == pattern_name
        ]
        
        return self._aggregate_setup_memory(
            normalized=normalized,
            pattern_name=pattern_name,
            market_condition=market_condition,
            signal_stack=signal_stack,
            rows=dummy_rows,
            source="demo",
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
            except Exception as e:
                logging.error(f"Failed to record outcome to Supabase: {e}")
        
        body["source"] = "demo"
        self._demo_outcomes.append(body.copy())
        return body

    def list_outcomes(self, symbol: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        normalized_symbol = symbol.upper() if symbol else None
        if self._client:
            try:
                query = self._client.table("recommendation_outcomes").select("*").order("created_at", desc=True).limit(limit)
                if normalized_symbol:
                    query = query.eq("symbol", normalized_symbol)
                result = query.execute()
                return result.data or []
            except Exception as e:
                logging.error(f"Failed to list outcomes from Supabase: {e}")

        demo_rows = [
            {
                "id": 1,
                "user_id": "demo_moderate",
                "symbol": "TATASTEEL",
                "pattern_name": "breakout",
                "action": "BUY",
                "market_condition": "risk_on",
                "signal_stack": ["bulk_deal", "delivery_spike", "oi_buildup", "pattern_start"],
                "entry_price": 132.5,
                "target_price": 148.0,
                "stop_loss": 125.0,
                "outcome_return_pct": 12.4,
                "outcome_horizon_days": 18,
                "outcome_label": "win",
                "created_at": "2026-03-26T09:15:00+05:30",
            },
            {
                "id": 2,
                "user_id": "demo_aggressive",
                "symbol": "TATASTEEL",
                "pattern_name": "breakout",
                "action": "BUY",
                "market_condition": "risk_on",
                "signal_stack": ["bulk_deal", "volume_breakout", "pattern_start"],
                "entry_price": 130.0,
                "target_price": 146.0,
                "stop_loss": 123.0,
                "outcome_return_pct": 9.1,
                "outcome_horizon_days": 12,
                "outcome_label": "win",
                "created_at": "2026-03-25T10:20:00+05:30",
            },
            {
                "id": 3,
                "user_id": "demo_moderate",
                "symbol": "TATASTEEL",
                "pattern_name": "breakout",
                "action": "WATCH",
                "market_condition": "risk_on",
                "signal_stack": ["delivery_spike", "pattern_start"],
                "entry_price": 128.0,
                "target_price": 140.0,
                "stop_loss": 121.0,
                "outcome_return_pct": -4.3,
                "outcome_horizon_days": 9,
                "outcome_label": "loss",
                "created_at": "2026-03-24T11:10:00+05:30",
            },
        ]

        rows = [row for row in (self._demo_outcomes + demo_rows) if not normalized_symbol or row.get("symbol") == normalized_symbol]
        rows.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
        return rows[:limit]

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
            source=source,
        )

    # ────────────────────────────── Monitored Symbols ──────────────────────────────

    def add_monitored_symbol(self, user_id: str, symbol: str, interval_minutes: int = 60) -> dict[str, Any]:
        """Add or update a monitored symbol for a user."""
        normalized = symbol.upper()
        record = {
            "user_id": user_id,
            "symbol": normalized,
            "interval_minutes": interval_minutes,
        }
        if self._client:
            try:
                result = (
                    self._client.table("monitored_symbols")
                    .upsert(record, on_conflict="user_id,symbol")
                    .execute()
                )
                return result.data[0] if result.data else record
            except Exception as e:
                logging.error(f"Failed to add monitored symbol {normalized}: {e}")

        # In-memory fallback
        existing = next((m for m in self._demo_monitored if m["user_id"] == user_id and m["symbol"] == normalized), None)
        if existing:
            existing["interval_minutes"] = interval_minutes
            return existing
        entry = {**record, "id": f"demo_{user_id}_{normalized}", "last_scanned_at": None, "latest_result": None, "created_at": "now", "source": "demo"}
        self._demo_monitored.append(entry)
        return entry

    def list_monitored_symbols(self, user_id: str) -> list[dict[str, Any]]:
        """List all monitored symbols for a user."""
        if self._client:
            try:
                result = (
                    self._client.table("monitored_symbols")
                    .select("*")
                    .eq("user_id", user_id)
                    .order("created_at", desc=True)
                    .execute()
                )
                return result.data or []
            except Exception as e:
                logging.error(f"Failed to list monitored symbols for {user_id}: {e}")

        return [m for m in self._demo_monitored if m["user_id"] == user_id]

    def remove_monitored_symbol(self, user_id: str, symbol: str) -> bool:
        """Remove a monitored symbol for a user."""
        normalized = symbol.upper()
        if self._client:
            try:
                self._client.table("monitored_symbols").delete().eq("user_id", user_id).eq("symbol", normalized).execute()
                return True
            except Exception as e:
                logging.error(f"Failed to remove monitored symbol {normalized}: {e}")

        before = len(self._demo_monitored)
        self._demo_monitored[:] = [m for m in self._demo_monitored if not (m["user_id"] == user_id and m["symbol"] == normalized)]
        return len(self._demo_monitored) < before

    def update_monitored_result(self, user_id: str, symbol: str, result_json: dict[str, Any]) -> None:
        """Store the latest scan result for a monitored symbol."""
        import json
        from datetime import datetime, timezone
        normalized = symbol.upper()
        now_iso = datetime.now(timezone.utc).isoformat()
        if self._client:
            try:
                self._client.table("monitored_symbols").update({
                    "latest_result": result_json,
                    "last_scanned_at": now_iso,
                }).eq("user_id", user_id).eq("symbol", normalized).execute()
                return
            except Exception as e:
                logging.error(f"Failed to update monitored result for {normalized}: {e}")

        existing = next((m for m in self._demo_monitored if m["user_id"] == user_id and m["symbol"] == normalized), None)
        if existing:
            existing["latest_result"] = result_json
            existing["last_scanned_at"] = now_iso

    def get_due_monitored_symbols(self) -> list[dict[str, Any]]:
        """Return all monitored symbols that are due for a rescan."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        rows: list[dict[str, Any]] = []
        if self._client:
            try:
                result = self._client.table("monitored_symbols").select("*").execute()
                rows = result.data or []
            except Exception as e:
                logging.error(f"Failed to fetch due monitored symbols: {e}")
                rows = list(self._demo_monitored)
        else:
            rows = list(self._demo_monitored)

        due = []
        for row in rows:
            last = row.get("last_scanned_at")
            interval = int(row.get("interval_minutes", 60))
            if last is None:
                due.append(row)
            else:
                try:
                    last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                    if now - last_dt >= timedelta(minutes=interval):
                        due.append(row)
                except Exception:
                    due.append(row)
        return due
