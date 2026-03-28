import { proxyGet, proxyPost } from "@/lib/ai-investor";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  return proxyGet("/outcomes", searchParams);
}

export async function POST(request: Request) {
  const body = await request.json();
  return proxyPost("/outcomes", body);
}
