# AI Investor Agent

Autonomous buy-side analyst workflow for Indian retail investors.

## What it does

Given an NSE symbol and a user ID, the system runs a 5-step agent flow:

1. Signal detection
2. Context enrichment
3. Technical analysis
4. Decision engine
5. Personalization

The final output is always shaped like:

`Do X at price Y because Z, with confidence W%`

The response also includes entry/target/stop-loss and a personalized allocation.

## Stack

- Python 3.11+
- LangGraph for orchestration
- Supabase/Postgres for state and historical stats
- yfinance + nsepython for Indian market data
- TA-Lib with custom fallbacks for technical detection
- FastAPI API layer
- Streamlit demo UI

## Capabilities Implemented (So Far)

### Step 1: Signal Detector

Implemented in `app/nodes.py` via `AnalystNodes.signal_detector()`.

- Bulk deal: uses `nsepython` bulk deals when available; demo fallback for `TATASTEEL` (`> Rs 10cr`) when unavailable.
- Delivery spike: mocked delivery% (explicitly marked as demo source).
- Volume breakout: current volume vs 20-day average volume.
- OI buildup (approx): for F&O stocks, finds a “Put OI support” strike from option-chain; demo fallback when NSE call fails.
- Pattern start: price approaching prior 20-day high breakout level.

Output: a `SignalBundle` with weighted signals and `total_score`.

### Step 2: Context Enricher

Implemented in `app/nodes.py` via `AnalystNodes.context_enricher()`.

- Historical success rates: queries Supabase `pattern_success_rates` (fallback to deterministic demo values).
- Sector trend: uses Yahoo Finance sector ETF proxies (fallback to demo strength).
- Market breadth/regime: uses `^NSEI` and `^INDIAVIX` on yfinance when available (fallback to demo “risk_on” snapshot).

Output: `EnrichedContext` with historical, sector, and market context.

### Step 3: Technical Analyzer

Implemented in `app/nodes.py` via `AnalystNodes.technical_analyzer()`.

- Detects patterns: `breakout` (prior 20-day high + volume confirmation), `support_bounce` (near prior 20-day low + RSI filter).
- Pulls pattern-specific historical success rate and avg return from `pattern_success_rates` (Supabase or demo).
- Pulls setup memory from stored `recommendation_outcomes` and blends it into the technical edge.
- Computes support/resistance from price history.
- Computes option OI “support” strike for F&O stocks when available (or demo).
- Computes risk/reward and enforces a 2:1 style target definition:
  - `stop_loss = recent support`
  - `target = stop_loss + 2 * (entry - stop_loss)`

Output: `TechnicalAnalysis` including entry/target/stop-loss and pattern stats.

### Step 4: Decision Engine

Implemented in `app/nodes.py` via `AnalystNodes.decision_engine()`.

- Confidence blend (0-1): signal score + context score + technical score.
- Non-linear conviction stacking:
  - `HIGH_CONVICTION`: strong signal cluster + aligned market + historical edge + technical edge + setup-memory support
  - `ALIGNED`: multiple layers line up but not enough for high-conviction framing
  - `NORMAL`: only partial alignment
- Decision rules:
  - `>= 0.80` -> `BUY`
  - `0.60 - 0.79` -> `WATCH`
  - `< 0.60` -> `AVOID`
- Output now includes:
  - analyst-style narrative
  - confidence explanation in trader language
  - confirmation triggers
  - invalidation triggers
  - watch-next checklist

Output: `Decision` with action, confidence, entry/target/stop-loss, reasoning.

### Step 5: Personalizer

Implemented in `app/nodes.py` via `AnalystNodes.personalizer()`.

- Loads user portfolio (`user_portfolios`) with fallback demo users.
- Sector exposure check:
  - if sector exposure `> 30%`, halves allocation and returns a warning.
- Risk profile sizing:
  - aggressive: max 10% per trade
  - moderate: max 5%
  - conservative: max 2%
- Adjustments:
  - `WATCH` reduces allocation further
  - `AVOID` allocates 0

Output: final `FinalRecommendation` including allocation and a single-line summary string:

`Do X at Rs Y because Z, with confidence W%.`

### Adaptive Memory Layer

Implemented in `app/repository.py` and surfaced in the final recommendation.

- Stores realized trade outcomes in `recommendation_outcomes`.
- Aggregates:
  - similar setups by symbol + pattern + market regime
  - exact matches by signal stack subset
- Produces memory statements like:
  - `this exact setup appeared 19 times, won 68% of the time, and averaged 11.2%`
