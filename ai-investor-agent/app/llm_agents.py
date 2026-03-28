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
    warning: str | None = None


class RadarSignalOutput(BaseModel):
    id: str
    symbol: str
    category: str
    signal_type: str
    title: str
    description: str
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
            "get_fundamental_context": self.toolbox.get_fundamental_context,
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
                "You are the Signal Detection Agent for an Indian equities trading workflow. "
                "Use the provided tools before answering. Focus on real tradeable signal quality, "
                "not summarization. Return strict JSON only."
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
                "You are the Portfolio Personalization Agent. Adapt the trade for the user's portfolio and risk profile. "
                "Use the portfolio tools before answering. Return strict JSON only."
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

        return FinalRecommendation(
            symbol=symbol,
            user_id=user_id,
            action=decision_output.action,
            confidence_pct=max(0.0, min(float(decision_output.confidence_pct), 99.0)),
            conviction_mode=decision_output.conviction_mode,
            confidence_note=decision_output.confidence_note,
            entry_price=float(trade_levels["entry_price"]),
            target_price=float(trade_levels["target_price"]),
            stop_loss=float(trade_levels["stop_loss"]),
            reasoning=decision_output.reasoning,
            analyst_note=decision_output.analyst_note,
            setup_memory=setup_memory,
            allocation_pct=float(personalization["allocation_pct"]),
            allocation_amount=float(personalization["allocation_amount"]),
            sector_exposure_pct=float(personalization["sector_exposure_pct"]),
            personalization_warning=portfolio_output.warning or personalization.get("warning"),
            next_step=portfolio_output.next_step or str(personalization["next_step"]),
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

    def run_signal_radar(self, symbols: list[str] | None = None, limit: int = 10) -> RadarFeedOutput:
        watchlist = [symbol.upper() for symbol in (symbols or ["TATASTEEL", "RELIANCE", "HDFCBANK", "INFY", "SUNPHARMA"])]
        prompt = (
            "You are the Opportunity Radar Agent for Indian equities. Use the provided tools to inspect each "
            f"symbol in this watchlist: {', '.join(watchlist)}. Focus on real alpha, not summarization. "
            "Return strict JSON only with keys radar_summary and signals. Each signal must include id, symbol, "
            "category, signal_type, title, description, confidence_pct, detected_at, source, is_demo, explanation. "
            f"Return at most {limit} signals ranked by tradeability. Prefer technical, flow, and derivatives signals "
            "that have actionable confirmation or invalidation logic."
        )
        output, trace = self._call_model(
            instructions=(
                "You are a market scanning agent. Use tools for price, signal facts, market context, and trade levels "
                "before synthesizing a ranked radar feed. Return JSON only."
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
        normalized_signals: list[RadarSignalOutput] = []
        for signal in signals:
            normalized_signals.append(signal)
        return RadarFeedOutput(
            radar_summary=output.radar_summary,
            signals=normalized_signals,
            agent_trace=[trace],
        )


def build_signal_feed(symbols: list[str] | None = None) -> list[dict[str, Any]]:
    toolbox = AgentToolbox()
    watchlist = [symbol.upper() for symbol in (symbols or ["TATASTEEL", "RELIANCE", "HDFCBANK", "INFY", "SUNPHARMA"])]
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
    if not settings.gemini_agent_enabled or not settings.gemini_api_key:
        raise RuntimeError("Gemini agent path is not configured")

    try:
        return GeminiToolAgent().run(symbol, user_id)
    except Exception as exc:
        logging.exception("LLM agent recommendation failed: %s", exc)
        raise


def run_signal_radar(symbols: list[str] | None = None, limit: int = 10) -> RadarFeedOutput:
    settings = get_settings()
    if settings.gemini_agent_enabled and settings.gemini_api_key:
        try:
            return GeminiToolAgent().run_signal_radar(symbols, limit)
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
