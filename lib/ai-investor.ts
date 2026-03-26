export type RiskProfile = "aggressive" | "moderate" | "conservative";
export type ActionType = "BUY" | "WATCH" | "AVOID";
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

export interface RecommendationResponse {
  symbol: string;
  user_id: string;
  action: ActionType;
  confidence_pct: number;
  conviction_mode: string;
  confidence_note: string;
  entry_price: number;
  target_price: number;
  stop_loss: number;
  reasoning: string;
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
  sources: {
    signals: string[];
    historical: string;
    sector: string;
    market: string;
    technical: string;
  };
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

export interface HealthResponse {
  status: string;
  env: string;
}

function getBackendBaseUrl() {
  return process.env.AI_INVESTOR_API_BASE_URL ?? "http://127.0.0.1:8000";
}

async function proxyToBackend(path: string, init?: RequestInit): Promise<Response> {
  const targetUrl = new URL(path, getBackendBaseUrl());

  try {
    return await fetch(targetUrl, {
      ...init,
      cache: "no-store",
      headers: {
        ...(init?.headers ?? {}),
        ...(init?.body ? { "content-type": "application/json" } : {}),
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
