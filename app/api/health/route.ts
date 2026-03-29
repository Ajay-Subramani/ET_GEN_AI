export const runtime = "nodejs";

export async function GET() {
  const hasTwelveData = Boolean(process.env.TWELVEDATA_API_KEY?.trim());
  const ollamaBaseUrl = process.env.OLLAMA_BASE_URL ?? "http://127.0.0.1:11434";

  return Response.json(
    {
      status: "ok",
      env: "local",
      twelvedata: hasTwelveData ? "configured" : "missing_api_key",
      ollama_base_url: ollamaBaseUrl,
    },
    { status: 200 },
  );
}
