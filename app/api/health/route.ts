import { proxyGet } from "@/lib/ai-investor";

export async function GET() {
  return proxyGet("/health");
}
