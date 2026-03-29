export type Candle = {
  datetime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type TimeSeriesResult =
  | {
      ok: true;
      source: "twelvedata";
      symbol: string;
      interval: string;
      candles: Candle[];
    }
  | {
      ok: true;
      source: "demo";
      symbol: string;
      interval: string;
      candles: Candle[];
      warning: string;
    }
  | {
      ok: false;
      source: "twelvedata";
      symbol: string;
      interval: string;
      error: string;
    };

export type TimeSeriesDebugResult =
  | (Extract<TimeSeriesResult, { ok: true }> & {
      request: { url: string; redacted_url: string };
      response: { ok: boolean; status: number };
      payload: unknown | null;
    })
  | (Extract<TimeSeriesResult, { ok: false }> & {
      request: { url: string; redacted_url: string };
      response: { ok: boolean; status: number };
      payload: unknown | null;
    });

function toNumber(value: unknown) {
  const num = typeof value === "number" ? value : Number(value);
  return Number.isFinite(num) ? num : 0;
}

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

function demoCandles(symbol: string): Candle[] {
  const base = 100 + (symbol.toUpperCase().charCodeAt(0) % 20);
  const now = new Date();
  const candles: Candle[] = [];
  for (let index = 0; index < 10; index += 1) {
    const day = new Date(now);
    day.setDate(now.getDate() - (9 - index));
    const drift = index * 0.6;
    const noise = ((symbol.length + index) % 7) * 0.15;
    const open = base + drift + noise;
    const close = open + (index % 3 === 0 ? -0.2 : 0.35);
    const high = Math.max(open, close) + 0.8;
    const low = Math.min(open, close) - 0.7;
    candles.push({
      datetime: day.toISOString().slice(0, 10),
      open: Number(open.toFixed(2)),
      high: Number(high.toFixed(2)),
      low: Number(low.toFixed(2)),
      close: Number(close.toFixed(2)),
      volume: 1_000_000 + index * 50_000,
    });
  }
  return candles;
}

async function fetchTimeSeriesInternal(
  symbol: string,
  {
    interval = "1day",
    outputsize = 10,
    debug = false,
  }: { interval?: string; outputsize?: number; debug?: boolean } = {},
): Promise<TimeSeriesResult | TimeSeriesDebugResult> {
  const apiKeyRaw = process.env.TWELVEDATA_API_KEY ?? process.env.NEXT_PUBLIC_TWELVEDATA_API_KEY;
  const apiKeyFromEnv = apiKeyRaw?.trim().replace(/^["']|["']$/g, "");
  const apiKey = apiKeyFromEnv || (await readKeyFromAgentEnvFile());
  const upper = symbol.toUpperCase().trim();

  if (!apiKey) {
    const demo: Extract<TimeSeriesResult, { ok: true; source: "demo" }> = {
      ok: true,
      source: "demo",
      symbol: upper,
      interval,
      candles: demoCandles(upper),
      warning:
        "TWELVEDATA_API_KEY not found (checked root env and ai-investor-agent/.env); using deterministic demo candles.",
    };
    if (!debug) return demo;
    return {
      ...demo,
      request: { url: "n/a", redacted_url: "n/a" },
      response: { ok: true, status: 200 },
      payload: null,
    };
  }

  const url = new URL("https://api.twelvedata.com/time_series");
  url.searchParams.set("apikey", apiKey);
  url.searchParams.set("symbol", upper);
  url.searchParams.set("interval", interval);
  url.searchParams.set("outputsize", String(outputsize));
  url.searchParams.set("exchange", "NSE");
  url.searchParams.set("country", "India");
  url.searchParams.set("format", "JSON");
  url.searchParams.set("timezone", "exchange");
  url.searchParams.set("type", "stock");

  const redacted = new URL(url);
  redacted.searchParams.set("apikey", "REDACTED");

  try {
    const response = await fetch(url, { cache: "no-store" });
    const payload: unknown = await response.json();

    if (!response.ok) {
      const messageFromBody =
        payload && typeof payload === "object" && "message" in payload ? (payload as { message?: unknown }).message : null;
      const message =
        (typeof messageFromBody === "string" && messageFromBody) ||
        response.statusText ||
        "TwelveData request failed";
      const failure: Extract<TimeSeriesResult, { ok: false }> = {
        ok: false,
        source: "twelvedata",
        symbol: upper,
        interval,
        error: String(message),
      };
      if (!debug) return failure;
      return {
        ...failure,
        request: { url: url.toString(), redacted_url: redacted.toString() },
        response: { ok: false, status: response.status },
        payload,
      };
    }

    const maybeValues =
      payload && typeof payload === "object" ? (payload as Record<string, unknown>).values : undefined;
    if (!Array.isArray(maybeValues)) {
      const failure: Extract<TimeSeriesResult, { ok: false }> = {
        ok: false,
        source: "twelvedata",
        symbol: upper,
        interval,
        error: "Unexpected TwelveData response shape",
      };
      if (!debug) return failure;
      return {
        ...failure,
        request: { url: url.toString(), redacted_url: redacted.toString() },
        response: { ok: true, status: response.status },
        payload,
      };
    }

    const candles = maybeValues
      .slice()
      .reverse()
      .map((row: unknown) => {
        const obj = row && typeof row === "object" ? (row as Record<string, unknown>) : {};
        return {
          datetime: String(obj.datetime ?? ""),
          open: toNumber(obj.open),
          high: toNumber(obj.high),
          low: toNumber(obj.low),
          close: toNumber(obj.close),
          volume: toNumber(obj.volume),
        };
      })
      .filter((row: Candle) => Boolean(row.datetime));

    const ok: Extract<TimeSeriesResult, { ok: true; source: "twelvedata" }> = {
      ok: true,
      source: "twelvedata",
      symbol: upper,
      interval,
      candles,
    };
    if (!debug) return ok;
    return {
      ...ok,
      request: { url: url.toString(), redacted_url: redacted.toString() },
      response: { ok: true, status: response.status },
      payload,
    };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown TwelveData error";
    const failure: Extract<TimeSeriesResult, { ok: false }> = {
      ok: false,
      source: "twelvedata",
      symbol: upper,
      interval,
      error: message,
    };
    if (!debug) return failure;
    return {
      ...failure,
      request: { url: url.toString(), redacted_url: redacted.toString() },
      response: { ok: false, status: 0 },
      payload: null,
    };
  }
}

export async function fetchTimeSeries(
  symbol: string,
  opts: { interval?: string; outputsize?: number } = {},
): Promise<TimeSeriesResult> {
  return (await fetchTimeSeriesInternal(symbol, { ...opts, debug: false })) as TimeSeriesResult;
}

export async function fetchTimeSeriesDebug(
  symbol: string,
  opts: { interval?: string; outputsize?: number } = {},
): Promise<TimeSeriesDebugResult> {
  return (await fetchTimeSeriesInternal(symbol, { ...opts, debug: true })) as TimeSeriesDebugResult;
}
