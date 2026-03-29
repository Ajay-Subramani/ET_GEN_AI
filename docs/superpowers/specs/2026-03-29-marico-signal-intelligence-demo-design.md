# Marico Signal Intelligence Demo

## Goal

Add a dedicated, judge-facing demo route that simulates the ET Markets Signal Intelligence Agent analyzing a hardcoded promoter bulk-deal event for Marico Ltd. The experience should feel like a credible enterprise AI workflow while remaining fully deterministic and offline.

## Scope

### In scope

- A dedicated demo page that does not replace the current homepage.
- A visible `Run Agent Demo` trigger that starts a five-step agent sequence.
- A local mock API route that returns only hardcoded MARICO scenario data.
- Sequential step reveal behavior with per-step simulated delays between 1.2s and 2.0s.
- A persistent portfolio sidebar showing MARICO as the top holding with a red P&L.
- A final alert card containing the exact citation `BD20240328-4421`.
- Non-destructive action buttons that raise toast confirmations only.

### Out of scope

- Live market data, filing APIs, or any external network calls.
- Real trade execution, watchlist persistence, or backend mutations.
- Generic multi-symbol support for this demo path.
- Changing existing non-demo analysis flows.

## Primary design decision

Use a dedicated route plus a local mock API instead of a pure client-only fake.

Rationale:

- It preserves the appearance of a real agent-backed product for judges.
- It isolates the demo from the existing homepage and production-style routes.
- It keeps all demo content deterministic, inspectable, and stable under time pressure.

## User experience

### Entry state

The page loads with:

- A strong headline framing this as ET Markets Signal Intelligence.
- A visible `Run Agent Demo` button.
- A persistent portfolio sidebar already showing:
  - `MARICO` as the top holding
  - `150 shares`
  - average price `₹637`
  - a red unrealized P&L of `−₹3,750`
- An idle step timeline showing all five stages in the `pending` state before execution begins.

No analysis cards should be pre-rendered as completed before the trigger is pressed.

### Run behavior

After the user clicks `Run Agent Demo`:

1. The UI requests the hardcoded payload from the local mock API.
2. The step timeline enters an active state.
3. Each step is processed sequentially.
4. Each step remains hidden until its own simulated delay completes.
5. While a step is active:
   - its row shows `running`
   - the status bar shows a plain-English description of the current work
6. When a step finishes:
   - its row flips to `done (✓)`
   - its content card becomes visible
7. The next step starts only after the previous one completes.

The page should feel like a live agent run, not a static report.

### Final action behavior

The final alert includes these action buttons:

- `Set Stop-Loss`
- `Add to Watchlist`
- `Save Brief`

All buttons show toast confirmations only. No real order execution or durable save occurs.

## Route design

### Demo page

Add a standalone route:

- `/demo/marico-signal-intelligence`

This route should be implemented as a dedicated page-level client experience with no dependency on the existing homepage state.

### Mock API

Add a dedicated demo endpoint:

- `GET /api/demo/marico-signal`

The endpoint returns one hardcoded JSON payload containing all content needed by the page:

- filing block fields
- earnings and management context
- technical metrics and 90-day chart series
- distress factor table
- portfolio position data
- final alert copy and action recommendations

## Data contract

The mock payload should be strongly structured so the UI remains declarative.

Suggested top-level sections:

- `scenario`
- `steps`
- `portfolio`
- `final_alert`

### Scenario fields

Include the exact hardcoded event details:

- company: `Marico Ltd`
- symbol: `MARICO`
- exchange: `NSE`
- seller: `Harsh Mariwala`
- event: promoter sold `4.2%` stake via BSE bulk deal
- deal price: `₹575`
- previous close: `₹611.70`
- discount: `6.0%`
- filing ref: `BD20240328-4421`
- timestamp: `28 Mar 2024 15:47 IST`
- deal value: `₹1,580 Cr`
- buyer: `Undisclosed institutional`

### Enrichment fields

Include:

- a 3-quarter earnings table showing PAT decline
- a volume-growth trend showing slowing growth
- one hardcoded management quote from the Q3 call

### Technical fields

Include:

- RSI: `38.2`
- bearish MACD cross: `true`
- price vs 200D MA: `-4.1%`
- Wyckoff pattern: `distribution`
- 90 days of hardcoded price data descending clearly from `₹648` to `₹569`

### Distress classifier fields

Include seven factors, each with:

- factor name
- observed condition
- signal direction or weight

The aggregate output must be:

- distress probability: `34%`
- signal strength: `HIGH`

