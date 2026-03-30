# Opportunity Radar — AI Investor Agent for Indian Markets

Opportunity Radar is an autonomous, institutional-grade AI investor agent designed to detect high-alpha signals in the Indian stock market (NSE). It moves beyond simple news summarization by executing a rigorous 3-step signal intelligence pipeline directly in your local environment.

## 🚀 Key Features

- **3-Step Autonomous Pipeline:**
  1. **Signal Detection:** Rigorous technical analysis of price trend, volume expansion, and momentum shifts using real-time candle data.
  2. **Context Enrichment:** Plain-language reasoning that connects technical observations into a coherent investment thesis.
  3. **Actionable Alerts:** Generation of precise `BUY/WATCH/AVOID` recommendations with calculated entry, target, and stop-loss levels.
- **Institutional-Grade Terminal:** A high-precision interface for deep-dive stock analysis and "Neural Stream" confidence monitoring.
- **Global Signals Radar:** A live dashboard scanning the NSE for emerging opportunities across a broader watchlist.
- **Portfolio-Aware Risk Management:** Personalized position sizing and risk alerts based on your current holdings and sector exposure.
- **Pattern Memory & Outcome Tracking:** A closed-loop system that learns from historical trade outcomes to refine future confidence scores.

## 🛠 Tech Stack

- **Frontend:** Next.js 16 (App Router), React 19, Tailwind CSS 4.0
- **Intelligence Engine:** Local LLM via Ollama (`deepseek-v3.2:cloud`)
- **Data Integration:** TwelveData (Market Data), Supabase (Authentication)
- **Persistence:** Local in-memory store for rapid development and testing

## 🚦 Getting Started

### 1. Prerequisites

- **Ollama:** Install [Ollama](https://ollama.ai/) and pull the required model:
  ```bash
  ollama pull deepseek-v3.2:cloud
  ```
- **TwelveData API Key:** Obtain a free API key from [TwelveData](https://twelvedata.com/). (The app includes a deterministic demo fallback if no key is provided).

### 2. Configuration

Copy the example environment file and set your keys:

```bash
cp .env.example .env.local
```

Required variables:
- `TWELVEDATA_API_KEY`: Your TwelveData key.
- `NEXT_PUBLIC_SUPABASE_URL`: Your Supabase project URL.
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Your Supabase anon key.

### 3. Installation & Development

```bash
# Install dependencies
npm install

# Start the local development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to access the Opportunity Radar.

## 🏗 Architecture

The system is designed for **local-only execution** to ensure maximum privacy and performance.

```text
Browser (React 19)
   |
   |  fetch("/api/analyze-stock")
   v
Next.js Route Handlers (Node.js)
   |
   +--> TwelveData API (Market Data)
   |
   +--> Ollama (Local LLM Reasoning)
   |
   +--> Local Pattern Memory (Outcome Feedback)
   v
Structured JSON Response (Signals + Actions)
```

## 📖 Commands

- `npm run dev`: Start development server.
- `npm run build`: Build for production.
- `npm run lint`: Run ESLint for code quality.

---

*Note: This project is optimized for Indian Markets (NSE) and uses heuristic-backed intelligence to simulate a senior financial analyst.*
