import { runOpportunityAnalysis } from "@/lib/opportunity-agent";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const body = (await request.json()) as { symbol?: string; user_id?: string };
  const symbol = body.symbol ?? "";
  const userId = body.user_id ?? "user_default";

  if (!symbol) {
    return Response.json({ message: "Missing symbol." }, { status: 400 });
  }

  const recommendation = await runOpportunityAnalysis({ symbol, userId });
  return Response.json(recommendation, { status: 200 });
}
