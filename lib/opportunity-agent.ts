import type { AgentStepTrace, RecommendationResponse } from "@/lib/ai-investor";
import { fetchTimeSeries } from "@/lib/twelvedata";

type SignalStrength = "early" | "strong" | "late";
type MarketSignal = "bullish" | "bearish" | "neutral";

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function pctChange(from: number, to: number) {
  if (!from) return 0;
  return ((to / from) - 1) * 100;
}

function computeVolatility(closes: number[]) {
  if (closes.length < 2) return 0;
  const returns: number[] = [];
  for (let index = 1; index < closes.length; index += 1) {
    const prev = closes[index - 1]!;
    const cur = closes[index]!;
    returns.push(prev ? (cur / prev) - 1 : 0);
  }
  const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
  const variance = returns.reduce((a, b) => a + (b - mean) ** 2, 0) / returns.length;
  return Math.sqrt(variance);
}

function detectSignal({
  closes,
  volumes,
}: {
  closes: number[];
  volumes: number[];
}): { signal: MarketSignal; strength: SignalStrength; score: number; notes: string[] } {
  const notes: string[] = [];
  const latestClose = closes.at(-1) ?? 0;
  const firstClose = closes.at(0) ?? latestClose;
  const changePct = pctChange(firstClose, latestClose);

  const lastVol = volumes.at(-1) ?? 0;
  const avgVol = volumes.length ? volumes.reduce((a, b) => a + b, 0) / volumes.length : 0;
  const volRatio = avgVol ? lastVol / avgVol : 1;

  if (changePct > 1.2) notes.push(`Price trend is up (${changePct.toFixed(1)}% over window).`);
  if (changePct < -1.2) notes.push(`Price trend is down (${changePct.toFixed(1)}% over window).`);
  if (volRatio > 1.4) notes.push(`Volume is expanding (${volRatio.toFixed(2)}x vs average).`);
  if (volRatio < 0.75) notes.push(`Volume is lighter (${volRatio.toFixed(2)}x vs average).`);

  const trendScore = clamp(changePct / 6, -1, 1);
  const volumeScore = clamp((volRatio - 1) / 1.2, -1, 1);
  const raw = 0.65 * trendScore + 0.35 * volumeScore;
  const score = clamp((raw + 1) / 2, 0, 1);

  let signal: MarketSignal = "neutral";
  if (raw >= 0.25) signal = "bullish";
  if (raw <= -0.25) signal = "bearish";

  let strength: SignalStrength = "early";
  if (Math.abs(raw) >= 0.65) strength = "strong";
  else if (Math.abs(raw) >= 0.45) strength = "late";

  return { signal, strength, score, notes };
}

function buildReasoning({
  signal,
  strength,
  notes,
  volatility,
}: {
  signal: MarketSignal;
  strength: SignalStrength;
  notes: string[];
  volatility: number;
}): { reasoning: string[]; confidenceNote: string } {
  const reasoning = [...notes];
  reasoning.push(`Volatility is ${(volatility * 100).toFixed(2)}% (daily return std dev, windowed).`);

  const strengthText =
    strength === "strong" ? "strong alignment" : strength === "late" ? "some confirmation" : "early-stage evidence";
  const directionText = signal === "bullish" ? "upside" : signal === "bearish" ? "downside" : "sideways";
  const confidenceNote = `Detected ${strengthText} for a ${directionText} signal using recent price + volume behavior.`;

  return { reasoning, confidenceNote };
}

function decideAction(signal: MarketSignal, score: number) {
  if (signal === "bullish" && score >= 0.62) return "BUY" as const;
  if (signal === "bearish" && score >= 0.62) return "AVOID" as const;
  return "WATCH" as const;
}

function computeLevels(current: number, volatility: number) {
  const vol = clamp(volatility, 0.004, 0.06);
  const targetPct = clamp(vol * 6, 0.03, 0.12);
  const stopPct = clamp(vol * 3, 0.02, 0.08);
  return {
    entry_price: Number(current.toFixed(2)),
    target_price: Number((current * (1 + targetPct)).toFixed(2)),
    stop_loss: Number((current * (1 - stopPct)).toFixed(2)),
  };
}

