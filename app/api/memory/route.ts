import { proxyGet } from "@/lib/ai-investor";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbol = searchParams.get("symbol") || "TATASTEEL";
  return proxyGet(`/memory/${symbol}`, searchParams);
}
