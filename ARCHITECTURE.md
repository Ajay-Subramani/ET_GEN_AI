# Architecture — Opportunity Radar (Local-Only)

## Goal

Run a single autonomous “Opportunity Radar” agent locally with a Next.js App Router frontend. A single request triggers a 3-step pipeline:

1. Signal detection
2. Context enrichment
3. Action generation

Market data is sourced from TwelveData `time_series` (daily candles). No Python backend is required for local operation.

---

## High-Level Diagram

```text
Browser (React UI)
   |
   |  fetch("/api/*")
   v
Next.js Route Handlers (Node runtime)
   |
   +--> TwelveData time_series (HTTP fetch)
   |
   +--> Agent pipeline (deterministic rules)
   |
   +--> Local in-memory store (monitors/outcomes/memory)
   v
JSON responses consumed by UI
```

---

## Runtime Components

### 1) Frontend (Client UI)

- File: `app/page.tsx`
- Responsibilities:
  - Session/auth via Supabase client
  - Calls local Route Handlers under `app/api/*`
  - Renders recommendation, trace, radar feed, monitor list, outcomes/memory views
  - Displays backend-unreachable errors cleanly (no unhandled promise crashes)

### 2) Backend-for-Frontend (Route Handlers)

All APIs are implemented as Next Route Handlers (Web `Request`/`Response` APIs) and run locally in Node.

Core endpoints:

- `POST /api/analyze-stock`
  - File: `app/api/analyze-stock/route.ts`
  - Input (preferred): `{ "stock": "RELIANCE", "portfolio": ["TCS"] }`
  - Input (UI compatible): `{ "symbol": "RELIANCE", "user_id": "user_default" }`
  - Output: `RecommendationResponse` JSON + `agent_trace`

- `POST /api/analyze`
  - File: `app/api/analyze/route.ts`
  - Compatibility alias used by the current UI. Same output as `/api/analyze-stock`.

- `GET /api/signals`
  - File: `app/api/signals/route.ts`
  - Returns a simple radar feed for a fixed local watchlist.

- `GET /api/health`
  - File: `app/api/health/route.ts`
  - Returns `{ status, env, twelvedata, twelvedata_env_var, ... }` for quick configuration validation.

Local persistence endpoints (in-memory, dev-friendly):

- `GET/POST /api/outcomes` → `app/api/outcomes/route.ts`
- `GET /api/memory` and `GET /api/memory/[symbol]` → `app/api/memory/*`
- `GET/POST/DELETE /api/monitor*` → `app/api/monitor/*`

Debug endpoint (proves TwelveData fetch content):

- `GET /api/twelvedata/raw?symbol=TATASTEEL&interval=1day&outputsize=10`
  - File: `app/api/twelvedata/raw/route.ts`
  - Returns:
    - `request.redacted_url` (never includes the API key)
    - `response.status`
    - `payload` (full TwelveData JSON)
    - `candles` (parsed OHLCV array)

### 3) Agent Pipeline (Single-Agent, Sequential)

- File: `lib/opportunity-agent.ts`
- Entry: `runOpportunityAnalysis({ symbol, userId })`
- Steps:
  1. **market_data_fetch** → calls TwelveData `time_series` via `lib/twelvedata.ts`
  2. **signal_detection** → computes trend + volume alignment
  3. **context_enrichment** → converts observations into plain-language reasoning
  4. **action_generation** → maps signal + confidence into `BUY/WATCH/AVOID` and derives levels

Every run returns an `agent_trace` array used by the UI’s “Agent Verification Trace”.

### 4) Market Data Adapter (TwelveData)

- File: `lib/twelvedata.ts`
- Primary call:
  - `fetchTimeSeries(symbol, { interval: "1day", outputsize: 10 })`
- Debug call:
  - `fetchTimeSeriesDebug(...)` returns the full raw payload and the redacted request URL.

Key lookup order:
1. `TWELVEDATA_API_KEY`
2. `NEXT_PUBLIC_TWELVEDATA_API_KEY`
3. `ai-investor-agent/.env` (fallback for local convenience)

If no key is found, the adapter returns deterministic demo candles so the UI stays usable.

### 5) Local Store (Dev Persistence)

- File: `lib/local-repo.ts`
- Purpose:
  - Keep “monitor list”, “outcomes”, and “memory” routes functional without a database.
  - Stores data in a Node global (`globalThis.__LOCAL_AGENT_STORE__`) so it persists across requests during `next dev`.

---

## Data Contracts

- Shared TypeScript response types live in `lib/ai-investor.ts` (used by the UI).
- `RecommendationResponse` is the primary response shape used by `app/page.tsx`.

---

## Configuration (Local)

Copy `.env.example` → `.env.local` and set:

- `TWELVEDATA_API_KEY` (recommended for live data)
- Supabase keys for auth UI:
  - `NEXT_PUBLIC_SUPABASE_URL`
  - `NEXT_PUBLIC_SUPABASE_ANON_KEY`

Optional:
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL` (not required for the current deterministic pipeline)

---

## Legacy Python Backend

The folder `ai-investor-agent/` remains in the repo for historical development, but the local architecture described here does not require running it.

