import { listMonitored } from "@/lib/local-repo";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const userId = searchParams.get("user_id") || "user_default";
  return Response.json({ monitored_symbols: listMonitored(userId) }, { status: 200 });
}
