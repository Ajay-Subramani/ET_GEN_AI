from __future__ import annotations

from fastapi import FastAPI, Query, UploadFile, File, Form
from pydantic import BaseModel

from app.config import get_settings
from app.graph import run_recommendation
from app.llm_agents import run_signal_radar, GeminiToolAgent
from app.data_sources import MarketDataService
from app.repository import Repository
from app.scheduler import lifespan


app = FastAPI(title="AI Investor Agent", version="0.1.0", lifespan=lifespan)

class RecommendationRequest(BaseModel):
    symbol: str
    user_id: str


class OutcomeRequest(BaseModel):
    user_id: str
    symbol: str
    pattern_name: str
    action: str
    market_condition: str
    signal_stack: list[str]
    entry_price: float
    target_price: float
    stop_loss: float
    outcome_return_pct: float
    outcome_horizon_days: int
    outcome_label: str
    exit_reason: str | None = None
    is_stop_loss_hit: bool = False


class OutcomeListItem(BaseModel):
    id: int | str | None = None
    user_id: str
    symbol: str
    pattern_name: str
    action: str
    market_condition: str
    signal_stack: list[str]
    entry_price: float
    target_price: float
    stop_loss: float
    outcome_return_pct: float
    outcome_horizon_days: int
    outcome_label: str
    created_at: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "env": settings.app_env}


@app.get("/api/users")
def get_users() -> dict[str, object]:
    repo = Repository()
    return {
        "default_user_id": get_settings().default_user_id,
        "user_portfolio": repo.get_user_portfolio(get_settings().default_user_id),
    }


@app.post("/analyze")
def analyze(payload: RecommendationRequest) -> dict[str, object]:
    recommendation = run_recommendation(payload.symbol, payload.user_id)
    body = recommendation.model_dump()
    body["summary"] = recommendation.summary
    return body


@app.get("/signals")
def get_signals(limit: int = 10) -> dict[str, object]:
    radar = run_signal_radar(limit=limit)
    return radar.model_dump()


@app.get("/symbols/{symbol}/technicals")
def get_technicals(symbol: str) -> dict[str, object]:
    market = MarketDataService()
    history = market.get_price_history(symbol).data
    indicators = market.compute_pattern_indicators(history)
    return {
        "symbol": symbol.upper(),
        "indicators": indicators,
        "source": "yfinance" if not history.empty else "demo"
    }


@app.get("/memory/{symbol}")
def memory(
    symbol: str, 
    pattern_name: str, 
    market_condition: str = "neutral",
    signal_stack: list[str] = Query(default=[])
) -> dict[str, object]:
    repo = Repository()
    memory_snapshot = repo.get_setup_memory(symbol, pattern_name, market_condition, signal_stack)
    return memory_snapshot.model_dump()


@app.get("/outcomes")
def list_outcomes(symbol: str | None = None, limit: int = 20) -> list[dict[str, object]]:
    repo = Repository()
    outcomes = repo.list_outcomes(symbol=symbol, limit=limit)
    return [OutcomeListItem.model_validate(row).model_dump() for row in outcomes]


@app.post("/outcomes")
def record_outcome(payload: OutcomeRequest) -> dict[str, object]:
    repo = Repository()
    stored = repo.record_outcome(payload.model_dump())
    memory_snapshot = repo.get_setup_memory(
        symbol=payload.symbol,
        pattern_name=payload.pattern_name,
        market_condition=payload.market_condition,
        signal_stack=payload.signal_stack,
    )
    return {
        "stored_outcome": stored,
        "updated_memory": memory_snapshot.model_dump(),
    }


class MonitorRequest(BaseModel):
    user_id: str
    interval_minutes: int = 60


@app.post("/monitor/{symbol}")
def add_monitor(symbol: str, payload: MonitorRequest) -> dict[str, object]:
    """Add a symbol to the user's monitoring watchlist."""
    repo = Repository()
    entry = repo.add_monitored_symbol(payload.user_id, symbol, payload.interval_minutes)
    return {"monitored": entry}


@app.delete("/monitor/{symbol}")
def remove_monitor(symbol: str, user_id: str) -> dict[str, object]:
    """Remove a symbol from the user's monitoring watchlist."""
    repo = Repository()
    removed = repo.remove_monitored_symbol(user_id, symbol)
    return {"removed": removed, "symbol": symbol.upper()}


@app.get("/monitor")
def list_monitors(user_id: str) -> dict[str, object]:
    """List all monitored symbols for a user, with their latest scan results."""
    repo = Repository()
    entries = repo.list_monitored_symbols(user_id)
    return {"monitored_symbols": entries}


@app.post("/monitor/{symbol}/scan")
def scan_now(symbol: str, payload: MonitorRequest) -> dict[str, object]:
    """Trigger an immediate one-time scan for a symbol and store the result."""
    repo = Repository()
    # Ensure entry exists before scanning
    repo.add_monitored_symbol(payload.user_id, symbol, payload.interval_minutes)
    rec = run_recommendation(symbol, payload.user_id)
    result_json = rec.model_dump(mode="json")
    result_json["summary"] = rec.summary
    repo.update_monitored_result(payload.user_id, symbol, result_json)
    return {"symbol": symbol.upper(), "result": result_json}
@app.post("/api/portfolio/extract")
async def extract_portfolio(
    file: UploadFile = File(...), 
    user_id: str = Form(..., description="The ID of the user for whom to update the portfolio.")
) -> dict[str, object]:
    """Extract stock holdings from a portfolio screenshot and update the user's portfolio."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=400, detail="Gemini API key is not configured. Cannot extract portfolio from image."
        )

    content = await file.read()
    agent = GeminiToolAgent()
    holdings = agent.extract_portfolio_from_image(content)
    
    # Update Supabase repository
    repo = Repository()
    
    # user_id is now received directly from the form data
    effective_user_id = user_id
    
    # Clear old holdings and add new ones (or merge)
    # For simplicity, we replace with the detected ones
    repo.update_portfolio_holdings(effective_user_id, holdings)
    
    return {
        "extracted_holdings": holdings,
        "message": f"Successfully extracted {len(holdings)} holdings and updated portfolio."
    }
