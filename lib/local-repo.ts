import type { OutcomeHistoryItem, OutcomeRequest, RecommendationResponse, SetupMemory } from "@/lib/ai-investor";

type MonitoredRecord = {
  id: string;
  user_id: string;
  symbol: string;
  interval_minutes: number;
  latest_result: RecommendationResponse | null;
};

type StoreState = {
  monitored: MonitoredRecord[];
  outcomes: OutcomeHistoryItem[];
};

declare global {
  var __LOCAL_AGENT_STORE__: StoreState | undefined;
}

function getStore(): StoreState {
  if (!globalThis.__LOCAL_AGENT_STORE__) {
    globalThis.__LOCAL_AGENT_STORE__ = { monitored: [], outcomes: [] };
  }
  return globalThis.__LOCAL_AGENT_STORE__;
}

export function listMonitored(userId: string) {
  return getStore().monitored.filter((m) => m.user_id === userId);
}

export function addMonitored(userId: string, symbol: string, intervalMinutes: number) {
  const store = getStore();
  const upper = symbol.toUpperCase();
  const existing = store.monitored.find((m) => m.user_id === userId && m.symbol === upper);
  if (existing) {
    existing.interval_minutes = intervalMinutes;
    return existing;
  }
  const record: MonitoredRecord = {
    id: `mon_${userId}_${upper}`.toLowerCase(),
    user_id: userId,
    symbol: upper,
    interval_minutes: intervalMinutes,
    latest_result: null,
  };
  store.monitored.push(record);
  return record;
}

export function removeMonitored(userId: string, symbol: string) {
  const store = getStore();
  const upper = symbol.toUpperCase();
  const before = store.monitored.length;
  store.monitored = store.monitored.filter((m) => !(m.user_id === userId && m.symbol === upper));
  return store.monitored.length !== before;
}

export function updateMonitoredResult(
  userId: string,
  symbol: string,
  result: RecommendationResponse | null,
) {
  const store = getStore();
  const upper = symbol.toUpperCase();
  const record = store.monitored.find((m) => m.user_id === userId && m.symbol === upper);
  if (record) record.latest_result = result;
}

export function listOutcomes(symbol?: string, limit: number = 20): OutcomeHistoryItem[] {
  const store = getStore();
  const filtered = symbol
    ? store.outcomes.filter((o) => o.symbol.toUpperCase() === symbol.toUpperCase())
    : store.outcomes.slice();
  return filtered.slice(-limit).reverse();
}

export function recordOutcome(payload: OutcomeRequest): OutcomeHistoryItem {
  const store = getStore();
  const item: OutcomeHistoryItem = {
    ...payload,
    id: `${Date.now()}`,
    created_at: new Date().toISOString(),
  };
  store.outcomes.push(item);
  return item;
}

export function getSetupMemory(symbol: string, patternName: string, marketCondition: string, signalStack: string[]): SetupMemory {
  return {
    symbol: symbol.toUpperCase(),
    pattern_name: patternName,
    market_condition: marketCondition,
    signal_stack: signalStack,
    similar_setups: 0,
    exact_matches: 0,
    success_rate: 0,
    avg_return_pct: 0,
    source: "demo",
  };
}
