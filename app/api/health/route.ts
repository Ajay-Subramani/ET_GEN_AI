export const runtime = "nodejs";

async function readKeyFromAgentEnvFile(): Promise<string | null> {
  try {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const envPath = path.join(process.cwd(), "ai-investor-agent", ".env");
    const raw = await fs.readFile(envPath, "utf8");
    for (const line of raw.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const match = trimmed.match(/^TWELVEDATA_API_KEY\s*=\s*(.+)\s*$/);
      if (!match) continue;
      const value = match[1] ?? "";
      const cleaned = value.trim().replace(/^["']|["']$/g, "");
      return cleaned || null;
    }
    return null;
  } catch {
    return null;
  }
}

export async function GET() {
  const apiKeyRaw = process.env.TWELVEDATA_API_KEY ?? process.env.NEXT_PUBLIC_TWELVEDATA_API_KEY;
  const apiKeyFromEnv = apiKeyRaw?.trim().replace(/^["']|["']$/g, "");
  const apiKeyFromAgentEnv = apiKeyFromEnv ? null : await readKeyFromAgentEnvFile();
  const hasTwelveData = Boolean(apiKeyFromEnv || apiKeyFromAgentEnv);
  const ollamaBaseUrl = process.env.OLLAMA_BASE_URL ?? "http://127.0.0.1:11434";

  return Response.json(
    {
      status: "ok",
      env: "local",
      twelvedata: hasTwelveData ? "configured" : "missing_api_key",
      twelvedata_env_var: process.env.TWELVEDATA_API_KEY
        ? "TWELVEDATA_API_KEY"
        : process.env.NEXT_PUBLIC_TWELVEDATA_API_KEY
          ? "NEXT_PUBLIC_TWELVEDATA_API_KEY"
          : apiKeyFromAgentEnv
            ? "ai-investor-agent/.env"
            : "none",
      ollama_base_url: ollamaBaseUrl,
    },
    { status: 200 },
  );
}
