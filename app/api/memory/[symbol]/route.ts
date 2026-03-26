import { proxyGet } from "@/lib/ai-investor";

export async function GET(
  request: Request,
  context: { params: Promise<{ symbol: string }> },
) {
  const { symbol } = await context.params;
  const searchParams = new URL(request.url).searchParams;
  return proxyGet(`/memory/${symbol}`, searchParams);
}
