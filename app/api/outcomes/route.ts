import type { OutcomeRequest } from "@/lib/ai-investor";
import { getSetupMemory, listOutcomes, recordOutcome } from "@/lib/local-repo";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbol = searchParams.get("symbol") ?? undefined;
  const limit = Number(searchParams.get("limit") ?? "20") || 20;
  const outcomes = listOutcomes(symbol, limit);
  return Response.json(outcomes, { status: 200 });
}

export async function POST(request: Request) {
  const body = (await request.json()) as OutcomeRequest;
  const stored = recordOutcome(body);
  const updatedMemory = getSetupMemory(
    body.symbol,
    body.pattern_name,
    body.market_condition,
    body.signal_stack,
  );
  return Response.json(
    {
      stored_outcome: stored,
      updated_memory: updatedMemory,
    },
    { status: 200 },
  );
}
