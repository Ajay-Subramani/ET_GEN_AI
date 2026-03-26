from __future__ import annotations

from math import isfinite

from app.data_sources import MarketDataService
from app.models import (
    AgentState,
    Decision,
    EnrichedContext,
    FinalRecommendation,
    HistoricalContext,
    MarketContext,
    Personalization,
    SectorContext,
    Signal,
    SignalBundle,
    TechnicalAnalysis,
    TechnicalPattern,
)
from app.repository import Repository


class AnalystNodes:
    def __init__(self) -> None:
        self.repo = Repository()
        self.market = MarketDataService()

    def signal_detector(self, state: AgentState) -> AgentState:
        symbol = state["symbol"].upper()
        history_result = self.market.get_price_history(symbol)
        history = history_result.data
        indicators = self.market.compute_pattern_indicators(history)

        signals: list[Signal] = []
        total_score = 0

        deals, deal_source = self.market.get_bulk_deals(symbol)
        big_deal = next((deal for deal in deals if float(deal.get("deal_value_cr", 0)) > 10), None)
        if big_deal:
            signals.append(
                Signal(
                    type="bulk_deal",
                    weight=2,
                    details=f"{big_deal['buyer']} bought Rs {big_deal['deal_value_cr']:.2f}cr",
                    source=deal_source,
                )
            )
            total_score += 2

        delivery_pct, avg_delivery_pct, delivery_source = self.market.get_delivery_pct(symbol, history)
        if delivery_pct > 60 and delivery_pct > avg_delivery_pct * 1.5:
            signals.append(
                Signal(
                    type="delivery_spike",
                    weight=2,
                    details=f"{delivery_pct:.0f}% delivery vs {avg_delivery_pct:.0f}% avg",
                    source=delivery_source,
                )
            )
            total_score += 2

        current_volume = float(history["volume"].iloc[-1]) if not history.empty else 0.0
        avg_volume = indicators.get("20d_vol_avg", 0.0)
        if avg_volume and current_volume > avg_volume * 2:
            signals.append(
                Signal(
                    type="volume_breakout",
                    weight=2,
                    details=f"{current_volume / avg_volume:.1f}x 20-day average volume",
                    source=history_result.source,
                )
            )
            total_score += 2

        stock_meta = self.repo.get_stock(symbol)
        current_price = float(history["close"].iloc[-1]) if not history.empty else 0.0
        if stock_meta.get("is_fno"):
            oi_support, oi_source = self.market.get_option_chain_support(symbol, current_price)
            if oi_support and oi_support >= current_price * 0.9:
                signals.append(
                    Signal(
                        type="oi_buildup",
                        weight=2,
                        details=f"Put OI support near Rs {oi_support:.2f}",
                        source=oi_source,
                    )
                )
                total_score += 2

        breakout_level = indicators.get("prev_20d_high") or indicators.get("20d_high")
        if breakout_level and current_price >= breakout_level * 0.985:
            signals.append(
                Signal(
                    type="pattern_start",
                    weight=2,
                    details=f"Price at Rs {current_price:.2f} approaching breakout level Rs {breakout_level:.2f}",
                    source=history_result.source,
                )
            )
            total_score += 2

        state["signal_bundle"] = SignalBundle(symbol=symbol, signals=signals, total_score=total_score)
        return state

    def context_enricher(self, state: AgentState) -> AgentState:
        symbol = state["symbol"].upper()
        stock_meta = self.repo.get_stock(symbol)
        history = self.repo.get_pattern_success(symbol, "breakout")
        market = self.market.get_market_breadth()
        sector = self.market.get_sector_snapshot(stock_meta["sector"])

        state["context"] = EnrichedContext(
            historical=HistoricalContext(
                similar_setups=int(history["total_occurrences"]),
                success_rate=float(history["success_rate"]),
                avg_return_pct=float(history["avg_return_pct"]),
                source="supabase" if self.repo.is_configured else "demo",
            ),
            sector=SectorContext(
                trend=sector["trend"],
                strength=float(sector["strength"]),
                proxy=sector.get("proxy"),
                source=sector["source"],
            ),
            market=MarketContext(
                breadth=float(market["breadth"]),
                condition=market["condition"],
                nifty_trend=market["nifty_trend"],
                volatility_regime=market["volatility_regime"],
                source=market["source"],
            ),
        )
        return state

    def technical_analyzer(self, state: AgentState) -> AgentState:
        symbol = state["symbol"].upper()
        history_result = self.market.get_price_history(symbol)
        history = history_result.data
        indicators = self.market.compute_pattern_indicators(history)
        stock_meta = self.repo.get_stock(symbol)

        current_price = float(history["close"].iloc[-1])
        resistance = float(indicators["prev_20d_high"])
        support = float(indicators["prev_20d_low"])
        avg_volume = float(indicators["prev_20d_vol_avg"])
        current_volume = float(history["volume"].iloc[-1])

        is_breakout = current_price >= resistance and current_volume >= avg_volume * 1.5
        near_support = current_price <= support * 1.03 and float(indicators["rsi"]) > 45

        if is_breakout:
            pattern_name = "breakout"
            details = (
                f"Price closed above 20-day high Rs {resistance:.2f} with "
                f"{current_volume / avg_volume:.1f}x volume confirmation"
            )
        elif near_support:
            pattern_name = "support_bounce"
            details = f"Price is rebounding near 20-day support Rs {support:.2f} with RSI {indicators['rsi']:.1f}"
        else:
            pattern_name = "breakout"
            details = f"Price is consolidating below resistance Rs {resistance:.2f}; breakout not confirmed yet"

        success = self.repo.get_pattern_success(symbol, pattern_name)
        oi_support, oi_source = (None, "n/a")
        if stock_meta.get("is_fno"):
            oi_support, oi_source = self.market.get_option_chain_support(symbol, current_price)

        stop_loss = min(filter(lambda x: x is not None and isfinite(x), [support, oi_support, current_price * 0.95]))
        target_price = stop_loss + (current_price - stop_loss) * 2
        risk_reward = (target_price - current_price) / max(current_price - stop_loss, 0.01)

        state["technicals"] = TechnicalAnalysis(
            symbol=symbol,
            current_price=current_price,
            pattern=TechnicalPattern(
                name=pattern_name,
                detected=is_breakout or near_support,
                success_rate=float(success["success_rate"]),
                avg_return_pct=float(success["avg_return_pct"]),
                support=support,
                resistance=resistance,
                oi_support=oi_support,
                risk_reward_ratio=risk_reward,
                details=details + (f"; option OI support at Rs {oi_support:.2f}" if oi_support else ""),
                source="supabase+technical" if self.repo.is_configured else f"demo+{oi_source}",
            ),
            entry_price=current_price,
            target_price=target_price,
            stop_loss=stop_loss,
        )
        return state

    def decision_engine(self, state: AgentState) -> AgentState:
        signal_bundle = state["signal_bundle"]
        context = state["context"]
        technicals = state["technicals"]

        signal_score = signal_bundle.total_score / signal_bundle.max_score
        context_score = (
            context.historical.success_rate * 0.6
            + context.sector.strength * 0.2
            + min(context.market.breadth / 2, 1.0) * 0.2
        )
        technical_score = technicals.pattern.success_rate
        if technicals.pattern.risk_reward_ratio >= 2:
            technical_score = min(1.0, technical_score + 0.08)
        if technicals.pattern.detected:
            technical_score = min(1.0, technical_score + 0.05)

        strong_signal_count = sum(1 for signal in signal_bundle.signals if signal.weight >= 2)
        aligned_market = context.sector.trend == "bullish" or context.market.condition == "risk_on"
        historical_edge = context.historical.success_rate >= 0.65
        technical_edge = technicals.pattern.detected or technicals.pattern.risk_reward_ratio >= 2
        if strong_signal_count >= 4 and aligned_market and historical_edge and technical_edge:
            conviction_mode = "HIGH_CONVICTION"
            confidence_bonus = 0.10
            confidence_note = "Confidence is high because signals, historical edge, technical structure, and market regime all align."
        elif strong_signal_count >= 3 and (aligned_market or historical_edge):
            conviction_mode = "ALIGNED"
            confidence_bonus = 0.05
            confidence_note = "Confidence is constructive because multiple layers align, but the setup still needs confirmation."
        else:
            conviction_mode = "NORMAL"
            confidence_bonus = 0.0
            confidence_note = "Confidence is measured because the setup is only partially aligned."

        confidence = (signal_score * 0.4) + (context_score * 0.3) + (technical_score * 0.3)
        confidence = min(0.99, confidence + confidence_bonus)
        confidence = round(confidence, 2)

        if confidence >= 0.8:
            action = "BUY"
        elif confidence >= 0.6:
            action = "WATCH"
        else:
            action = "AVOID"

        lead_signal_text = ", ".join(signal.details for signal in signal_bundle.signals[:3]) or "signal stack is weak"
        reasons = [
            lead_signal_text,
            (
                f"{technicals.pattern.name} historically succeeded "
                f"{technicals.pattern.success_rate * 100:.0f}% with avg {technicals.pattern.avg_return_pct:.1f}% return"
            ),
            f"sector trend is {context.sector.trend} and market is {context.market.condition}",
        ]
        analyst_note = (
            f"{signal_bundle.symbol} is showing {strong_signal_count} aligned signals: {lead_signal_text}. "
            f"Similar {technicals.pattern.name} setups worked {context.historical.success_rate * 100:.0f}% of the time, "
            f"with average follow-through near {context.historical.avg_return_pct:.1f}%. "
            f"{confidence_note}"
        )
        confirmation_triggers = [
            f"Breakout sustains above Rs {technicals.pattern.resistance:.2f}" if technicals.pattern.resistance else "Price confirms breakout",
            "Volume remains above the recent 20-day average",
            f"{context.market.condition.replace('_', ' ')} market regime stays intact",
        ]
        invalidation_triggers = [
            f"Price closes below Rs {technicals.stop_loss:.2f}",
            "Sector strength fades sharply",
            "Volume support disappears on the next advance",
        ]
        watch_next = [
            confirmation_triggers[0],
            confirmation_triggers[1],
            invalidation_triggers[0],
        ]

        state["decision"] = Decision(
            action=action,
            confidence=confidence,
            conviction_mode=conviction_mode,
            confidence_note=confidence_note,
            entry_price=technicals.entry_price,
            target_price=technicals.target_price,
            stop_loss=technicals.stop_loss,
            reasoning=" + ".join(reasons),
            analyst_note=analyst_note,
            watch_next=watch_next,
            confirmation_triggers=confirmation_triggers,
            invalidation_triggers=invalidation_triggers,
        )
        return state

    def personalizer(self, state: AgentState) -> AgentState:
        symbol = state["symbol"].upper()
        user_id = state["user_id"]
        decision = state["decision"]
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
            market_price = decision.entry_price if holding["symbol"] == symbol else float(holding.get("avg_price", 0))
            sector_value += float(holding["quantity"]) * market_price
        sector_exposure_pct = sector_value / capital if capital else 0.0

        warning = None
        adjusted_allocation = base_allocation
        if sector_exposure_pct > 0.30:
            adjusted_allocation *= 0.5
            warning = f"Sector exposure already high at {sector_exposure_pct * 100:.1f}% in {stock_meta['sector']}"

        if decision.action == "WATCH":
            adjusted_allocation *= 0.4
        elif decision.action == "AVOID":
            adjusted_allocation = 0.0

        next_step = {
            "BUY": f"Place staggered entries near Rs {decision.entry_price:.2f} and trail stop at Rs {decision.stop_loss:.2f}",
            "WATCH": f"Add to watchlist and trigger review only on breakout above Rs {decision.entry_price * 1.01:.2f}",
            "AVOID": "Skip for now and re-scan after new signals emerge",
        }[decision.action]

        state["personalization"] = Personalization(
            allocation_pct=adjusted_allocation,
            allocation_amount=capital * adjusted_allocation,
            sector_exposure_pct=sector_exposure_pct,
            warning=warning,
            next_step=next_step,
        )

        state["recommendation"] = FinalRecommendation(
            symbol=symbol,
            user_id=user_id,
            action=decision.action,
            confidence_pct=decision.confidence * 100,
            conviction_mode=decision.conviction_mode,
            confidence_note=decision.confidence_note,
            entry_price=decision.entry_price,
            target_price=decision.target_price,
            stop_loss=decision.stop_loss,
            reasoning=decision.reasoning,
            analyst_note=decision.analyst_note,
            allocation_pct=adjusted_allocation * 100,
            allocation_amount=capital * adjusted_allocation,
            sector_exposure_pct=sector_exposure_pct * 100,
            personalization_warning=warning,
            next_step=next_step,
            watch_next=decision.watch_next,
            confirmation_triggers=decision.confirmation_triggers,
            invalidation_triggers=decision.invalidation_triggers,
            sources={
                "signals": [signal.source for signal in state["signal_bundle"].signals],
                "historical": state["context"].historical.source,
                "sector": state["context"].sector.source,
                "market": state["context"].market.source,
                "technical": state["technicals"].pattern.source,
            },
        )
        return state
