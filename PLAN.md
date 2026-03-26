It is three separate problems that need to be solved in order:

  1. The UI claims capabilities the backend does not expose.
  2. The backend has partial logic, but its contracts and fallback behavior are inconsistent.
  3. The repo has no ingestion + monitoring system, so the radar cannot be real.

  The right plan is to close those in phases, not try to “make it real-time” first.

  Phase 0: Stop overstating capabilities
  Ship this first. It is the fastest way to make the product honest.

  - Replace hardcoded radar and memory-log claims in app/page.tsx:525 with backend-driven states or explicit
    “demo” labels.
  - Remove copy that says “continuously monitors” until a push/polling system exists in app/page.tsx:568.
  - Add source badges everywhere the frontend renders signals/recommendations so users can see demo,
    yfinance, nsepython, supabase, or failed.
  - Hide unsupported categories from the radar for now: Management Commentary, Insider Cluster, XBRL Filing.
  - Keep only categories the backend can actually produce today: volume_breakout, pattern_start, oi_buildup,
    bulk_deal, delivery_spike once it is real.

  Acceptance criteria:

  - No screen claims monitoring, NLP, insider clustering, or XBRL parsing unless the backend returns those.
  - Every displayed recommendation includes provenance.

  Phase 1: Make the existing backend truthful and stable
  Before adding new intelligence, fix the contract and persistence bugs.

  Backend fixes:

  - Fix the table mismatch in ai-investor-agent/app/repository.py:65 from portfolios to user_portfolios to
    match ai-investor-agent/sql/schema.sql:30.
  - Implement actual demo fallback datasets inside the repository instead of returning empty/zeroed objects.
    This affects:
      - get_stock
      - get_pattern_success
      - get_user_portfolio
      - get_setup_memory
      - record_outcome
  - Make fallback source values consistent. none should become demo if deterministic local fallback is used.
  - Import logging in ai-investor-agent/app/data_sources.py:1 and normalize fallback market condition to
    neutral, not unknown, to satisfy ai-investor-agent/app/models.py:31.
  - Guard technical_analyzer against empty history in ai-investor-agent/app/nodes.py:136 so upstream data
    failures become degraded recommendations, not crashes.
  - Align README with code after the fixes. Right now the docs overpromise fallback behavior.

  API fixes:

  - Add GET /signals for raw detected signals.
  - Add GET /symbols/{symbol}/technicals for raw technical state.
  - Extend GET /memory/{symbol} to accept signal_stack.
  - Keep POST /analyze as the synthesized endpoint, but make it compose from these same primitives.

  Acceptance criteria:

  - pytest passes in ai-investor-agent/.
  - The app can run without Supabase and still return deterministic, labeled demo outputs.
  - The UI never has to invent “memory” or “portfolio” data.

  Phase 2: Introduce a real backend contract for the radar
  Do not make the radar read /analyze. It needs its own model.

  Add a SignalEvent contract in the Python models:

  class SignalEvent(BaseModel):
      id: str
      symbol: str
      category: Literal["technical", "bulk_deal", "delivery", "filing", "insider", "management_commentary"]
      title: str
      description: str
      confidence_pct: float
      detected_at: datetime
      source: str
      source_urls: list[str] = []
      payload: dict[str, Any] = {}

  Add backend endpoints:

  - GET /signals?limit=50
  - GET /signals/{id}
  - POST /signals/refresh for manual refresh during early rollout

  Frontend changes:

  - Replace the hardcoded array in app/page.tsx:526 with fetches to /api/signals.
  - Render category-specific cards only if the category exists in the API response.
  - Use an empty-state card when no live signals exist instead of fake sample rows.

  Acceptance criteria:

  - Radar is always backend-driven.
  - Manual refresh shows newly detected signals without changing app code.

  Phase 3: Build the ingestion layer
  This is the real missing engine.

  Create new backend modules:

  - ai-investor-agent/app/ingestion/sebi_filings.py
  - ai-investor-agent/app/ingestion/nse_bse_filings.py
  - ai-investor-agent/app/ingestion/market_data.py
  - ai-investor-agent/app/ingestion/insider_trades.py
  - ai-investor-agent/app/ingestion/xbrl_parser.py

  Start with polling, not websockets:

  - A scheduled worker every 1 to 5 minutes.
  - Fetch latest exchange/regulatory artifacts.
  - Normalize them into a common internal schema.
  - De-duplicate by (source_type, source_id, symbol, published_at).

  Add database tables:

  - raw_filings
  - raw_insider_disclosures
  - raw_bulk_deals
  - signal_events
  - signal_event_sources

  Recommended minimal schema shape:

  - raw_filings(id, symbol, source, source_doc_id, published_at, filing_type, title, text_content,
    xbrl_json, metadata_json, created_at)
  - signal_events(id, symbol, category, signal_key, title, description, confidence_pct, detected_at, status,
    payload_json, created_at)

  First ingestion targets:

  - NSE/BSE corporate announcements
  - Bulk/block deal feeds
  - Promoter/insider disclosures
  - Quarterly filing metadata

  Do not start with “full SEBI intelligence.” Start with stable parsers for a narrow subset.

  Acceptance criteria:

  - New filing appears in raw_filings.
  - Detector converts it into a signal_event.
  - /signals returns it.

  Phase 4: Expand technical detection from demo rules to a detector library
  The current logic in ai-investor-agent/app/nodes.py:136 is real but too narrow.

  Refactor into a dedicated detector module:

  - ai-investor-agent/app/detectors/technical.py

  Implement detectors as independent functions:

  - detect_20d_breakout
  - detect_52w_breakout
  - detect_support_bounce
  - detect_volume_spike
  - detect_rsi_divergence
  - detect_ema_reclaim
  - detect_delivery_spike once real delivery data exists

  Each detector should return:

  {
    "matched": bool,
    "signal_key": "52w_breakout",
    "confidence_pct": 78,
    "reason": "...",
    "metrics": {...},
    "source": "yfinance"
  }

  Then:

  - Use these outputs both in /signals and /analyze.
  - Stop duplicating technical descriptions in the UI.

  Acceptance criteria:

  - A technical signal shown in the radar can be traced to a detector result and exact metrics.
  - /analyze references the same detector payloads used by /signals.

  Phase 5: Make learning real and persistent
  Current outcome feedback is aggregation, not model improvement.

  Short-term implementable version:

  - Keep the heuristic engine.
  - Persist outcomes in recommendation_outcomes.
  - Add nightly aggregation jobs that update:
      - pattern_success_rates
      - signal_success_rates
      - symbol_regime_success_rates

  Add new tables:

  - signal_success_rates
  - pattern_regime_stats

  Then modify decision scoring:

  - Blend detector-level win rates
  - Blend pattern-level win rates
  - Blend user-segment win rates
  - Blend market-regime-conditioned stats

  Medium-term:

  - Add offline evaluation notebooks/scripts before introducing ML.
  - Train only after you have enough labeled outcomes.

  Acceptance criteria:

  - Submitting outcomes changes future confidence scores through recomputed stats.
  - The score change is explainable from stored aggregates.

  Phase 6: Add monitoring and push delivery
  Only do this after /signals exists.

  Backend:

  - Add a background worker that polls ingestion jobs.
  - Add server push via SSE first, WebSocket second.
  - SSE is simpler for one-way “new signal detected” updates.

  Endpoints:

  - GET /signals/stream
  - Optional GET /jobs/status

  Frontend:

  - Subscribe from the radar screen.
  - Prepend new signals into local state.
  - Show “last updated” and connection status.

  Acceptance criteria:

  - A newly ingested signal appears in the UI without a full page reload.
  - Connection loss degrades to polling.

  Phase 7: Cleanly separate demo mode from live mode
  Right now demo and live are mixed in a way that confuses both users and developers.

  Add explicit runtime mode:

  - APP_MODE=demo|live|hybrid

  Behavior:

  - demo: seeded local data only
  - live: live providers only, no fabricated signals
  - hybrid: live where available, labeled fallback where not

  Frontend:

  - Show the current mode in the header.
  - If demo, display a banner on radar/memory pages.

  Acceptance criteria:

  - No one can mistake demo signals for live ones.
  - QA can test both paths deterministically.

  Recommended delivery order
  If you want the shortest path to a credible product:

  1. Phase 0 and Phase 1
  2. Phase 2
  3. Phase 3 for filings + bulk deals
  4. Phase 4
  5. Phase 6
  6. Phase 5 after you have data volume
  7. Phase 7 in parallel with Phase 1 if possible

  Concrete file map
  Start changes here:

  - Frontend contract cleanup: app/page.tsx
  - Frontend API proxy additions: lib/ai-investor.ts
  - Next API routes: app/api/analyze/route.ts, app/api/outcomes/route.ts
  - Backend API surface: ai-investor-agent/app/main.py
  - Backend scoring logic: ai-investor-agent/app/nodes.py
  - Backend data providers: ai-investor-agent/app/data_sources.py
  - Persistence and fallback correctness: ai-investor-agent/app/repository.py
  - Schema evolution: ai-investor-agent/sql/schema.sql
  - Smoke coverage: ai-investor-agent/tests/test_graph.py

  What not to do

  - Do not add WebSockets before the radar has a real backend endpoint.
  - Do not build ML before you have stable labeled outcomes and evaluation.
  - Do not keep fake radar cards while claiming “continuous monitoring.”
  - Do not let /analyze remain the only backend contract; it is too coarse.