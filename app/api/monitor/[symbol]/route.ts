import { proxyPost, proxyDelete } from "@/lib/ai-investor";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params;
  const body = await request.json();
  return proxyPost(`/monitor/${encodeURIComponent(symbol)}`, body);
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params;
  const { searchParams } = new URL(request.url);
  const userId = searchParams.get("user_id") || "user_default";
  return proxyDelete(`/monitor/${encodeURIComponent(symbol)}?user_id=${encodeURIComponent(userId)}`);
}