- Works in both Supabase-backed mode and demo fallback mode.

### Orchestration

The pipeline is fully autonomous and sequential using LangGraph:

- `app/graph.py` builds the 5-node `StateGraph` and returns the final recommendation.

## API and UI

### FastAPI

Implemented in `app/main.py`.

- `GET /health`
- `GET /api/users`
- `GET /signals`
- `GET /symbols/{symbol}/technicals`
- `GET /memory/{symbol}` (query by `pattern_name`, `market_condition`, and `signal_stack`)
- `POST /analyze` (symbol + user_id -> full recommendation + `summary`)
- `POST /outcomes` (record realized trade outcome and return updated memory snapshot)

### Streamlit Demo

Implemented in `streamlit_app.py`.

- Pick a demo user and symbol, run analysis, view portfolio-aware recommendation and data sources used.

## Existing System Inventory

This section is the current implementation inventory for product, frontend, and integration work. It describes what is actually wired in code today, what contracts are stable enough for a frontend to consume, and what exists only at the schema/demo layer.

### 1. Systems Present in the Repository

#### LangGraph recommendation engine

- Entry point: `app/graph.py::run_recommendation(symbol, user_id)`
- Execution model: synchronous, 5-node sequential workflow
- Output contract: `FinalRecommendation` from `app/models.py`
- Use case: direct Python integration, internal jobs, and the FastAPI/Streamlit layers

#### FastAPI service layer

- File: `app/main.py`
- Use case: frontend/backend integration over HTTP
- Default FastAPI docs also exist at:
  - `GET /docs`
  - `GET /openapi.json`
- Auth: not implemented
- Async/background processing: not implemented

#### Streamlit demo frontend

- File: `streamlit_app.py`
- Use case: internal demo and operator UI
- Integration mode: calls Python modules directly, not the HTTP API

#### Repository and persistence layer

- File: `app/repository.py`
- Primary role: read stocks, historical pattern stats, user portfolios, setup memory, and write realized outcomes
- Persistence modes:
  - Supabase/Postgres when `SUPABASE_URL` and `SUPABASE_KEY` are configured
  - deterministic in-memory/demo fallback when unavailable

#### Market data adapter layer

- File: `app/data_sources.py`
- Live providers when available:
  - `yfinance`
  - `nsepython`
  - `TA-Lib`
- Fallback mode:
  - demo history
  - demo bulk deals
  - demo delivery percentages
  - demo market/sector snapshots
  - demo option-chain support

### 2. Functional Capabilities Implemented Today

#### Recommendation workflow

- Symbol normalization to uppercase
- 5-step recommendation flow:
  - signal detection
  - context enrichment
  - technical analysis
  - decisioning
  - portfolio-aware personalization
- Final actions supported:
  - `BUY`
  - `WATCH`
  - `AVOID`
- Conviction modes supported:
  - `HIGH_CONVICTION`
  - `ALIGNED`
  - `NORMAL`

#### Signal detection

Signals currently implemented in code:

- `bulk_deal`
- `delivery_spike`
- `volume_breakout`
- `oi_buildup`
- `pattern_start`

Each signal returned to callers includes:

- `type`
- `weight`
- `details`
- `source`

#### Context enrichment

- Historical pattern success lookup per symbol/pattern
- Sector trend and strength lookup via sector ETF proxy mapping
- Market breadth, Nifty trend, and volatility regime snapshot
- Returned context contains:
  - `historical`
  - `sector`
  - `market`

#### Technical analysis

Patterns currently recognized:

- `breakout`
- `support_bounce`

Derived technical outputs:

- current price
- pattern detected/not detected
- historical pattern success rate
- historical average return
- support
- resistance
- option OI support when available
- risk/reward ratio
- entry price
- target price
- stop loss

#### Adaptive memory

- Reads prior recommendation outcomes by symbol and pattern
- Filters by market regime
- Tracks exact signal-stack matches when the requested stack is a subset of a stored stack
- Produces:
  - `similar_setups`
  - `exact_matches`
  - `success_rate`
  - `avg_return_pct`
  - `signal_stack`
  - `source`
  - narrative text via `setup_memory.narrative`

#### Portfolio-aware personalization

- Reads a user portfolio by `user_id`
- Uses risk-profile-based max allocation
- Computes current same-sector exposure
- Reduces allocation if sector exposure exceeds `30%`
- Reduces allocation for `WATCH`
- Zero allocation for `AVOID`
- Returns:
  - `allocation_pct`
  - `allocation_amount`
  - `sector_exposure_pct`
  - `personalization_warning`
  - `next_step`

