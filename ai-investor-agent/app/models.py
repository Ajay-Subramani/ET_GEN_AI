from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


class Signal(BaseModel):
    type: str
    weight: int
    details: str
    source: str = "live"


class SignalBundle(BaseModel):
    symbol: str
    signals: list[Signal] = Field(default_factory=list)
    total_score: int = 0
    max_score: int = 10


class HistoricalContext(BaseModel):
    similar_setups: int = 0
    success_rate: float = 0.5
    avg_return_pct: float = 0.0
    source: str = "demo"


class SectorContext(BaseModel):
    trend: Literal["bullish", "neutral", "bearish"] = "neutral"
    strength: float = 0.5
    proxy: str | None = None
    source: str = "demo"


class MarketContext(BaseModel):
    breadth: float = 1.0
    condition: Literal["risk_on", "neutral", "risk_off"] = "neutral"
    nifty_trend: str = "sideways"
    volatility_regime: str = "normal"
    source: str = "demo"


class EnrichedContext(BaseModel):
    historical: HistoricalContext
    sector: SectorContext
    market: MarketContext


class TechnicalPattern(BaseModel):
    name: str
    detected: bool
    success_rate: float = 0.5
    avg_return_pct: float = 0.0
    support: float | None = None
    resistance: float | None = None
    oi_support: float | None = None
    risk_reward_ratio: float = 0.0
    details: str
    source: str = "live"


class TechnicalAnalysis(BaseModel):
    symbol: str
    current_price: float
    pattern: TechnicalPattern
    entry_price: float
    target_price: float
    stop_loss: float


class SetupMemory(BaseModel):
    symbol: str
    pattern_name: str
    market_condition: str
    signal_stack: list[str] = Field(default_factory=list)
    similar_setups: int = 0
    exact_matches: int = 0
    success_rate: float = 0.5
    avg_return_pct: float = 0.0
    source: str = "demo"

    @property
    def narrative(self) -> str:
        setup_scope = "this exact setup" if self.exact_matches else "similar setups"
        return (
            f"{setup_scope} appeared {max(self.exact_matches, self.similar_setups)} times, "
            f"won {self.success_rate * 100:.0f}% of the time, and averaged {self.avg_return_pct:.1f}%."
        )


class Decision(BaseModel):
    action: Literal["BUY", "WATCH", "AVOID"]
    confidence: float
    conviction_mode: Literal["HIGH_CONVICTION", "ALIGNED", "NORMAL"]
    confidence_note: str
    entry_price: float
    target_price: float
    stop_loss: float
    reasoning: str
    analyst_note: str
    setup_memory: SetupMemory
    watch_next: list[str] = Field(default_factory=list)
    confirmation_triggers: list[str] = Field(default_factory=list)
    invalidation_triggers: list[str] = Field(default_factory=list)


class Personalization(BaseModel):
    allocation_pct: float
    allocation_amount: float
    sector_exposure_pct: float
    warning: str | None = None
    next_step: str


class FinalRecommendation(BaseModel):
    symbol: str
    user_id: str
    action: str
    confidence_pct: float
    conviction_mode: str
    confidence_note: str
    entry_price: float
    target_price: float
    stop_loss: float
    reasoning: str
    analyst_note: str
    setup_memory: SetupMemory
    allocation_pct: float
    allocation_amount: float
    sector_exposure_pct: float
    personalization_warning: str | None = None
    next_step: str
    watch_next: list[str] = Field(default_factory=list)
    confirmation_triggers: list[str] = Field(default_factory=list)
    invalidation_triggers: list[str] = Field(default_factory=list)
    sources: dict[str, Any] = Field(default_factory=dict)

    @property
    def summary(self) -> str:
        return (
            f"Do {self.action} at Rs {self.entry_price:.2f} because {self.analyst_note}, "
            f"with confidence {self.confidence_pct:.1f}%."
        )


class AgentState(TypedDict, total=False):
    symbol: str
    user_id: str
    signal_bundle: SignalBundle
    context: EnrichedContext
    technicals: TechnicalAnalysis
    setup_memory: SetupMemory
    decision: Decision
    personalization: Personalization
    recommendation: FinalRecommendation
