import { proxyGet, proxyPost } from "@/lib/ai-investor";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const userId = searchParams.get("user_id") || "user_default";
  return proxyGet(`/monitor?user_id=${encodeURIComponent(userId)}`);
}
