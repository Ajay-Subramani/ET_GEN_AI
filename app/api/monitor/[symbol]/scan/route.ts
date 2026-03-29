import { runOpportunityAnalysis } from "@/lib/opportunity-agent";
import { addMonitored, updateMonitoredResult } from "@/lib/local-repo";

export const runtime = "nodejs";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params;
  const body = await request.json();
  const userId = String(body?.user_id ?? "user_default");
  const intervalMinutes = Number(body?.interval_minutes ?? 60) || 60;

  addMonitored(userId, symbol, intervalMinutes);
  const recommendation = await runOpportunityAnalysis({ symbol, userId });
  updateMonitoredResult(userId, symbol, recommendation);

  return Response.json({ symbol: symbol.toUpperCase(), result: recommendation }, { status: 200 });
}
