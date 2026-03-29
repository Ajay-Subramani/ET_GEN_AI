from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable

import numpy as np
import pandas as pd
import httpx
from pydantic import BaseModel, Field, ValidationError

from google import genai
from google.genai import types
from tools.screener import scrape_screener, discover_stocks

from app.config import get_settings
from app.data_sources import MarketDataService
from app.models import AgentStepTrace, AgentToolTrace, FinalRecommendation, SetupMemory
from app.repository import Repository
from app.detectors.fundamental import get_fundamental_context


class SignalAgentOutput(BaseModel):
    signal_summary: str
    detected_signals: list[str]
    signal_stack: list[str]
    pattern_hypothesis: str
    actionability: str


class ContextAgentOutput(BaseModel):
    context_summary: str
    market_condition: str
    sector_trend: str
    historical_edge: str
    fundamental_context: dict[str, Any] = Field(default_factory=dict)
    preferred_pattern: str


class DecisionAgentOutput(BaseModel):
    action: str
    conviction_mode: str
    confidence_pct: float
    confidence_note: str
    reasoning: str
    analyst_note: str
    confirmation_triggers: list[str]
    invalidation_triggers: list[str]
    watch_next: list[str]


class PortfolioAgentOutput(BaseModel):
    allocation_pct: float
    next_step: str
    personalization_note: str
    memo_narrative: str = ""
    warning: str | None = None


class RadarSignalOutput(BaseModel):
    id: str
    symbol: str
    category: str
    signal_type: str
    title: str
    description: str
    memo_narrative: str = ""
    confidence_pct: float
    detected_at: str
    source: str
    is_demo: bool = False
    explanation: str = Field(default="Agent-generated radar card.")


class RadarFeedOutput(BaseModel):
    radar_summary: str
    signals: list[RadarSignalOutput]
    agent_trace: list[AgentStepTrace] = Field(default_factory=list)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _to_json_safe(value.model_dump())
    if isinstance(value, pd.Series):
        return {str(key): _to_json_safe(item) for key, item in value.tail(5).items()}
    if isinstance(value, pd.DataFrame):
        return value.tail(5).to_dict(orient="records")
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(item) for item in value]
    return value


