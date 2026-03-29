# Ollama DeepSeek-R1 (7B) as text brain (Gemini for vision)

## Goal

Replace Gemini as the “brain” for **text-only agent paths** (recommendations + radar) with a local Ollama model (`deepseek-r1:7b`), while keeping **all vision functionality** (portfolio screenshot extraction) on Gemini.

## Scope

### In scope

- Backend: route text agent generation through Ollama:
  - `POST /analyze` → produces `FinalRecommendation`
  - `GET /signals` → produces radar feed
- Vision extraction stays on Gemini:
  - `POST /api/portfolio/extract` continues to use `GeminiToolAgent.extract_portfolio_from_image`
- Keep current deterministic heuristic fallbacks intact where they already exist.

### Out of scope

- Implementing model-side tool calling for Ollama (no function-call loop).
- Changing the API contract of existing endpoints.
- Modifying frontend behavior besides any required compatibility adjustments.

## Key design decision: “Prefetch context, no tool-calling”

Instead of having the model call tools, the backend will:

1. Gather all required inputs using existing Python tool/repo code (market data, memory, portfolio, trade levels, etc.).
2. Send a single prompt to Ollama that contains the context as JSON.
3. Require Ollama to return strict JSON matching existing output schemas (`SignalAgentOutput`, `ContextAgentOutput`, `DecisionAgentOutput`, `PortfolioAgentOutput`).

This minimizes implementation complexity and keeps the existing tool access / safety constraints server-side.

## Architecture changes

### Settings

Add Ollama settings to `ai-investor-agent/app/config.py`:

- `ollama_agent_enabled: bool` (default `True`)
- `ollama_base_url: str` (default `http://127.0.0.1:11434`)
- `ollama_text_model: str` (default `deepseek-r1:7b`)
- Optional timeout setting (seconds) for robustness.

Gemini settings remain for:

- vision extraction
- (optional) legacy text paths if toggled back on

### New module responsibilities

`ai-investor-agent/app/llm_agents.py`

- Add an `OllamaTextAgent` responsible for:
  - building “analysis context” by calling existing methods (repo/toolbox)
  - calling Ollama chat API
  - parsing JSON into existing Pydantic models
  - returning `FinalRecommendation` and `RadarFeedOutput`

### Switching logic

- Recommendation path:
  - `run_llm_recommendation()` prefers `OllamaTextAgent` when enabled
  - If Ollama is unreachable or returns invalid JSON, raise an exception and let the caller fall back to heuristics (existing behavior in `graph.py`)

- Radar path:
  - `run_signal_radar()` uses `OllamaTextAgent` when enabled
  - On failure, fall back to deterministic radar feed (existing behavior)

## Data flow: `/analyze`

1. Inputs: `symbol`, `user_id`
2. Backend collects:
   - `get_stock_metadata`, `get_price_snapshot`, `get_signal_facts`
   - `get_market_context`, `get_fundamental_context`, `get_historical_edge`, setup memory
   - `get_trade_levels`
   - portfolio + personalization details
3. Ollama prompt requests a single strict-JSON payload aligned with the final API response schema (or a multi-stage JSON object that is then mapped into `FinalRecommendation`).
4. Output: `FinalRecommendation` with `confidence_score` normalized to 0–1.

## Data flow: `/signals`

1. Inputs: optional symbols + `limit`
2. Backend collects the symbol list and per-symbol lightweight tool context
3. Ollama generates a radar summary + list of signals with the existing `RadarSignalOutput` schema
4. Output: `RadarFeedOutput`

## Error handling

- If Ollama is disabled, preserve current behavior.
- If Ollama request fails (connection refused/timeout/5xx) or response is not parseable JSON:
  - recommendation path: raise → existing heuristic fallback path executes
  - radar path: log warning → deterministic radar feed fallback

## Testing & verification

- Unit/integration:
  - Ensure tests still pass in environments without Ollama running (fallback path exercised).
  - Add targeted tests for “Ollama disabled” and “Ollama unreachable” behavior.
- Local manual:
  - Run Ollama with `deepseek-r1:7b` and verify `/analyze` returns a populated recommendation.

## Rollout plan

1. Add settings + Ollama client implementation behind `ollama_agent_enabled`.
2. Wire in `run_llm_recommendation` / `run_signal_radar` switches.
3. Verify fallbacks and existing endpoints.

