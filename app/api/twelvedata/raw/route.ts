import { fetchTimeSeriesDebug } from "@/lib/twelvedata";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbol = searchParams.get("symbol") || "TATASTEEL";
  const interval = searchParams.get("interval") || "1day";
  const outputsize = Number(searchParams.get("outputsize") || "10") || 10;

  const result = await fetchTimeSeriesDebug(symbol, { interval, outputsize });
  return Response.json(result, { status: 200 });
}

