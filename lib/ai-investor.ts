export type RiskProfile = "aggressive" | "moderate" | "conservative";
export type ActionType = "High Conviction Buy" | "Potential Buy" | "Watch" | "Avoid / Exit";
export type BackendActionType = "BUY" | "WATCH" | "AVOID";
export type OutcomeLabel = "win" | "loss" | "neutral";
export interface PortfolioHolding {
  symbol: string;
  quantity: number;
  avg_price: number;
  sector: string;
}

export interface UserPortfolio {
  user_id?: string;
  risk_profile: RiskProfile;
  total_capital: number;
  holdings: PortfolioHolding[];
}

export interface UsersResponse {
  default_user_id: string;
  user_portfolio: UserPortfolio;
}

export interface FundamentalContext {
  pe_ratio: number | null;
  roce: number | null;
  roe: number | null;
  debt_to_equity: number | null;
  revenue_growth: number | null;
  profit_growth: number | null;
  operating_margin: number | null;
  source: string;
}

export interface SetupMemory {
  symbol: string;
  pattern_name: string;
  market_condition: string;
  signal_stack: string[];
  similar_setups: number;
  exact_matches: number;
  success_rate: number;
  avg_return_pct: number;
  source: string;
}

export interface AgentToolTrace {
  tool_name: string;
  arguments: Record<string, unknown>;
  output_preview: string;
}

export interface AgentStepTrace {
  step_name: string;
  objective: string;
  thought: string;
  model: string;
  tool_calls: AgentToolTrace[];
  output_summary: string;
}

export interface RecommendationResponse {
  symbol: string;
  user_id: string;
  action: BackendActionType;
  confidence_score: number;
  conviction_mode: string;
  confidence_note: string;
  entry_price: number;
  target_price: number;
  stop_loss: number;
  reasoning: string | string[];
  memo_narrative?: string;
  analyst_note: string;
  setup_memory: SetupMemory;
  allocation_pct: number;
  allocation_amount: number;
  sector_exposure_pct: number;
  personalization_warning: string | null;
  next_step: string;
  watch_next: string[];
  confirmation_triggers: string[];
  invalidation_triggers: string[];
  fundamental_context: FundamentalContext;
  sources: {
    signals: string[];
    historical: string;
    sector: string;
    market: string;
    technical: string;
  };
  execution_mode?: string;
  agent_trace?: AgentStepTrace[];
  summary: string;
}

export interface OutcomeRequest {
  user_id: string;
  symbol: string;
  pattern_name: string;
  action: string;
  market_condition: string;
  signal_stack: string[];
  entry_price: number;
  target_price: number;
  stop_loss: number;
  outcome_return_pct: number;
  outcome_horizon_days: number;
  outcome_label: OutcomeLabel;
}

export interface OutcomeResponse {
  stored_outcome: OutcomeRequest;
  updated_memory: SetupMemory;
}

export interface OutcomeHistoryItem extends OutcomeRequest {
  id?: number | string | null;
  created_at?: string | null;
}

export interface HealthResponse {
  status: string;
  env: string;
}

function getBackendBaseUrl() {
  return process.env.AI_INVESTOR_API_BASE_URL ?? "http://127.0.0.1:8000";
}

function hasContentType(headers: HeadersInit | undefined) {
  if (!headers) return false;
  if (headers instanceof Headers) return headers.has("content-type");
  if (Array.isArray(headers)) return headers.some(([key]) => key.toLowerCase() === "content-type");
  return Object.keys(headers).some((key) => key.toLowerCase() === "content-type");
}

async function proxyToBackend(path: string, init?: RequestInit): Promise<Response> {
  const targetUrl = new URL(path, getBackendBaseUrl());
  const shouldSetJsonContentType = typeof init?.body === "string" && !hasContentType(init?.headers);

  try {
    return await fetch(targetUrl, {
      ...init,
      cache: "no-store",
      headers: {
        ...(init?.headers ?? {}),
        ...(shouldSetJsonContentType ? { "content-type": "application/json" } : {}),
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown backend error";
    return Response.json(
      {
        error: "backend_unreachable",
        message,
        target: targetUrl.toString(),
      },
      { status: 502 },
    );
  }
}

export async function proxyGet(path: string, searchParams?: URLSearchParams): Promise<Response> {
  const suffix = searchParams?.toString();
  return proxyToBackend(suffix ? `${path}?${suffix}` : path, {
    method: "GET",
  });
}

export async function proxyPost(path: string, body: unknown): Promise<Response> {
  return proxyToBackend(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function proxyPostFormData(path: string, body: FormData): Promise<Response> {
  return proxyToBackend(path, {
    method: "POST",
    body,
  });
}

export async function proxyDelete(path: string, searchParams?: URLSearchParams): Promise<Response> {
  const suffix = searchParams?.toString();
  return proxyToBackend(suffix ? `${path}?${suffix}` : path, {
    method: "DELETE",
  });
}
