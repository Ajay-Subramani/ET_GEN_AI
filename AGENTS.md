# AGENTS.md — Opportunity Radar (AI for Indian Investor)

## Overview

This project implements an AI-powered Opportunity Radar that detects stock market signals and generates actionable trading insights.

Goal:

* Detect signals (NOT summarize news)
* Enrich signals with reasoning
* Generate actionable alerts

System Type:

* Single-agent autonomous pipeline
* Built inside Next.js (App Router)
* No multi-agent orchestration
* No backend microservices

LLM:

* Ollama (local runtime)
* Model: deepseek-v3.2:cloud

Market Data:

* TwelveData API (time_series endpoint only)

---

## Core Pipeline

The agent executes **3 sequential steps autonomously**:

1. Signal Detection
2. Context Enrichment
3. Actionable Alert Generation

Flow:
Input → Fetch Data → Detect → Enrich → Act → Output

---

## Agent Architecture

This system uses a **single autonomous agent** that completes all steps in one execution.

### Execution Flow

1. Input Reception

   * Accept stock symbol and optional portfolio

2. Data Fetch

   * Retrieve market data from TwelveData

3. Signal Detection

   * Analyze price trend and volume

4. Context Enrichment

   * Explain reasoning behind signals

5. Action Generation

   * Produce actionable recommendation

6. Output

   * Return structured JSON

---

### Autonomous Behavior

* Fully automatic execution
* No human intervention required
* Single request triggers full pipeline
* Stateless (no memory between runs)

---

### Internal State Flow

RAW INPUT
↓
MARKET DATA
↓
DETECTED SIGNALS
↓
ENRICHED CONTEXT
↓
ACTIONABLE DECISION

---

## Project Structure

* `app/` → Next.js pages and layouts
* `app/api/analyze-stock/route.ts` → API route (core backend)
* `lib/opportunity-agent.ts` → agent pipeline logic (3-step deterministic agent)
* `lib/twelvedata.ts` → TwelveData `time_series` fetch + demo fallback

Alias:

* `@/*` → project root (see `tsconfig.json`)

---

## Build & Dev Commands

* `npm install`
* `npm run dev`
* `npm run build`
* `npm run start`
* `npm run lint`

---

## Coding Style

* JavaScript (Next.js / React)
* 2-space indentation
* Prefer double quotes
* Functional components only
* Keep logic modular (`lib/`)

---

## API Design

### Endpoint

POST `/api/analyze-stock` (preferred)

Compatibility:

POST `/api/analyze` (used by the UI)

### Input

```json
{
  "stock": "RELIANCE",
  "portfolio": ["TCS", "INFY"]
}
```

The UI also supports:

```json
{
  "symbol": "RELIANCE",
  "user_id": "user_default"
}
```

---

## Market Data Integration

Uses TwelveData API.

Base URL:
https://api.twelvedata.com

### Endpoint

GET `/time_series`

### Configuration

* interval = 1day
* outputsize = 10
* exchange = NSE
* country = India
* format = JSON
* timezone = exchange
* type = stock

### Example

https://api.twelvedata.com/time_series?apikey=YOUR_API_KEY&symbol=RELIANCE&interval=1day&outputsize=10&exchange=NSE&country=India&format=JSON&timezone=exchange&type=stock

---

## Data Strategy

Fetch ONLY:

* last ~10 daily candles

Extract:

* price trend (up/down)
* momentum (increasing/decreasing)
* volatility
* volume behavior

Do NOT:

* use technical indicator endpoints
* fetch 1min data
* fetch large datasets

---

## Agent Logic

### Step 1 — Signal Detection

From candle data:

* rising prices → bullish trend
* falling prices → bearish trend
* rising volume → accumulation
* falling volume → weak momentum

Also detect:

* sudden drops → potential risk events
* sharp spikes → breakout potential

Output:

* signal (bullish / bearish / neutral)
* signal_strength (early / strong / late)

---

### Step 2 — Context Enrichment

Combine observations:

* trend + volume → confirmation
* sideways + spike → breakout setup
* sudden drop + volume → selling pressure

Rules:

* explain WHY signal exists
* connect price and volume
* avoid generic statements

---

### Step 3 — Actionable Alert

Must include:

* Action:

  * buy / watch / avoid
* Entry:

  * breakout / dip / confirmation
* Risk:

  * invalidation condition

Examples:

* "Enter above recent high"
* "Exit if price drops below support"

---

## Advanced Reasoning Requirements

### Conflicting Signals Handling

If signals conflict:

* Identify bullish signals
* Identify bearish signals
* Present both clearly
* Provide balanced recommendation

Example:

* breakout (bullish)
* overbought (bearish)

Do NOT give one-sided output.

---

### Source Attribution

The agent must reference source of reasoning:

Examples:

* "Based on recent price and volume data"
* "Based on observed selling pressure"

Avoid vague statements.

---

### Portfolio Impact Analysis

If portfolio is provided:

* Identify affected stocks
* Estimate impact (low / medium / high)
* Explain reasoning

Example:

* "This impacts 2 out of 5 holdings in your portfolio"
* "Impact level: medium due to sector exposure"

---

### Uncertainty Handling

The agent must:

* Avoid absolute predictions
* Provide conditional actions
* Include confidence score

Example:

* "If price sustains above resistance → bullish continuation"
* "If reversal occurs → downside risk increases"

---

## Ollama Integration

Endpoint:
http://localhost:11434/api/generate

Model:
deepseek-v3.2:cloud

Behavior:

* Accept prompt
* Return response
* Must be parsed into JSON

---

## Prompt Rules

The model must:

* Act as a financial analyst
* Focus on signals (not news summary)
* Follow 3-step pipeline strictly
* Return structured JSON
* Use only provided data
* Avoid hallucination

---

## Output Schema

```json
{
  "step_1_signal_detection": {
    "signal": "string",
    "signal_strength": "early | strong | late"
  },
  "step_2_context_enrichment": {
    "reasoning": []
  },
  "step_3_actionable_alert": {
    "action": "string",
    "entry": "string",
    "risk": "string"
  },
  "conflicting_signals": [],
  "confidence": number,
  "why_most_people_miss_this": "string",
  "portfolio_impact": {
    "affected_stocks": [],
    "impact_level": "low | medium | high",
    "explanation": ""
  },
  "source": []
}
```

---

## Constraints

* No database
* No background jobs
* No multi-agent system
* No complex pipelines

Single request → single response

---

## Security

* Store API keys in `.env.local`
* Never commit credentials
* Validate API responses

---

## Development Workflow

1. Create API route
2. Integrate TwelveData
3. Implement agent logic
4. Connect Ollama
5. Return structured JSON
6. Test with sample stocks

---

## Example Flow

1. User sends stock symbol
2. Fetch time_series data
3. Extract trend + volume
4. Send to LLM
5. Generate signal + action
6. Return response

---

## Final Notes

* Focus on intelligence, not infrastructure
* Keep system simple
* Output quality > system complexity
* Simulate a smart analyst, not a trading engine


## Jury Expectation

* Refer to EXPECTATION.txt
