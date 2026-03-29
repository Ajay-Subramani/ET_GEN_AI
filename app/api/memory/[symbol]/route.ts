import { getSetupMemory } from "@/lib/local-repo";

export const runtime = "nodejs";

export async function GET(
  request: Request,
  context: { params: Promise<{ symbol: string }> },
) {
  const { symbol } = await context.params;
  const searchParams = new URL(request.url).searchParams;
  const patternName = searchParams.get("pattern_name") || "breakout";
  const marketCondition = searchParams.get("market_condition") || "neutral";
  const signalStack = searchParams.getAll("signal_stack");
  const memory = getSetupMemory(symbol, patternName, marketCondition, signalStack);
  return Response.json(memory, { status: 200 });
}