### 3. Frontend-Consumable APIs

These are the only HTTP endpoints implemented today.

#### `GET /health`

Purpose:
- service liveness and environment label

Response:
- `status`
- `env`

#### `GET /demo/users`

Purpose:
- bootstrap the demo frontend with a default user and portfolio payload

Response:
- `default_user_id`
- `demo_user`

Notes:
- despite the plural route name, this currently returns one default demo user payload, not a full user list

#### `POST /analyze`

Purpose:
- run the full 5-step recommendation workflow for a symbol and user

Request body:

```json
{
  "symbol": "TATASTEEL",
  "user_id": "demo_moderate"
}
```

Response body:

- Top-level trade decision:
  - `symbol`
  - `user_id`
  - `action`
  - `confidence_pct`
  - `conviction_mode`
  - `confidence_note`
- Price plan:
  - `entry_price`
  - `target_price`
  - `stop_loss`
- Explanation fields:
  - `reasoning`
  - `analyst_note`
  - `summary`
- Memory block:
  - `setup_memory.symbol`
  - `setup_memory.pattern_name`
  - `setup_memory.market_condition`
  - `setup_memory.signal_stack`
  - `setup_memory.similar_setups`
  - `setup_memory.exact_matches`
  - `setup_memory.success_rate`
  - `setup_memory.avg_return_pct`
  - `setup_memory.source`
- Personalization block:
  - `allocation_pct`
  - `allocation_amount`
  - `sector_exposure_pct`
  - `personalization_warning`
  - `next_step`
- UX helper lists:
  - `watch_next`
  - `confirmation_triggers`
  - `invalidation_triggers`
- Source provenance:
  - `sources.signals`
  - `sources.historical`
  - `sources.sector`
  - `sources.market`
  - `sources.technical`

Frontend guidance:

- This is the main endpoint a web or mobile client should use.
- The response already contains presentational helper text (`summary`, `confidence_note`, `analyst_note`, `next_step`) in addition to raw numbers.
- No pagination, batching, streaming, or websocket updates are implemented.

#### `GET /memory/{symbol}`

Purpose:
- retrieve setup-memory statistics for one symbol/pattern/regime combination

Path parameter:
- `symbol`

Query parameters:
- `pattern_name` (required)
- `market_condition` (optional, defaults to `neutral`)

Response:
- `symbol`
- `pattern_name`
- `market_condition`
- `signal_stack`
- `similar_setups`
- `exact_matches`
- `success_rate`
- `avg_return_pct`
- `source`

Important limitation:

- this endpoint does not accept `signal_stack`, so it cannot return exact-match memory scoped to a specific frontend-selected signal combination

#### `POST /outcomes`

Purpose:
- record a realized trade outcome and immediately return refreshed setup memory

Request body:

```json
{
  "user_id": "demo_moderate",
  "symbol": "TATASTEEL",
  "pattern_name": "breakout",
  "action": "BUY",
  "market_condition": "neutral",
  "signal_stack": ["bulk_deal", "delivery_spike", "oi_buildup"],
  "entry_price": 133.0,
  "target_price": 149.0,
  "stop_loss": 126.0,
  "outcome_return_pct": 13.1,
  "outcome_horizon_days": 16,
  "outcome_label": "win"
}
```

Response:
- `stored_outcome`
- `updated_memory`

Frontend guidance:

- This is the only write API currently exposed.
- There is no update/delete outcome API.

### 4. Contracts the Frontend Can Reliably Assume

#### Supported demo users

- `demo_moderate`
- `demo_aggressive`

#### Supported demo seed symbols

- `TATASTEEL`
- `RELIANCE`
- `HDFCBANK`
- `INFY`
- `SUNPHARMA`

#### Supported risk profiles in code

- `aggressive`
- `moderate`
- `conservative`

#### Supported market conditions in code

- `risk_on`
- `neutral`
- `risk_off`

#### Source labels the frontend may see

- `demo`
- `yfinance`
- `nsepython`
- `supabase`
- `supabase+technical`
- `demo+demo`
- `demo+n/a`
- `demo+nsepython`

### 5. Database and Backend Surfaces

Tables actively used by the running application code:

- `stocks`
- `pattern_success_rates`
- `user_portfolios`
- `recommendation_outcomes`

Tables present in schema but not exposed through current app logic:

- `bulk_deals`
  - schema exists, but runtime bulk-deal reads currently come from `nsepython` or demo data, not this table
- `alerts`
  - schema exists, but there is no API, no repository method, and no frontend flow using it yet

