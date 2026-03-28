<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

## Agent Development Guide

This repository contains two primary agent tiers working together:

- A Next.js frontend (`app/`) that proxies requests to the backend via `app/api/*` route handlers.
- A Python FastAPI agent service under `ai-investor-agent/app/` which implements the investment-agent pipeline and smaller LLM tool-agent paths.

This document explains the architecture, how to run the system locally, where to add or change agent behavior, and common troubleshooting notes.

**Architecture overview**

- Frontend: React + Next (app router). UI code is in `app/page.tsx` and components under `components/`. The frontend never talks directly to the Python API — it hits local Next route handlers under `app/api/*` which proxy to the backend using `lib/ai-investor.ts`.
- Backend: FastAPI app lives at `ai-investor-agent/app/main.py`. The agent pipeline is constructed in `ai-investor-agent/app/graph.py` using LangGraph and node implementations live in `ai-investor-agent/app/nodes.py`.
- Data + persistence: `ai-investor-agent/app/repository.py` abstracts Supabase (Postgres) access and provides deterministic demo fallbacks when Supabase is not configured.
- Market adapters: `ai-investor-agent/app/data_sources.py` (yfinance, optional nsepython, talib)
- LLM/tool agent: `ai-investor-agent/app/llm_agents.py` — contains OpenAI tool-agent wrappers and the radar builder used by `/signals`.

**Key files**

- `ai-investor-agent/app/main.py` — FastAPI entrypoints and REST contract.
- `ai-investor-agent/app/graph.py` — builds the sequential agent flow: signal_detector -> context_enricher -> technical_analyzer -> decision_engine -> personalizer.
- `ai-investor-agent/app/nodes.py` — concrete node implementations. To add rules or detectors, extend this file or refactor into `detectors/` as described in `PLAN.md`.
- `ai-investor-agent/app/repository.py` — persistence + demo fallbacks.
- `lib/ai-investor.ts` — Next proxy helpers. Frontend code uses the Next API routes to call the backend.

Running locally

1. Backend (Python)

	- Create/activate the virtualenv in `ai-investor-agent/.venv` or create one and `pip install -r ai-investor-agent/requirements.txt`.
	- From the backend folder:

	```bash
	cd ai-investor-agent
	source .venv/bin/activate
	uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
	```

	- The API endpoints are available at `http://127.0.0.1:8000`.

2. Frontend (Next)

	- Ensure frontend env is configured: copy `.env.example` → `.env.local` and set `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` and optionally `AI_INVESTOR_API_BASE_URL` (default `http://127.0.0.1:8000`).
	- Start the Next dev server from repo root:

	```bash
	npm install
	npm run dev
	```

3. Combined helper

	- The repo includes `scripts/backend.sh` to start the backend; ensure it points to `uvicorn app.main:app` or run the command above directly.

Feature flags & environment

- Backend settings are in `ai-investor-agent/app/config.py` (Pydantic settings). Key toggles:
  - `OPENAI_API_KEY` and `openai_agent_enabled` — enable the LLM/tool agent path.
  - `SUPABASE_URL` / `SUPABASE_KEY` — if present, the repository uses Supabase instead of demo fallback.

API surface (important endpoints)

- `GET /health` — simple status
- `GET /api/users` — bootstrap user portfolio
- `GET /signals` — backend radar feed (may use LLM agent or deterministic build)
- `POST /analyze` — produces a full `FinalRecommendation` for a symbol + user_id
- `GET /memory/{symbol}` — setup memory & historical stats
- `GET /symbols/{symbol}/technicals` — raw technical indicators
- `GET /outcomes` / `POST /outcomes` — list and record realized outcomes

Where to change agent behavior

- Add detectors: factor out detection functions into `ai-investor-agent/app/detectors/technical.py` (recommended) and call them from `nodes.signal_detector` and `nodes.technical_analyzer`.
- Change decision rules: update `ai-investor-agent/app/nodes.py::AnalystNodes.decision_engine()`.
- Extend memory/persistence: modify `Repository` in `ai-investor-agent/app/repository.py` and add new SQL tables in `ai-investor-agent/sql/` with migrations.

Testing

- Backend tests: run from `ai-investor-agent/`:

```bash
cd ai-investor-agent
source .venv/bin/activate
pytest -q
```

- The tests validate the graph output and demo outcome behavior.

Common troubleshooting

- Error: "Could not import module 'main'" — means Uvicorn was pointed to `main:app` but no `main.py` at cwd; use `uvicorn app.main:app` or run from `ai-investor-agent` where a compatibility wrapper exists.
- Backend unreachable from Next: ensure `AI_INVESTOR_API_BASE_URL` points to the running backend; check `lib/ai-investor.ts` for proxy behavior and error payloads.
- Missing market data: yfinance and `nsepython` are optional; the code falls back to deterministic demo values if remote providers fail.

Developer workflow & PR checklist

- Run backend unit tests and smoke-start the API before opening a PR.
- If adding public APIs, update `ai-investor-agent/app/main.py` and add OpenAPI docstrings where appropriate.
- Keep demo vs live behavior explicit: label demo outputs (`source: demo`, `is_demo: true`) so frontend can render provenance.

Notes and roadmap links

- The detailed phases for roadmap and architectural direction live in `PLAN.md`. Follow Phase 0–3 before adding ingestion/real-time push features.

If you want, I can also:

- Patch `scripts/backend.sh` to call `uvicorn app.main:app` directly.
- Add a small README in `ai-investor-agent/` that mirrors these run instructions.

---

Last updated: 2026-03-28
