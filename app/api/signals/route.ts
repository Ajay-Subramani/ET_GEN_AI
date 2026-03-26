import { proxyGet } from "@/lib/ai-investor";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  return proxyGet("/signals", searchParams);
}
