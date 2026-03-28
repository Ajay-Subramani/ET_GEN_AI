import { proxyPost } from "@/lib/ai-investor";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ symbol: string }> }
) {
  const { symbol } = await params;
  const body = await request.json();
  return proxyPost(`/monitor/${encodeURIComponent(symbol)}/scan`, body);
}