export async function runOpportunityAnalysis({
  symbol,
  userId,
}: {
  symbol: string;
  userId: string;
}): Promise<RecommendationResponse> {
  const upper = symbol.toUpperCase().trim();
  const series = await fetchTimeSeries(upper, { interval: "1day", outputsize: 10 });

  const trace: AgentStepTrace[] = [];

  if (!series.ok) {
    throw new Error(`TwelveData error: ${series.error}`);
  }

  trace.push({
    step_name: "market_data_fetch",
    objective: "Fetch last ~10 daily candles via TwelveData time_series.",
    thought: series.source === "demo" ? series.warning : "Fetched TwelveData time_series candles.",
    model: "twelvedata",
    tool_calls: [],
    output_summary: `${series.candles.length} candles (${series.source}).`,
  });

  const candles = series.candles;
  const closes = candles.map((c) => c.close);
  const volumes = candles.map((c) => c.volume);
  const latestClose = closes.at(-1) ?? 0;
  const volatility = computeVolatility(closes);

  const detection = detectSignal({ closes, volumes });
  trace.push({
    step_name: "signal_detection",
    objective: "Detect bullish/bearish/neutral signals from price + volume.",
    thought: `Signal=${detection.signal} strength=${detection.strength}.`,
    model: "rule_engine",
    tool_calls: [],
    output_summary: detection.notes.join(" "),
  });

  const context = buildReasoning({
    signal: detection.signal,
    strength: detection.strength,
    notes: detection.notes,
    volatility,
  });
  trace.push({
    step_name: "context_enrichment",
    objective: "Explain why the signal is present using observations.",
    thought: context.confidenceNote,
    model: "rule_engine",
    tool_calls: [],
    output_summary: context.reasoning.slice(0, 5).join(" "),
  });

  const action = decideAction(detection.signal, detection.score);
  const levels = computeLevels(latestClose, volatility);
  trace.push({
    step_name: "action_generation",
    objective: "Generate an actionable alert (BUY/WATCH/AVOID) with levels.",
    thought: `Action=${action} confidence_score=${detection.score.toFixed(2)}.`,
    model: "rule_engine",
    tool_calls: [],
    output_summary: `Entry=${levels.entry_price} Target=${levels.target_price} Stop=${levels.stop_loss}`,
  });

  const summary = `${upper}: ${action} (${Math.round(detection.score * 100)}% confidence)`;

  return {
    symbol: upper,
    user_id: userId,
    action,
    confidence_score: clamp(detection.score, 0, 1),
    conviction_mode: detection.strength === "strong" ? "HIGH_CONVICTION" : detection.strength === "late" ? "ALIGNED" : "NORMAL",
    confidence_note: context.confidenceNote,
    entry_price: levels.entry_price,
    target_price: levels.target_price,
    stop_loss: levels.stop_loss,
    reasoning: context.reasoning,
    memo_narrative: context.reasoning.slice(0, 3).join(" "),
    analyst_note: context.reasoning.slice(0, 2).join(" "),
    setup_memory: {
      symbol: upper,
      pattern_name: "twelvedata_window",
      market_condition: "neutral",
      signal_stack: [detection.signal, detection.strength],
      similar_setups: 0,
      exact_matches: 0,
      success_rate: 0,
      avg_return_pct: 0,
      source: "demo",
    },
    allocation_pct: action === "BUY" ? 5 : 0,
    allocation_amount: 0,
    sector_exposure_pct: 0,
    personalization_warning: null,
    next_step:
      action === "BUY"
        ? "Enter in tranches; re-check signal if volume fades."
        : action === "AVOID"
          ? "Avoid new exposure until trend stabilizes."
          : "Wait for confirmation (higher highs + sustained volume).",
    watch_next: ["Volume confirmation", "Next daily close", "Market breadth"],
    confirmation_triggers: ["Daily close above recent highs", "Volume > 1.3x average"],
    invalidation_triggers: ["Close below recent swing low", "Volume dries up during breakout"],
    fundamental_context: {
      pe_ratio: null,
      roce: null,
      roe: null,
      debt_to_equity: null,
      revenue_growth: null,
      profit_growth: null,
      operating_margin: null,
      source: "n/a",
    },
    sources: {
      signals: ["twelvedata_time_series", series.source],
      historical: "n/a",
      sector: "n/a",
      market: "n/a",
      technical: "twelvedata_time_series",
    },
    execution_mode: series.source === "twelvedata" ? "heuristic" : "heuristic",
    agent_trace: trace,
    summary,
  };
}

