import { addMonitored, removeMonitored } from "@/lib/local-repo";

export const runtime = "nodejs";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params;
  const body = await request.json();
  const userId = String(body?.user_id ?? "user_default");
  const intervalMinutes = Number(body?.interval_minutes ?? 60) || 60;
  const entry = addMonitored(userId, symbol, intervalMinutes);
  return Response.json({ monitored: entry }, { status: 200 });
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params;
  const { searchParams } = new URL(request.url);
  const userId = searchParams.get("user_id") || "user_default";
  const removed = removeMonitored(userId, symbol);
  return Response.json({ removed, symbol: symbol.toUpperCase() }, { status: 200 });
}
