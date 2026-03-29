import { getSetupMemory } from "@/lib/local-repo";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbol = searchParams.get("symbol") || "TATASTEEL";
  const patternName = searchParams.get("pattern_name") || "breakout";
  const marketCondition = searchParams.get("market_condition") || "neutral";
  const signalStack = searchParams.getAll("signal_stack");
  const memory = getSetupMemory(symbol, patternName, marketCondition, signalStack);
  return Response.json(memory, { status: 200 });
}
