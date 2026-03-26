import { proxyPost } from "@/lib/ai-investor";

export async function POST(request: Request) {
  const body = await request.json();
  return proxyPost("/analyze", body);
}