### 6. Current Gaps / Non-Capabilities

These capabilities are not implemented today and should not be assumed by frontend work:

- no authentication or authorization
- no user management API
- no endpoint to list stocks or symbol metadata
- no endpoint to list all portfolios or all demo users
- no endpoint to retrieve raw signals, raw context, or raw technical objects independently
- no bulk or multi-symbol analyze endpoint
- no async job queue, progress updates, or streaming token/event output
- no alert creation or alert retrieval API despite the `alerts` table existing in schema
- no portfolio write/update endpoint
- no outcome update/delete endpoint
- no guarantee that live NSE/Yahoo sources will be available at runtime; demo fallback is part of the intended behavior
- no dedicated JavaScript/TypeScript SDK; frontend integration is plain HTTP against FastAPI

## Python Version

Use Python `3.11`, `3.12`, or `3.13`.

This project targets `3.11+`, but some compiled finance dependencies may not yet provide wheels for Python `3.14`.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run and Verify

### 1) Static Checks

```bash
python -m compileall app streamlit_app.py tests
```

### 2) Unit Test (Smoke)

```bash
pytest -q
```

### 3) Run Pipeline Once (CLI)

```bash
python -c "from app.graph import run_recommendation; r=run_recommendation('TATASTEEL','demo_moderate'); print(r.summary)"
```

Inspect adaptive memory directly:

```bash
python -c "from app.graph import run_recommendation; r=run_recommendation('TATASTEEL','demo_moderate'); print(r.setup_memory.model_dump())"
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Verify the API:

```bash
curl -s http://127.0.0.1:8000/health
curl -s "http://127.0.0.1:8000/memory/TATASTEEL?pattern_name=breakout&market_condition=neutral" | python -m json.tool
curl -s -X POST http://127.0.0.1:8000/analyze -H 'content-type: application/json' \
  -d '{"symbol":"TATASTEEL","user_id":"demo_moderate"}' | python -m json.tool
curl -s -X POST http://127.0.0.1:8000/outcomes -H 'content-type: application/json' \
  -d '{"user_id":"demo_moderate","symbol":"TATASTEEL","pattern_name":"breakout","action":"BUY","market_condition":"neutral","signal_stack":["bulk_deal","delivery_spike","oi_buildup"],"entry_price":133.0,"target_price":149.0,"stop_loss":126.0,"outcome_return_pct":13.1,"outcome_horizon_days":16,"outcome_label":"win"}' | python -m json.tool
```

Run the demo UI:

```bash
streamlit run streamlit_app.py
```

## Environment

See `.env.example`.

If Supabase or NSE endpoints are unavailable, the app falls back to deterministic demo data and marks the source in the response.

## Supabase Setup (Optional)

1. Create a Supabase project.
2. Run `sql/schema.sql` then `sql/seed.sql` in the Supabase SQL editor.
3. Set `SUPABASE_URL` and `SUPABASE_KEY` in `.env`.

When configured, historical success rates and portfolios come from Supabase; otherwise demo data is used.

## Project Layout

- `app/config.py`: runtime settings
- `app/models.py`: state and response contracts
- `app/data_sources.py`: market, NSE, and sector adapters
- `app/repository.py`: Supabase access with demo fallbacks
- `app/nodes.py`: 5 autonomous agent steps
- `app/graph.py`: LangGraph orchestration
- `app/main.py`: FastAPI endpoints
- `streamlit_app.py`: demo front-end
- `sql/schema.sql`: Supabase schema
- `sql/seed.sql`: demo seed data

## Demo Notes

- Delivery percentage uses mock values when live delivery data is unavailable.
- Sector trends use ETF-style proxies on Yahoo Finance for demo convenience.
- Historical success rates come from Supabase when configured, otherwise from seeded in-memory defaults.
- Setup memory adapts from stored outcomes and can change immediately after `POST /outcomes`.
- Option-chain support is approximated when NSE derivative data is missing.
- Local runtime verification in this workspace may fail on Python `3.14.x`; use Python `3.11-3.13` for a clean setup.

## Known Gaps (Intentional for Demo)

- Delivery% is mocked (no NSE bhavcopy ingestion yet).
- OI “buildup” is approximated as a Put OI support strike, not a strict `Put OI > Call OI by 20%` calculation.
- Only two technical patterns are implemented (`breakout`, `support_bounce`); head-and-shoulders is not implemented yet.
- `alerts` table exists (pgvector), but embedding generation + similarity search is not wired yet.
- Outcome learning currently aggregates in-process for demo fallback; persistent learning requires Supabase.
