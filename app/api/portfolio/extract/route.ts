import { proxyPostFormData } from "@/lib/ai-investor";

export async function POST(request: Request) {
  const formData = await request.formData();
  return proxyPostFormData("/api/portfolio/extract", formData);
}