### Portfolio and alert fields

Include:

- holdings: `150`
- average price: `₹637`
- marked demo P&L: `−₹3,750`
- projected downside support: `₹558`
- projected downside loss: `−₹11,850`
- stop-loss recommendation: `₹585`
- alert citation text containing `BD20240328-4421` verbatim

## UI structure

### Main layout

Use a two-column layout on desktop:

- main analysis timeline on the left
- sticky portfolio sidebar on the right

On mobile:

- portfolio summary appears first or in a compact pinned card
- timeline stacks below

### Core sections

The main column should include:

- hero/header
- run trigger and live status bar
- step progress rail
- revealed step cards
- final action alert

### Portfolio sidebar

The sidebar should make portfolio awareness obvious at a glance:

- MARICO appears first and most prominent
- red negative P&L is visible without scrolling
- support downside scenario is repeated here or near the final alert

## Step-by-step content

### Step 1: Filing retrieval

Status text example:

- `Retrieving and parsing the latest bulk-deal filing for MARICO`

Card content:

- parsed filing block with all deal fields
- filing reference and timestamp
- discount versus previous close highlighted visually

### Step 2: Context enrichment

Status text example:

- `Cross-checking promoter activity against earnings momentum and management commentary`

Card content:

- compact earnings table with three declining PAT quarters
- slowing volume growth trend
- Q3 management quote block

### Step 3: Technical detection

Status text example:

- `Running technical signal stack on 90-day price action`

Card content:

- hardcoded downtrend chart from `₹648` to `₹569`
- RSI `38.2`
- bearish MACD cross
- price `4.1%` below 200D MA
- Wyckoff distribution label

### Step 4: Distress classifier

Status text example:

- `Scoring distress probability across event, operating, and technical factors`

Card content:

- 7-factor table
- distress probability `34%`
- `HIGH` signal strength badge

### Step 5: Portfolio-aware alert

Status text example:

- `Mapping signal impact to your MARICO holding and generating a risk action`

Card content:

- user holds `150 shares @ ₹637 avg`
- current P&L `−₹3,750`
- projected downside to `₹558` support: `−₹11,850`
- stop-loss recommendation at `₹585`
- explicit cited alert containing `BD20240328-4421`

## State model

The page should use a simple deterministic state machine:

- `idle`
- `loading_payload`
- `running_step_n`
- `complete`

Per-step view state:

- `pending`
- `running`
- `done`

The step content is rendered only when the step reaches `done`.

## Timing model

Each of the five steps receives a fixed simulated delay between 1.2s and 2.0s.

Recommendation:

- assign explicit fixed delays in code rather than randomizing
- choose slightly varied values so the sequence feels natural
- keep the full demo under roughly 10 seconds

This keeps the experience repeatable for judging while still feeling agentic.

## Visual direction

The demo should feel enterprise-grade and editorial, not like a hackathon toy dashboard.

Guidance:

- preserve the existing visual language where it helps, but give the demo route a more focused presentation
- use strong hierarchy and clear contrast for the five-step progression
- use red selectively for losses, downside, and caution
- keep the citation, timestamps, and numeric evidence highly legible
- make the chart visually clean and obviously downward trending

## Error handling

Even though the API is local and deterministic, the UI should still handle failure gracefully.

If the mock request fails:

- show a visible demo error state
- allow retry from the same page
- do not partially run the sequence

If the user re-runs the demo:

- reset steps to `pending`
- clear prior toasts
- replay the same deterministic sequence

## Testing strategy

### Automated

Add targeted tests around the deterministic pieces that are easiest to regress:

- mock API returns the expected hardcoded payload shape
- chart dataset contains exactly 90 points and trends downward
- citation `BD20240328-4421` is present in the final alert payload
- portfolio calculation values displayed in the UI match the hardcoded scenario values

### Manual

Verify:

- the current homepage is unchanged
- the demo route loads independently
- clicking `Run Agent Demo` reveals steps one at a time only after their delays
- step rows animate from `running` to `done (✓)`
- status text updates at every stage
- toast actions do not execute any real mutation
- mobile and desktop layouts both keep portfolio awareness obvious

## Success criteria

The implementation is successful when:

- judges can open a dedicated route and immediately understand the MARICO use case
- the demo visibly behaves like a sequential AI agent run
- each step reveals only after its delay
- the portfolio-aware risk framing is impossible to miss
- the final alert contains `BD20240328-4421` verbatim
- no live APIs or real order actions are used anywhere in the demo flow