def _extract_json_payload(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model did not return a JSON object")
    return json.loads(cleaned[start : end + 1])


def _preview(value: Any, limit: int = 240) -> str:
    text = json.dumps(_to_json_safe(value), ensure_ascii=True, default=str)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


class AgentToolbox:
    def __init__(self) -> None:
        self.repo = Repository()
        self.market = MarketDataService()

    def get_fundamental_context(self, symbol: str) -> dict[str, Any]:
        return get_fundamental_context(symbol)

    def get_stock_metadata(self, symbol: str) -> dict[str, Any]:
        return self.repo.get_stock(symbol)

    def get_price_snapshot(self, symbol: str) -> dict[str, Any]:
        history_result = self.market.get_price_history(symbol)
        history = history_result.data
        indicators = self.market.compute_pattern_indicators(history)
        if history.empty:
            return {
                "symbol": symbol.upper(),
                "source": history_result.source,
                "available": False,
            }

        close = float(history["close"].iloc[-1])
        prev_close = float(history["close"].iloc[-2]) if len(history) > 1 else close
        return {
            "symbol": symbol.upper(),
            "source": history_result.source,
            "available": True,
            "current_price": round(close, 2),
            "daily_change_pct": round(((close / prev_close) - 1) * 100, 2) if prev_close else 0.0,
            "prev_20d_high": round(float(indicators.get("prev_20d_high", close)), 2),
            "prev_20d_low": round(float(indicators.get("prev_20d_low", close)), 2),
            "prev_20d_vol_avg": round(float(indicators.get("prev_20d_vol_avg", 0.0)), 2),
            "current_volume": round(float(history["volume"].iloc[-1]), 2),
            "rsi": round(float(indicators.get("rsi", 50.0)), 2),
        }

    def get_signal_facts(self, symbol: str) -> dict[str, Any]:
        history_result = self.market.get_price_history(symbol)
        history = history_result.data
        indicators = self.market.compute_pattern_indicators(history)
        stock_meta = self.repo.get_stock(symbol)

        current_price = float(history["close"].iloc[-1]) if not history.empty else 0.0
        current_volume = float(history["volume"].iloc[-1]) if not history.empty else 0.0
        avg_volume = float(indicators.get("20d_vol_avg", 0.0))

        deals, deal_source = self.market.get_bulk_deals(symbol)
        bulk_deal = next((deal for deal in deals if float(deal.get("deal_value_cr", 0)) > 10), None)

        delivery_pct, avg_delivery_pct, delivery_source = self.market.get_delivery_pct(symbol, history)
        oi_support, oi_source = (
            self.market.get_option_chain_support(symbol, current_price) if stock_meta.get("is_fno") else (None, "n/a")
        )

        breakout_level = indicators.get("prev_20d_high") or indicators.get("20d_high")
        pattern_start = bool(breakout_level and current_price >= breakout_level * 0.985)
        volume_breakout = bool(avg_volume and current_volume > avg_volume * 2)

        candidate_signals = []
        if bulk_deal:
            candidate_signals.append("bulk_deal")
        if delivery_pct > 60 and delivery_pct > avg_delivery_pct * 1.5:
            candidate_signals.append("delivery_spike")
        if volume_breakout:
            candidate_signals.append("volume_breakout")
        if oi_support and oi_support >= current_price * 0.9:
            candidate_signals.append("oi_buildup")
        if pattern_start:
            candidate_signals.append("pattern_start")

        return {
            "symbol": symbol.upper(),
            "candidate_signals": candidate_signals,
            "bulk_deal": bulk_deal,
            "bulk_deal_source": deal_source,
            "delivery_pct": round(delivery_pct, 2),
            "avg_delivery_pct": round(avg_delivery_pct, 2),
            "delivery_source": delivery_source,
            "volume_breakout": volume_breakout,
            "current_volume": round(current_volume, 2),
            "avg_volume": round(avg_volume, 2),
            "pattern_start": pattern_start,
            "breakout_level": round(float(breakout_level), 2) if breakout_level else None,
            "oi_support": round(float(oi_support), 2) if oi_support else None,
            "oi_source": oi_source,
            "market_data_source": history_result.source,
        }

    def get_market_context(self, symbol: str) -> dict[str, Any]:
        stock_meta = self.repo.get_stock(symbol)
        sector = self.market.get_sector_snapshot(stock_meta["sector"])
        market = self.market.get_market_breadth()
        return {
            "symbol": symbol.upper(),
            "sector": stock_meta["sector"],
            "sector_context": sector,
            "market_context": market,
        }

    def get_historical_edge(self, symbol: str, pattern_name: str) -> dict[str, Any]:
        return self.repo.get_pattern_success(symbol, pattern_name)

    def get_setup_memory(self, symbol: str, pattern_name: str, market_condition: str, signal_stack: list[str]) -> dict[str, Any]:
        return self.repo.get_setup_memory(symbol, pattern_name, market_condition, signal_stack).model_dump()

    def get_trade_levels(self, symbol: str, pattern_name: str | None = None) -> dict[str, Any]:
        history_result = self.market.get_price_history(symbol)
        history = history_result.data
        indicators = self.market.compute_pattern_indicators(history)
        stock_meta = self.repo.get_stock(symbol)

        if history.empty:
            current_price = 100.0
            support = 90.0
            resistance = 110.0
            avg_volume = 1000.0
            current_volume = 1000.0
            rsi = 50.0
        else:
            current_price = float(history["close"].iloc[-1])
            support = float(indicators.get("prev_20d_low", current_price * 0.95))
            resistance = float(indicators.get("prev_20d_high", current_price * 1.05))
            avg_volume = float(indicators.get("prev_20d_vol_avg", 0.0))
            current_volume = float(history["volume"].iloc[-1])
            rsi = float(indicators.get("rsi", 50.0))

        is_breakout = avg_volume > 0 and current_price >= resistance and current_volume >= avg_volume * 1.5
        near_support = current_price <= support * 1.03 and rsi > 45

        resolved_pattern = pattern_name or ("breakout" if is_breakout else "support_bounce" if near_support else "breakout")
        success = self.repo.get_pattern_success(symbol, resolved_pattern)
        oi_support, oi_source = (
            self.market.get_option_chain_support(symbol, current_price) if stock_meta.get("is_fno") else (None, "n/a")
        )

        stop_loss = min(filter(lambda x: x is not None and isfinite(x), [support, oi_support, current_price * 0.95]))
        target_price = stop_loss + (current_price - stop_loss) * 2
        risk_reward = (target_price - current_price) / max(current_price - stop_loss, 0.01)

        return {
            "symbol": symbol.upper(),
            "pattern_name": resolved_pattern,
            "detected": is_breakout or near_support,
            "current_price": round(current_price, 2),
            "support": round(float(support), 2),
            "resistance": round(float(resistance), 2),
            "oi_support": round(float(oi_support), 2) if oi_support else None,
            "entry_price": round(current_price, 2),
            "target_price": round(target_price, 2),
            "stop_loss": round(float(stop_loss), 2),
            "risk_reward_ratio": round(float(risk_reward), 2),
            "success_rate": float(success["success_rate"]),
            "avg_return_pct": float(success["avg_return_pct"]),
            "source": "supabase+technical" if self.repo.is_configured else f"demo+{oi_source}",
        }

    def get_user_portfolio(self, user_id: str) -> dict[str, Any]:
        return self.repo.get_user_portfolio(user_id)

    def compute_portfolio_personalization(self, symbol: str, user_id: str, action: str, entry_price: float) -> dict[str, Any]:
        stock_meta = self.repo.get_stock(symbol)
        portfolio = self.repo.get_user_portfolio(user_id)

        risk_profile = portfolio["risk_profile"]
        capital = float(portfolio["total_capital"])
        max_allocation_map = {"aggressive": 0.10, "moderate": 0.05, "conservative": 0.02}
        base_allocation = max_allocation_map.get(risk_profile, 0.05)

        holdings = portfolio.get("holdings", [])
        same_sector = [holding for holding in holdings if holding.get("sector") == stock_meta["sector"]]
        sector_value = 0.0
        for holding in same_sector:
            market_price = entry_price if holding["symbol"] == symbol else float(holding.get("avg_price", 0))
            sector_value += float(holding["quantity"]) * market_price
        sector_exposure_pct = sector_value / capital if capital else 0.0

        warning = None
        adjusted_allocation = base_allocation
        if sector_exposure_pct > 0.30:
            adjusted_allocation *= 0.5
            warning = f"Sector exposure already high at {sector_exposure_pct * 100:.1f}% in {stock_meta['sector']}"

        if action == "WATCH":
            adjusted_allocation *= 0.4
        elif action == "AVOID":
            adjusted_allocation = 0.0

        next_step = {
            "BUY": f"Place staggered entries near Rs {entry_price:.2f} and trail stop using the generated risk plan.",
            "WATCH": f"Add to watchlist and re-check only if price confirms above Rs {entry_price * 1.01:.2f}.",
            "AVOID": "Skip deployment and re-scan once fresh signal alignment appears.",
        }.get(action, "Hold and re-evaluate.")

        return {
            "allocation_pct": round(adjusted_allocation * 100, 2),
            "allocation_amount": round(capital * adjusted_allocation, 2),
            "sector_exposure_pct": round(sector_exposure_pct * 100, 2),
            "warning": warning,
            "next_step": next_step,
            "risk_profile": risk_profile,
            "capital": capital,
            "source": portfolio.get("source", "supabase" if self.repo.is_configured else "demo"),
        }


def _normalize_confidence_pct(confidence_pct: float) -> float:
    value = float(confidence_pct)
    if not isfinite(value):
        return 0.0
    if value > 1.0:
        value = value / 100.0
    return max(0.0, min(value, 1.0))


class OllamaTextAgent:
    """Text-only agent path using local Ollama (no tool-calling; prefetch context)."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.toolbox = AgentToolbox()

    def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        timeout = self.settings.ollama_timeout_s
        payload = {
            "model": self.settings.ollama_text_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            # Newer Ollama versions support "format": "json" for strict JSON.
            "format": "json",
        }

        with httpx.Client(base_url=self.settings.ollama_base_url, timeout=timeout) as client:
            try:
                resp = client.post("/api/chat", json=payload)
                resp.raise_for_status()
                body = resp.json()
                message = body.get("message") or {}
                content = message.get("content") or body.get("response")
                if not content:
                    raise RuntimeError("Ollama chat response missing assistant content")
                return str(content)
            except httpx.HTTPStatusError as exc:
                # Some Ollama installs do not expose /api/chat (or reject "format").
                status = exc.response.status_code if exc.response is not None else None
                if status not in {404, 405, 400}:
                    raise
            except Exception:
                pass

            # Fallback for older endpoints that only support /api/generate.
            resp = client.post(
                "/api/generate",
                json={
                    "model": self.settings.ollama_text_model,
                    "stream": False,
                    "prompt": f"{system_prompt}\n\n{user_prompt}",
                    "format": "json",
                },
            )
            resp.raise_for_status()
            body = resp.json()
            content = body.get("response") or ""
            if not content:
                raise RuntimeError("Ollama generate response missing assistant content")
            return str(content)

    def run(self, symbol: str, user_id: str) -> FinalRecommendation:
        symbol = symbol.upper()
        stock_meta = self.toolbox.get_stock_metadata(symbol)
        price_snapshot = self.toolbox.get_price_snapshot(symbol)
        signal_facts = self.toolbox.get_signal_facts(symbol)
        market_context = self.toolbox.get_market_context(symbol)
        fundamental_context = self.toolbox.get_fundamental_context(symbol)

        market_condition = str(market_context.get("market_context", {}).get("condition", "neutral"))
        signal_stack = list(signal_facts.get("candidate_signals", []))

        trade_levels = self.toolbox.get_trade_levels(symbol)
        setup_memory = self.toolbox.repo.get_setup_memory(
            symbol,
            str(trade_levels.get("pattern_name", "breakout")),
            market_condition,
            signal_stack,
        )

        portfolio = self.toolbox.get_user_portfolio(user_id)
        entry_price = float(trade_levels.get("entry_price", 0.0) or 0.0)
        personalization_scenarios = {
            action: self.toolbox.compute_portfolio_personalization(symbol, user_id, action, entry_price)
            for action in ("BUY", "WATCH", "AVOID")
        }

        context_blob = {
            "symbol": symbol,
            "user_id": user_id,
            "stock_metadata": stock_meta,
            "price_snapshot": price_snapshot,
            "signal_facts": signal_facts,
            "market_context": market_context,
            "fundamental_context": fundamental_context,
            "trade_levels": trade_levels,
            "setup_memory": setup_memory.model_dump(),
            "user_portfolio": portfolio,
            "personalization_scenarios": personalization_scenarios,
        }

        system_prompt = (
            "You are the Alpha Investment Agent for Indian equities. "
            "You are given pre-fetched market and portfolio context as JSON. "
            "Do not ask for tools. Do not output markdown. Output strict JSON only."
        )
        user_prompt = (
            "Using ONLY the provided context JSON, produce a single JSON object with keys:\n"
            "- signal: {signal_summary, detected_signals, signal_stack, pattern_hypothesis, actionability}\n"
            "- context: {context_summary, market_condition, sector_trend, historical_edge, fundamental_context, preferred_pattern}\n"
            "- decision: {action, conviction_mode, confidence_pct, confidence_note, reasoning, analyst_note, confirmation_triggers, invalidation_triggers, watch_next}\n"
            "- portfolio: {allocation_pct, next_step, personalization_note, memo_narrative, warning}\n\n"
            "Rules:\n"
            "- decision.action must be one of BUY, WATCH, AVOID.\n"
            "- decision.confidence_pct must be a number (0-100 preferred).\n"
            "- portfolio.allocation_pct must match the allocation_pct from personalization_scenarios for the chosen action.\n"
            "- Keep explanations mentor-style, plain English, and evidence-based.\n\n"
            f"CONTEXT_JSON={json.dumps(_to_json_safe(context_blob), ensure_ascii=True)}"
        )

        raw = self._call_ollama(system_prompt=system_prompt, user_prompt=user_prompt)
        payload = _extract_json_payload(raw)

        signal_output = SignalAgentOutput.model_validate(payload.get("signal", {}))
        context_output = ContextAgentOutput.model_validate(payload.get("context", {}))
        decision_output = DecisionAgentOutput.model_validate(payload.get("decision", {}))
        portfolio_output = PortfolioAgentOutput.model_validate(payload.get("portfolio", {}))

        pattern_name = context_output.preferred_pattern or str(trade_levels.get("pattern_name") or "breakout")
        trade_levels = self.toolbox.get_trade_levels(symbol, pattern_name)
        setup_memory = self.toolbox.repo.get_setup_memory(
            symbol,
            pattern_name,
            context_output.market_condition or market_condition,
            signal_output.signal_stack or signal_stack,
        )

        personalization = personalization_scenarios.get(decision_output.action) or self.toolbox.compute_portfolio_personalization(
            symbol=symbol,
            user_id=user_id,
            action=decision_output.action,
            entry_price=float(trade_levels["entry_price"]),
        )

        confidence_score = _normalize_confidence_pct(decision_output.confidence_pct)
        trace = AgentStepTrace(
            step_name="ollama_text_agent",
            objective="Generate a text-only recommendation using pre-fetched context (no tool-calling).",
            thought="Prefetched market, fundamentals, memory, and portfolio context; requested strict JSON recommendation.",
            model=self.settings.ollama_text_model,
            tool_calls=[],
            output_summary=_preview(payload),
        )

        return FinalRecommendation(
            symbol=symbol,
            user_id=user_id,
            action=decision_output.action,
            confidence_score=confidence_score,
            conviction_mode=decision_output.conviction_mode,
            confidence_note=decision_output.confidence_note,
            entry_price=float(trade_levels["entry_price"]),
            target_price=float(trade_levels["target_price"]),
            stop_loss=float(trade_levels["stop_loss"]),
            reasoning=decision_output.reasoning,
            analyst_note=decision_output.analyst_note,
            setup_memory=setup_memory,
            fundamental_context=context_output.fundamental_context,
            allocation_pct=float(personalization["allocation_pct"]),
            allocation_amount=float(personalization["allocation_amount"]),
            sector_exposure_pct=float(personalization["sector_exposure_pct"]),
            personalization_warning=portfolio_output.warning or personalization.get("warning"),
            next_step=portfolio_output.next_step or str(personalization["next_step"]),
            memo_narrative=portfolio_output.memo_narrative,
            watch_next=decision_output.watch_next,
            confirmation_triggers=decision_output.confirmation_triggers,
            invalidation_triggers=decision_output.invalidation_triggers,
            sources={
                "signals": ["ollama_text_agent", signal_facts.get("market_data_source", "demo")],
                "historical": setup_memory.source,
                "sector": market_context.get("sector_context", {}).get("source", stock_meta.get("source", "demo")),
                "market": market_context.get("market_context", {}).get("source", "demo"),
                "technical": trade_levels["source"],
            },
            execution_mode="ollama_text_agent",
            agent_trace=[trace],
        )

    def run_signal_radar(self, symbols: list[str] | None = None, limit: int = 10) -> RadarFeedOutput:
        watchlist = [symbol.upper() for symbol in (symbols or []) if symbol][:10]
        if not watchlist:
            try:
                watchlist = list(discover_stocks.invoke({"query": "Volume > 500000 AND Price > 100"}))[:10]
            except Exception as exc:
                logging.warning("Ollama radar discovery failed: %s", exc)
                watchlist = []

        if not watchlist:
            watchlist = ["RELIANCE", "TATASTEEL", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "BHARTIARTL", "ITC"]

        per_symbol: list[dict[str, Any]] = []
        for symbol in watchlist:
            try:
                per_symbol.append(
                    {
                        "symbol": symbol,
                        "price_snapshot": self.toolbox.get_price_snapshot(symbol),
                        "signal_facts": self.toolbox.get_signal_facts(symbol),
                        "market_context": self.toolbox.get_market_context(symbol),
                        "fundamental_context": self.toolbox.get_fundamental_context(symbol),
                        "trade_levels": self.toolbox.get_trade_levels(symbol),
                    }
                )
            except Exception as exc:
                logging.warning("Ollama radar context build failed for %s: %s", symbol, exc)

        system_prompt = (
            "You are the Opportunity Radar Agent for Indian equities. "
            "You are given pre-fetched per-symbol context as JSON. "
            "Do not ask for tools. Do not output markdown. Output strict JSON only."
        )
        user_prompt = (
            "Create a radar feed as strict JSON with keys radar_summary and signals.\n"
            "Each signal must include id, symbol, category, signal_type, title, description, memo_narrative, "
            "confidence_pct, detected_at, source, is_demo, explanation.\n"
            f"Return at most {int(limit)} signals, ranked by tradeability.\n\n"
            f"CONTEXT_JSON={json.dumps(_to_json_safe({'symbols': watchlist, 'data': per_symbol}), ensure_ascii=True)}"
        )

        raw = self._call_ollama(system_prompt=system_prompt, user_prompt=user_prompt)
        payload = _extract_json_payload(raw)
        parsed = RadarFeedOutput.model_validate(payload)

        trace = AgentStepTrace(
            step_name="ollama_radar",
            objective="Generate a radar feed using pre-fetched context (no tool-calling).",
            thought="Prefetched symbol contexts; requested strict JSON radar feed.",
            model=self.settings.ollama_text_model,
            tool_calls=[],
            output_summary=_preview(payload),
        )

        return RadarFeedOutput(
            radar_summary=parsed.radar_summary,
            signals=parsed.signals[:limit],
            agent_trace=[trace],
        )


class GeminiToolAgent:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = genai.Client(api_key=self.settings.gemini_api_key)
        self.toolbox = AgentToolbox()

    def _call_model(
        self,
        instructions: str,
        user_prompt: str,
        output_model: type[BaseModel],
        tool_names: list[str],
        step_name: str,
        objective: str,
    ) -> tuple[BaseModel, AgentStepTrace]:
        specs = {
            "get_stock_metadata": self.toolbox.get_stock_metadata,
            "get_price_snapshot": self.toolbox.get_price_snapshot,
            "get_signal_facts": self.toolbox.get_signal_facts,
            "get_market_context": self.toolbox.get_market_context,
            "get_historical_edge": self.toolbox.get_historical_edge,
            "get_setup_memory": self.toolbox.get_setup_memory,
            "get_trade_levels": self.toolbox.get_trade_levels,
            "get_user_portfolio": self.toolbox.get_user_portfolio,
            "compute_portfolio_personalization": self.toolbox.compute_portfolio_personalization,
            "get_fundamental_context": scrape_screener,
            "discover_stocks": discover_stocks,
        }
        selected_tools = [specs[name] for name in tool_names]
        
        config = types.GenerateContentConfig(
            system_instruction=instructions,
            tools=selected_tools,
            response_mime_type="application/json",
            response_schema=output_model,
        )
        
        chat = self.client.chats.create(
            model=self.settings.gemini_model,
            config=config
        )
        
        tool_traces = []
        response = chat.send_message(user_prompt)
        
        for _ in range(self.settings.openai_max_tool_rounds):
            if response.function_calls:
                tool_responses = []
                for call in response.function_calls:
                    func = specs[call.name]
                    args = {k: v for k, v in call.args.items()}
                    result = func(**args)
                    safe_result = _to_json_safe(result)
                    
                    tool_traces.append(AgentToolTrace(
                        tool_name=call.name,
                        arguments=args,
                        output_preview=_preview(safe_result)
                    ))
                    
                    tool_responses.append(
                        types.Part.from_function_response(
                            name=call.name,
                            response=safe_result
                        )
                    )
                response = chat.send_message(tool_responses)
            else:
                break
                
        if response.function_calls:
            raise RuntimeError(f"{step_name} exceeded max tool rounds")
            
        try:
            parsed = output_model.model_validate_json(response.text)
        except Exception as e:
            try:
                parsed = output_model.model_validate(_extract_json_payload(response.text))
            except Exception as e2:
                raise e
            
        # Extract thought (any text before function calls or the final answer)
        thought = response.text if response.text else ""
        
        return parsed, AgentStepTrace(
            step_name=step_name,
            objective=objective,
            thought=thought,
            model=self.settings.gemini_model,
            tool_calls=tool_traces,
            output_summary=_preview(parsed.model_dump()),
        )


    def run(self, symbol: str, user_id: str) -> FinalRecommendation:
        symbol = symbol.upper()

        signal_output, signal_trace = self._call_model(
            instructions=(
                "You are the Alpha Investment Agent for Indian markets. Your goal is to detect high-conviction "
                "trading signals (Buy/Watch/Avoid) and explain them to non-technical users in plain English. "
                "DO NOT use technical trader slang (e.g., 'bags', 'to the moon', 'rekt', 'support/resistance' without explanation). "
                "Act like a wise mentor: explain 'The Why' (context), 'The Proof' (data points), and 'The How' (action). "
                "Always use real data from tools. Return strict JSON only."
            ),
            user_prompt=(
                f"Analyze symbol {symbol}. You must call get_stock_metadata, get_price_snapshot, and get_signal_facts "
                "before you answer. Return a compact JSON object with keys: signal_summary, detected_signals, "
                "signal_stack, pattern_hypothesis, actionability."
            ),
            output_model=SignalAgentOutput,
            tool_names=["get_stock_metadata", "get_price_snapshot", "get_signal_facts"],
            step_name="signal_detection",
            objective="Detect the strongest market and technical signals for the symbol.",
        )

        provisional_pattern = signal_output.pattern_hypothesis or "breakout"
        context_output, context_trace = self._call_model(
            instructions=(
                "You are the Context Enrichment Agent. Use tools to evaluate market regime, sector alignment, "
                "fundamental quality, historical edge, and setup memory. Return strict JSON only."
            ),
            user_prompt=(
                "Working inputs:\n"
                f"{json.dumps(signal_output.model_dump(), ensure_ascii=True)}\n\n"
                f"For symbol {symbol}, call get_market_context, get_fundamental_context, "
                f"get_historical_edge with pattern_name={provisional_pattern}, "
                "and get_setup_memory using the signal_stack from the prior step. Return JSON with keys: "
                "context_summary, market_condition, sector_trend, fundamental_context, historical_edge, preferred_pattern."
            ),
            output_model=ContextAgentOutput,
            tool_names=["get_market_context", "get_fundamental_context", "get_historical_edge", "get_setup_memory"],
            step_name="context_enrichment",
            objective="Enrich the raw signal with market regime, sector, history, and memory.",
        )

        pattern_name = context_output.preferred_pattern or provisional_pattern
        decision_output, decision_trace = self._call_model(
            instructions=(
                "You are the Trade Decision Agent. Convert the signal and context into an actionable trade view. "
                "Use tools to compute trade levels before deciding. Return strict JSON only."
            ),
            user_prompt=(
                "Signal analysis:\n"
                f"{json.dumps(signal_output.model_dump(), ensure_ascii=True)}\n\n"
                "Context analysis:\n"
                f"{json.dumps(context_output.model_dump(), ensure_ascii=True)}\n\n"
                f"Call get_trade_levels for symbol {symbol} and pattern_name={pattern_name}. Then return JSON with keys: "
                "action, conviction_mode, confidence_pct, confidence_note, reasoning, analyst_note, "
                "confirmation_triggers, invalidation_triggers, watch_next."
            ),
            output_model=DecisionAgentOutput,
            tool_names=["get_trade_levels"],
            step_name="decision_generation",
            objective="Generate an action with risk levels and confirmation/invalidation logic.",
        )

        trade_levels = self.toolbox.get_trade_levels(symbol, pattern_name)
        setup_memory = self.repo_get_setup_memory(symbol, pattern_name, context_output.market_condition, signal_output.signal_stack)

        portfolio_output, portfolio_trace = self._call_model(
            instructions=(
                "You are the Portfolio Personalization Agent. Adapt the trade for users based on their "
                "current holdings and capital. Explain why this specific opportunity fits or conflicts with their "
                "portfolio. Use a supportive, mentor-like tone. Include a 'memo_narrative' field with a 3-sentence "
                "plain English explanation that connects the market signal to the user's specific financial situation. "
                "Avoid technical jargon. Return strict JSON only."
            ),
            user_prompt=(
                "Decision analysis:\n"
                f"{json.dumps(decision_output.model_dump(), ensure_ascii=True)}\n\n"
                "Trade levels:\n"
                f"{json.dumps(trade_levels, ensure_ascii=True)}\n\n"
                f"For symbol {symbol} and user {user_id}, call get_user_portfolio and compute_portfolio_personalization "
                f"using action={decision_output.action} and entry_price={trade_levels['entry_price']}. Return JSON with keys: "
                "allocation_pct, next_step, personalization_note, warning."
            ),
            output_model=PortfolioAgentOutput,
            tool_names=["get_user_portfolio", "compute_portfolio_personalization"],
            step_name="portfolio_personalization",
            objective="Translate the trade idea into a portfolio-aware action plan.",
        )

        personalization = self.toolbox.compute_portfolio_personalization(
            symbol=symbol,
            user_id=user_id,
            action=decision_output.action,
            entry_price=float(trade_levels["entry_price"]),
        )
        stock_meta = self.toolbox.get_stock_metadata(symbol)
        market_context = self.toolbox.get_market_context(symbol)

        confidence_value = float(decision_output.confidence_pct)
        if not isfinite(confidence_value):
            confidence_value = 0.0
        if confidence_value > 1.0:
            confidence_value = confidence_value / 100.0

        return FinalRecommendation(
            symbol=symbol,
            user_id=user_id,
            action=decision_output.action,
            confidence_score=max(0.0, min(confidence_value, 1.0)),
            conviction_mode=decision_output.conviction_mode,
            confidence_note=decision_output.confidence_note,
            entry_price=float(trade_levels["entry_price"]),
            target_price=float(trade_levels["target_price"]),
            stop_loss=float(trade_levels["stop_loss"]),
            reasoning=decision_output.reasoning,
            analyst_note=decision_output.analyst_note,
            setup_memory=setup_memory,
            fundamental_context=context_output.fundamental_context,
            allocation_pct=float(personalization["allocation_pct"]),
            allocation_amount=float(personalization["allocation_amount"]),
            sector_exposure_pct=float(personalization["sector_exposure_pct"]),
            personalization_warning=portfolio_output.warning or personalization.get("warning"),
            next_step=portfolio_output.next_step or str(personalization["next_step"]),
            memo_narrative=portfolio_output.memo_narrative,
            watch_next=decision_output.watch_next,
            confirmation_triggers=decision_output.confirmation_triggers,
            invalidation_triggers=decision_output.invalidation_triggers,
            sources={
                "signals": ["llm_tool_agent", self.toolbox.get_signal_facts(symbol).get("market_data_source", "demo")],
                "historical": setup_memory.source,
                "sector": market_context["sector_context"].get("source", stock_meta.get("source", "demo")),
                "market": market_context["market_context"].get("source", "demo"),
                "technical": trade_levels["source"],
            },
            execution_mode="llm_tool_agent",
            agent_trace=[signal_trace, context_trace, decision_trace, portfolio_trace],
        )

    @property
    def repo(self) -> Repository:
        return self.toolbox.repo

    def repo_get_setup_memory(
        self, symbol: str, pattern_name: str, market_condition: str, signal_stack: list[str]
    ) -> SetupMemory:
        return self.repo.get_setup_memory(symbol, pattern_name, market_condition, signal_stack)

    def extract_portfolio_from_image(self, image_bytes: bytes) -> list[dict[str, Any]]:
        """Extract stock symbols and quantities from an image using Gemini Flash Vision."""
        try:
            prompt = (
                "You are an expert financial analyst. Analyze this portfolio screenshot and extract "
                "a list of stock symbols and their corresponding quantities. "
                "Return a JSON array of objects with keys: 'symbol' and 'quantity'. "
                "Focus on NSE/BSE symbols. Ignore profit/loss or other values."
            )
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash", # Use the latest flash model
                contents=[
                    prompt,
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png")
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                )
            )
            
            # The model returns a list of objects
            holdings = json.loads(response.text)
            if not isinstance(holdings, list):
                # Fallback if it's not a list
                if isinstance(holdings, dict) and "holdings" in holdings:
                    holdings = holdings["holdings"]
                else:
                    return []
            
            # Normalize symbols
            for h in holdings:
                if "symbol" in h:
                    h["symbol"] = str(h["symbol"]).upper().split(".")[0].split(":")[0].strip()
            
            return holdings
        except Exception as e:
            logging.error(f"Failed to extract portfolio from image: {e}")
            return []

    def run_signal_radar(self, symbols: list[str] | None = None, limit: int = 10) -> RadarFeedOutput:
        """Runs the fully autonomous radar scan for 5-10 top symbols discovered today."""
        # Step 0: Discovery
        symbols_to_scan = [symbol.upper() for symbol in (symbols or []) if symbol]
        discovery_trace = None
        if not symbols_to_scan:
            try:
                discovery_result, discovery_trace = self._call_model(
                    instructions="You are the Discovery Agent. Find the top 5-10 high-alpha NSE stocks to scan today using tools.",
                    user_prompt="Call discover_stocks(query='Volume > 1000000 AND Price > 100') and return exactly 5-10 symbols in a list.",
                    output_model=list[str],
                    tool_names=["discover_stocks"],
                    step_name="stock_discovery",
                    objective="Pick symbols with high trading activity for today's radar.",
                )
                symbols_to_scan = [str(sym).upper() for sym in discovery_result]
            except Exception as e:
                logging.warning("Autonomous discovery failed: %s. Falling back to static watchlist.", e)
                symbols_to_scan = []

        if not symbols_to_scan:
            symbols_to_scan = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

        prompt = (
            "You are the Opportunity Radar Agent for Indian equities. Use the provided tools to inspect each "
            f"symbol in this watchlist: {', '.join(symbols_to_scan)}. Focus on real alpha, not summarization. "
            "Return strict JSON only with keys radar_summary and signals. Each signal must include id, symbol, "
            "category, signal_type, title, description, memo_narrative, confidence_pct, detected_at, source, is_demo, explanation. "
            "The memo_narrative should be a 2-3 sentence 'mentor-style' investment insight in plain English."
            "Return at most 10 signals ranked by tradeability. Prefer technical, flow, and derivatives signals "
            "that have actionable confirmation or invalidation logic."
        )
        output, trace = self._call_model(
            instructions=(
                "You are an expert market scanning agent. Use tools for price, signal facts, market context, "
                "fundamental context, and trade levels before synthesizing a ranked radar feed. "
                "Avoid technical slang; focus on clear, evidence-based opportunities. Return JSON only."
            ),
            user_prompt=prompt,
            output_model=RadarFeedOutput,
            tool_names=[
                "get_signal_facts",
                "get_market_context",
                "get_price_snapshot",
                "get_trade_levels",
                "get_fundamental_context",
            ],
            step_name="radar_generation",
            objective="Generate a ranked opportunity radar with agent-style explanations.",
        )

        signals = output.signals[:limit]
        out_traces = [trace]
        if discovery_trace:
            out_traces.insert(0, discovery_trace)

        return RadarFeedOutput(
            radar_summary=output.radar_summary,
            signals=signals,
            agent_trace=out_traces,
        )


def build_signal_feed(symbols: list[str] | None = None) -> list[dict[str, Any]]:
    toolbox = AgentToolbox()
    if not symbols:
        try:
            symbols = discover_stocks.invoke({"query": "Volume > 500000 AND Price > 100"})
        except Exception as exc:
            logging.warning("Discovery tool failed: %s", exc)
            symbols = None
            
        if not symbols:
            symbols = ["RELIANCE", "TATASTEEL", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "BHARTIARTL", "ITC", "LT", "MARUTI"]
    
    watchlist = [symbol.upper() for symbol in (symbols or [])][:10]
    events: list[dict[str, Any]] = []

    for symbol in watchlist:
        added_for_symbol = False
        try:
            facts = toolbox.get_signal_facts(symbol)
            trade_levels = toolbox.get_trade_levels(symbol)
            market_context = toolbox.get_market_context(symbol)
            price_snapshot = toolbox.get_price_snapshot(symbol)

            detected_at = "2026-03-26T10:15:00+05:30"
            if facts["volume_breakout"]:
                events.append(
                    {
                        "id": f"sig_{symbol.lower()}_volume_breakout",
                        "symbol": symbol,
                        "category": "technical",
                        "signal_type": "volume_breakout",
                        "title": "Volume breakout confirmed",
                        "description": (
                            f"Volume is running {facts['current_volume'] / max(facts['avg_volume'], 1):.1f}x the recent average "
                            f"with RSI at {price_snapshot.get('rsi', 50)}."
                        ),
                        "confidence_pct": min(95, 60 + (facts["current_volume"] / max(facts["avg_volume"], 1)) * 10),
                        "detected_at": detected_at,
                        "source": facts["market_data_source"],
                        "is_demo": facts["market_data_source"] != "yfinance",
                        "explanation": "Volume and momentum confirmation from market history and RSI context.",
                    }
                )
                added_for_symbol = True

            if facts["pattern_start"]:
                events.append(
                    {
                        "id": f"sig_{symbol.lower()}_pattern_start",
                        "symbol": symbol,
                        "category": "technical",
                        "signal_type": "pattern_start",
                        "title": "Breakout setup forming",
                        "description": (
                            f"Price is near the prior 20-day high at Rs {facts['breakout_level']:.2f} "
                            f"with a projected stop at Rs {trade_levels['stop_loss']:.2f}."
                        ),
                        "confidence_pct": min(94, 65 + max(trade_levels["risk_reward_ratio"], 1) * 5),
                        "detected_at": detected_at,
                        "source": trade_levels["source"],
                        "is_demo": trade_levels["source"].startswith("demo"),
                        "explanation": "Breakout setup detected using prior high, entry, and stop-loss levels.",
                    }
                )
                added_for_symbol = True

            if facts["bulk_deal"]:
                events.append(
                    {
                        "id": f"sig_{symbol.lower()}_bulk_deal",
                        "symbol": symbol,
                        "category": "flow",
                        "signal_type": "bulk_deal",
                        "title": "Institutional block activity",
                        "description": f"{facts['bulk_deal']['buyer']} bought Rs {facts['bulk_deal']['deal_value_cr']:.2f}cr.",
                        "confidence_pct": 75,
                        "detected_at": detected_at,
                        "source": facts["bulk_deal_source"],
                        "is_demo": facts["bulk_deal_source"] != "nsepython",
                        "explanation": "Institutional flow is acting as confirmation for the setup.",
                    }
                )
                added_for_symbol = True

            if facts["oi_support"] is not None:
                events.append(
                    {
                        "id": f"sig_{symbol.lower()}_oi_buildup",
                        "symbol": symbol,
                        "category": "derivatives",
                        "signal_type": "oi_buildup",
                        "title": "Open interest support nearby",
                        "description": (
                            f"Put support is clustered near Rs {facts['oi_support']:.2f} while sector trend is "
                            f"{market_context['sector_context']['trend']}."
                        ),
                        "confidence_pct": 70,
                        "detected_at": detected_at,
                        "source": facts["oi_source"],
                        "is_demo": facts["oi_source"] != "nsepython",
                        "explanation": "Option-chain support is reinforcing the directional bias.",
                    }
                )
                added_for_symbol = True

            if not added_for_symbol:
                events.append(
                    {
                        "id": f"sig_{symbol.lower()}_demo_scan",
                        "symbol": symbol,
                        "category": "technical",
                        "signal_type": "pattern_start",
                        "title": "No confirmed signal yet",
                        "description": "The agent scanned price, flow, and derivatives tools but did not find an actionable setup.",
                        "confidence_pct": 42,
                        "detected_at": detected_at,
                        "source": facts["market_data_source"],
                        "is_demo": True,
                        "explanation": "Agent scanned the watchlist but no higher-conviction signal cleared the threshold.",
                    }
                )
        except Exception as exc:
            logging.warning("Radar fallback tool scan failed for %s: %s", symbol, exc)
            events.append(
                {
                    "id": f"sig_{symbol.lower()}_demo_pattern_start",
                    "symbol": symbol,
                    "category": "technical",
                    "signal_type": "pattern_start",
                    "title": "Breakout setup forming",
                    "description": "Demo fallback radar card generated because live market tools were unavailable.",
                    "confidence_pct": 68,
                    "detected_at": "2026-03-26T10:15:00+05:30",
                    "source": "demo",
                    "is_demo": True,
                    "explanation": "Tool access failed, so the agent surfaced a deterministic demo signal instead.",
                }
            )

    events.sort(key=lambda item: float(item["confidence_pct"]), reverse=True)
    return events[:10]


def run_llm_recommendation(symbol: str, user_id: str) -> FinalRecommendation:
    settings = get_settings()
    if settings.ollama_agent_enabled:
        return OllamaTextAgent().run(symbol, user_id)

    if settings.gemini_agent_enabled and settings.gemini_api_key:
        try:
            return GeminiToolAgent().run(symbol, user_id)
        except Exception as exc:
            logging.exception("Gemini LLM recommendation failed: %s", exc)
            raise

    raise RuntimeError("No text agent path is configured (ollama_agent_enabled is false and Gemini is not configured)")


def run_signal_radar(symbols: list[str] | None = None, limit: int = 10) -> RadarFeedOutput:
    settings = get_settings()
    if settings.ollama_agent_enabled:
        try:
            return OllamaTextAgent().run_signal_radar(symbols=symbols, limit=limit)
        except Exception as exc:
            logging.warning("Ollama Radar failed, falling back to heuristic: %s", exc)

    if settings.gemini_agent_enabled and settings.gemini_api_key:
        try:
            return GeminiToolAgent().run_signal_radar(symbols=symbols, limit=limit)
        except Exception as exc:
            logging.warning("Gemini Radar failed, falling back to heuristic: %s", exc)

    # Radar signal feed must use deterministic rules only as per Step 8
    radar_feed = build_signal_feed(symbols)
    return RadarFeedOutput(
        radar_summary="Backend deterministic radar feed generated from live tool data.",
        signals=[
            RadarSignalOutput(
                id=item["id"],
                symbol=item["symbol"],
                category=item["category"],
                signal_type=item["signal_type"],
                title=item["title"],
                description=item["description"],
                memo_narrative=item.get("memo_narrative", item["description"]),
                confidence_pct=float(item["confidence_pct"]),
                detected_at=str(item["detected_at"]),
                source=str(item["source"]),
                is_demo=bool(item.get("is_demo", False)),
                explanation="Deterministic heuristic generated from market tools.",
            )
            for item in radar_feed[:limit]
        ],
        agent_trace=[],
    )
