from __future__ import annotations

from math import isfinite

from app.data_sources import MarketDataService
from app.detectors.fundamental import get_fundamental_signals, get_fundamental_context
from app.models import (
    AgentState,
    Decision,
    EnrichedContext,
    FundamentalContext,
    FinalRecommendation,
    HistoricalContext,
    MarketContext,
    Personalization,
    SectorContext,
    Signal,
    SignalBundle,
    SetupMemory,
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
        total_score = 0.0

        deals, deal_source = self.market.get_bulk_deals(symbol)
        big_deal = next((deal for deal in deals if float(deal.get("deal_value_cr", 0)) > 10), None)
        if big_deal:
            signals.append(
                Signal(
                    signal_type="Block/Bulk Deal",
                    strength_score=0.7,
                    short_explanation=f"{big_deal['buyer']} bought Rs {big_deal['deal_value_cr']:.2f}cr",
                    source=deal_source,
                )
            )
            total_score += 0.7

        delivery_pct, avg_delivery_pct, delivery_source = self.market.get_delivery_pct(symbol, history)
        if delivery_pct > 60 and delivery_pct > avg_delivery_pct * 1.5:
            signals.append(
                Signal(
                    signal_type="Delivery Spike",
                    strength_score=0.6,
                    short_explanation=f"{delivery_pct:.0f}% delivery vs {avg_delivery_pct:.0f}% avg",
                    source=delivery_source,
                )
            )
            total_score += 0.6

        current_volume = float(history["volume"].iloc[-1]) if not history.empty else 0.0
        avg_volume = indicators.get("20d_vol_avg", 0.0)
        if avg_volume and current_volume > avg_volume * 2:
            signals.append(
                Signal(
                    signal_type="Volume Breakout",
                    strength_score=0.8,
                    short_explanation=f"{current_volume / avg_volume:.1f}x 20-day average volume",
                    source=history_result.source,
                )
            )
            total_score += 0.8

        stock_meta = self.repo.get_stock(symbol)
        current_price = float(history["close"].iloc[-1]) if not history.empty else 0.0
        if stock_meta.get("is_fno"):
            oi_support, oi_source = self.market.get_option_chain_support(symbol, current_price)
            if oi_support and oi_support >= current_price * 0.9:
                signals.append(
                    Signal(
                        signal_type="OI Buildup",
                        strength_score=0.6,
                        short_explanation=f"Put OI support near Rs {oi_support:.2f}",
                        source=oi_source,
                    )
                )
                total_score += 0.6

        breakout_level = indicators.get("prev_20d_high") or indicators.get("20d_high")
        if breakout_level and current_price >= breakout_level * 0.985:
            signals.append(
                Signal(
                    signal_type="Pattern Start",
                    strength_score=0.7,
                    short_explanation=f"Price at Rs {current_price:.2f} approaching breakout level Rs {breakout_level:.2f}",
                    source=history_result.source,
                )
            )
            total_score += 0.7

        fund_signals = get_fundamental_signals(symbol)
        for fs in fund_signals:
            signals.append(Signal(**fs))
            total_score += fs["strength_score"]

        state["signal_bundle"] = SignalBundle(symbol=symbol, signals=signals, total_score=total_score)
        return state

    def context_enricher(self, state: AgentState) -> AgentState:
        symbol = state["symbol"].upper()
        stock_meta = self.repo.get_stock(symbol)
        history = self.repo.get_pattern_success(symbol, "breakout")
        market = self.market.get_market_breadth()
        sector = self.market.get_sector_snapshot(stock_meta["sector"])
        fund_context_dict = get_fundamental_context(symbol)

        state["context"] = EnrichedContext(
            historical=HistoricalContext(
                similar_setups=int(history["total_occurrences"]),
                success_rate=float(history["success_rate"]),
                avg_return_pct=float(history["avg_return_pct"]),
                source="supabase" if self.repo.is_configured else str(history.get("source", "demo")),
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
            fundamental=FundamentalContext(**fund_context_dict),
        )
        return state

    def technical_analyzer(self, state: AgentState) -> AgentState:
        symbol = state["symbol"].upper()
        history_result = self.market.get_price_history(symbol)
        history = history_result.data
        indicators = self.market.compute_pattern_indicators(history)
        stock_meta = self.repo.get_stock(symbol)

        if history.empty:
            current_price = 100.0  # reasonable fallback
            resistance = 110.0
            support = 90.0
            avg_volume = 1000.0
            current_volume = 1000.0
            is_breakout = False
            near_support = False
            if not indicators:
                indicators = {"rsi": 50.0}
        else:
            current_price = float(history["close"].iloc[-1])
            resistance = float(indicators.get("prev_20d_high", current_price * 1.1))
            support = float(indicators.get("prev_20d_low", current_price * 0.9))
            avg_volume = float(indicators.get("prev_20d_vol_avg", 0.0))
            current_volume = float(history["volume"].iloc[-1])

            is_breakout = avg_volume > 0 and current_price >= resistance and current_volume >= avg_volume * 1.5
            near_support = current_price <= support * 1.03 and float(indicators.get("rsi", 50)) > 45

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
        signal_types = [signal.signal_type for signal in state["signal_bundle"].signals]
        state["setup_memory"] = self.repo.get_setup_memory(
            symbol=symbol,
            pattern_name=pattern_name,
            market_condition=state["context"].market.condition,
            signal_stack=signal_types,
        )
        return state

    def decision_engine(self, state: AgentState) -> AgentState:
        signal_bundle = state["signal_bundle"]
        context = state["context"]
        technicals = state["technicals"]
        setup_memory = state.get(
            "setup_memory",
            SetupMemory(
                symbol=state["symbol"],
                pattern_name=technicals.pattern.name,
                market_condition=context.market.condition,
                signal_stack=[signal.signal_type for signal in signal_bundle.signals],
            ),
        )

        fund = context.fundamental
        fundamental_score = 0.5
        if fund:
            if fund.revenue_growth and fund.revenue_growth > 10: fundamental_score += 0.2
            if fund.pe_ratio and fund.pe_ratio < 30: fundamental_score += 0.1
            if fund.roce and fund.roce > 15: fundamental_score += 0.2
            if fund.debt_to_equity is not None and fund.debt_to_equity < 1.0: fundamental_score += 0.1
            if fund.profit_growth is not None and fund.profit_growth > 10: fundamental_score += 0.1
        fundamental_score = min(1.0, fundamental_score)

        signal_score = min(1.0, signal_bundle.total_score / 3.0) # Assume 3 max aligned
        context_score = (
            context.historical.success_rate * 0.4
            + context.sector.strength * 0.2
            + min(context.market.breadth / 2, 1.0) * 0.2
            + fundamental_score * 0.2
        )
        technical_score = (technicals.pattern.success_rate * 0.6) + (setup_memory.success_rate * 0.4)
        if technicals.pattern.risk_reward_ratio >= 2:
            technical_score = min(1.0, technical_score + 0.08)
        if technicals.pattern.detected:
            technical_score = min(1.0, technical_score + 0.05)

        strong_signal_count = sum(1 for signal in signal_bundle.signals if signal.strength_score >= 0.7)
        aligned_market = context.sector.trend == "bullish" or context.market.condition == "risk_on"
        historical_edge = context.historical.success_rate >= 0.65
        technical_edge = technicals.pattern.detected or technicals.pattern.risk_reward_ratio >= 2
        
        if setup_memory.exact_matches >= 10 and setup_memory.success_rate >= 0.65:
            technical_score = min(1.0, technical_score + 0.05)

        if strong_signal_count >= 2 and aligned_market and historical_edge and technical_edge:
            conviction_mode = "HIGH_CONVICTION"
            confidence_bonus = 0.10
            confidence_note = "High conviction due to extreme alignment between signals and structural edge."
        elif strong_signal_count >= 1 and (aligned_market or historical_edge):
            conviction_mode = "ALIGNED"
            confidence_bonus = 0.05
            confidence_note = "Constructive evidence from multiple signals but waiting for further breakdown/breakout confirmation."
        else:
            conviction_mode = "NORMAL"
            confidence_bonus = 0.0
            confidence_note = "Weak composite signal setup."

        confidence = (signal_score * 0.3) + (context_score * 0.4) + (technical_score * 0.3)
        confidence = min(0.99, confidence + confidence_bonus)
        confidence = round(confidence, 2)

        if confidence >= 0.85:
            action = "High Conviction Buy"
            analyst_note = f"Identified {strong_signal_count} powerful structural signals aligned with a high-probability technical breakout. This is a top-tier setup."
        elif confidence >= 0.70:
            action = "Potential Buy"
            analyst_note = f"Constructive setup with {strong_signal_count} clear signals. Waiting for price to stabilize above resistance before full commitment."
        elif confidence >= 0.55:
            action = "Watch"
            analyst_note = f"Interesting pattern forming but currently lacks the institutional volume or fundamental momentum for a 'Buy' rating. Monitor for further expansion."
        else:
            action = "Avoid / Exit"
            analyst_note = f"Scanned for price, volume, and institutional clues but found 0 high-quality structural signals. Capital is better preserved elsewhere for now."

        lead_signal_text = ", ".join(f"{s.signal_type} ({s.short_explanation})" for s in signal_bundle.signals[:3]) or "No strong signals detected"
        reasons = [
            f"Signals: {lead_signal_text}",
            (
                f"Historical: {technicals.pattern.name} succeeded "
                f"{technicals.pattern.success_rate * 100:.0f}% with avg {technicals.pattern.avg_return_pct:.1f}% return"
            ),
            f"Memory: {setup_memory.narrative}",
            f"Context: Sector trend is {context.sector.trend} and market is {context.market.condition}",
        ]
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
            confidence_score=confidence,
            conviction_mode=conviction_mode,
            confidence_note=confidence_note,
            entry_price=technicals.entry_price,
            target_price=technicals.target_price,
            stop_loss=technicals.stop_loss,
            reasoning=" + ".join(reasons),
            analyst_note=analyst_note,
            setup_memory=setup_memory,
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

        risky_fundamentals = False
        if decision.action != "Avoid / Exit":
            fund = state["context"].fundamental
            if fund.pe_ratio and fund.pe_ratio > 50: risky_fundamentals = True
            if fund.debt_to_equity and fund.debt_to_equity > 2.0: risky_fundamentals = True
            
            if risky_fundamentals and sector_exposure_pct > 0.20:
                warning = f"High exposure to {stock_meta['sector']} combined with risky internal fundamentals (e.g. high PE/Debt). Reducing allocation."
                adjusted_allocation *= 0.25
        
        if decision.action == "Watch":
            adjusted_allocation *= 0.4
        elif decision.action == "Avoid / Exit":
            adjusted_allocation = 0.0

        next_step = {
            "High Conviction Buy": f"Execute full allocation near Rs {decision.entry_price:.2f}. Strong fundamental and technical alignment.",
            "Potential Buy": f"Place staggered entries near Rs {decision.entry_price:.2f} and trail stop at Rs {decision.stop_loss:.2f}",
            "Watch": f"Add to watchlist and trigger review only on breakout above Rs {decision.entry_price * 1.01:.2f}",
            "Avoid / Exit": "Skip for now and re-scan after new signals emerge",
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
            action={
                "High Conviction Buy": "BUY",
                "Potential Buy": "BUY",
                "Watch": "WATCH",
                "Avoid / Exit": "AVOID",
            }.get(decision.action, decision.action),
            confidence_score=decision.confidence_score,
            conviction_mode=decision.conviction_mode,
            confidence_note=decision.confidence_note,
            entry_price=decision.entry_price,
            target_price=decision.target_price,
            stop_loss=decision.stop_loss,
            reasoning=decision.reasoning,
            analyst_note=decision.analyst_note,
            setup_memory=decision.setup_memory,
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
            execution_mode="heuristic",
        )
        return state
