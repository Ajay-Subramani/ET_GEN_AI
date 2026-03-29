export const runtime = "nodejs";

export async function POST(request: Request) {
  // This project is intended to run locally without external LLM services by default.
  // Portfolio extraction can be added later via Ollama vision / external APIs.
  await request.formData();
  return Response.json(
    {
      message: "Portfolio extraction is not configured for local mode.",
    },
    { status: 501 },
  );
}
