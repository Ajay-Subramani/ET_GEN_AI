import type { AgentStepTrace } from "@/lib/ai-investor";
import { fetchTimeSeries } from "@/lib/twelvedata";
import { runOpportunityAnalysis } from "@/lib/opportunity-agent";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const limit = Number(searchParams.get("limit") ?? "10") || 10;

  const watchlist = ["TATASTEEL", "RELIANCE", "HDFCBANK", "INFY", "SUNPHARMA"];
  const selected = watchlist.slice(0, Math.max(1, Math.min(limit, watchlist.length)));

  const agentTrace: AgentStepTrace[] = [];
  agentTrace.push({
    step_name: "watchlist",
    objective: "Select symbols for radar scan.",
    thought: "Using a fixed local watchlist for the radar.",
    model: "rule_engine",
    tool_calls: [],
    output_summary: selected.join(", "),
  });

  const signals = [];
  for (const symbol of selected) {
    const series = await fetchTimeSeries(symbol, { interval: "1day", outputsize: 10 });
    if (!series.ok) continue;

    const analysis = await runOpportunityAnalysis({ symbol, userId: "user_default" });
    signals.push({
      id: `sig_${symbol.toLowerCase()}_${Date.now()}`,
      symbol,
      category: "technical",
      signal_type: analysis.action === "BUY" ? "volume_breakout" : analysis.action === "AVOID" ? "sell_pressure" : "pattern_start",
      title: analysis.summary,
      description: Array.isArray(analysis.reasoning) ? analysis.reasoning.slice(0, 2).join(" ") : String(analysis.reasoning),
      memo_narrative: analysis.memo_narrative ?? analysis.summary,
      confidence_pct: Math.round((analysis.confidence_score ?? 0) * 100),
      detected_at: new Date().toISOString(),
      source: series.source,
      is_demo: series.source !== "twelvedata",
      explanation: analysis.confidence_note,
    });
  }

  return Response.json(
    {
      radar_summary: "Local deterministic radar feed generated from TwelveData time_series.",
      signals: signals.slice(0, limit),
      agent_trace: agentTrace,
    },
    { status: 200 },
  );
}
