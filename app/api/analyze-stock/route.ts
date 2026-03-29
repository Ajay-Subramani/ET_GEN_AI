import { runOpportunityAnalysis } from "@/lib/opportunity-agent";

export const runtime = "nodejs";

type AnalyzeStockBody =
  | {
      stock: string;
      portfolio?: string[];
      user_id?: string;
    }
  | {
      symbol: string;
      user_id: string;
    };

export async function POST(request: Request) {
  const body = (await request.json()) as AnalyzeStockBody;
  const stock = "stock" in body ? body.stock : body.symbol;
  const userId =
    ("user_id" in body && body.user_id) ? body.user_id : "user_default";

  if (!stock) {
    return Response.json({ message: "Missing stock symbol." }, { status: 400 });
  }

  const recommendation = await runOpportunityAnalysis({
    symbol: stock,
    userId,
  });

  return Response.json(recommendation, { status: 200 });
}

