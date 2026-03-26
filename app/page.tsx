"use client";

import { useEffect, useEffectEvent, useMemo, useState, useTransition } from "react";
import { supabase } from "@/lib/supabase";
import Auth from "@/components/Auth";
import type {
  HealthResponse,
  OutcomeLabel,
  OutcomeRequest,
  OutcomeResponse,
  RecommendationResponse,
  RiskProfile,
  UserPortfolio,
  UsersResponse,
} from "@/lib/ai-investor";

const SYMBOLS = ["TATASTEEL", "RELIANCE", "HDFCBANK", "INFY", "SUNPHARMA"];

const RISK_OPTIONS: { label: string; value: RiskProfile }[] = [
  { label: "Aggressive", value: "aggressive" },
  { label: "Moderate", value: "moderate" },
  { label: "Conservative", value: "conservative" },
];

const ACTION_STYLES: Record<
  RecommendationResponse["action"],
  { badge: string; accent: string; tone: string; eyebrow: string }
> = {
  BUY: {
    badge: "bg-[color:var(--success)] text-white",
    accent: "text-[color:var(--success)]",
    tone: "bg-[rgba(6,95,70,0.1)] text-[color:var(--success)]",
    eyebrow: "Strategic Accumulation Triggered",
  },
  WATCH: {
    badge: "bg-[color:var(--warning)] text-white",
    accent: "text-[color:var(--warning)]",
    tone: "bg-[rgba(146,64,14,0.12)] text-[color:var(--warning)]",
    eyebrow: "Monitor For Confirmation",
  },
  AVOID: {
    badge: "bg-[color:var(--danger)] text-white",
    accent: "text-[color:var(--danger)]",
    tone: "bg-[rgba(127,29,29,0.12)] text-[color:var(--danger)]",
    eyebrow: "Capital Preservation Preferred",
  },
};

const DEFAULT_PORTFOLIO: UserPortfolio = {
  risk_profile: "moderate",
  total_capital: 0,
  holdings: [],
};

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatCompactCurrency(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

function formatPercent(value: number) {
  return `${value.toFixed(1)}%`;
}

async function fetchJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const data = (await response.json()) as T & {
    error?: string;
    message?: string;
  };

  if (!response.ok) {
    const message =
      typeof data === "object" && data && "message" in data && data.message
        ? data.message
        : "Request failed";
    throw new Error(message);
  }

  return data;
}

export type TabId = "Terminal" | "Signals" | "Portfolio" | "Memory";

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabId>("Terminal");
  const [riskProfile, setRiskProfile] = useState<RiskProfile>("moderate");
  const [symbol, setSymbol] = useState("TATASTEEL");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [portfolio, setPortfolio] = useState<UserPortfolio>(DEFAULT_PORTFOLIO);
  const [recommendation, setRecommendation] =
    useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showOutcomeModal, setShowOutcomeModal] = useState(false);
  const [session, setSession] = useState<any>(null);
  const [isAuthChecking, setIsAuthChecking] = useState(true);
  const [outcomeLabel, setOutcomeLabel] = useState<OutcomeLabel>("win");
  const [outcomeReturnPct, setOutcomeReturnPct] = useState("8.5");
  const [outcomeHorizonDays, setOutcomeHorizonDays] = useState("14");
  const [isBootstrapping, startBootstrapTransition] = useTransition();
  const [isAnalyzing, startAnalyzeTransition] = useTransition();
  const [isSavingOutcome, startOutcomeTransition] = useTransition();

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setIsAuthChecking(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
    });

    return () => subscription.unsubscribe();
  }, []);


  const refreshBootstrap = useEffectEvent(async () => {
    const [healthResponse, usersResponse] = await Promise.all([
      fetchJson<HealthResponse>("/api/health"),
      fetchJson<UsersResponse>(`/api/users?user_id=${session?.user?.id || "user_default"}`),
    ]);

    setHealth(healthResponse);
    setPortfolio({
      ...usersResponse.user_portfolio,
      user_id: usersResponse.default_user_id,
    });
    setRiskProfile(usersResponse.user_portfolio.risk_profile);
  });

  useEffect(() => {
    startBootstrapTransition(() => {
      void refreshBootstrap().catch((bootstrapError: unknown) => {
        const message =
          bootstrapError instanceof Error
            ? bootstrapError.message
            : "Unable to load backend status.";
        setError(message);
      });
    });
  }, []);

  const effectiveUserId = session?.user?.id || "user_default";

  const latestComputedAt = new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "medium",
    timeZone: "Asia/Kolkata",
  }).format(new Date());

  const handleSignOut = () => {
    supabase.auth.signOut();
  };

  const inferredCapital = useMemo(() => {
    if (recommendation && recommendation.allocation_pct > 0) {
      return recommendation.allocation_amount / (recommendation.allocation_pct / 100);
    }

    return portfolio.total_capital;
  }, [portfolio.total_capital, recommendation]);

  const handleAnalyze = (targetSymbol = symbol) => {
    setError(null);
    setRecommendation(null);
    setShowOutcomeModal(false);

    startAnalyzeTransition(() => {
      void fetchJson<RecommendationResponse>("/api/analyze", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ symbol: targetSymbol, user_id: effectiveUserId }),
      })
        .then((response) => {
          setRecommendation(response);
          setOutcomeLabel("win");
          setOutcomeReturnPct(response.setup_memory.avg_return_pct.toFixed(1));
          setOutcomeHorizonDays("14");
        })
        .catch((analyzeError: unknown) => {
          const message =
            analyzeError instanceof Error
              ? analyzeError.message
              : "Unable to run analysis.";
          setError(message);
        });
    });
  };

  const deployAgentFromRadar = (targetSymbol: string) => {
    setSymbol(targetSymbol);
    setActiveTab("Terminal");
    handleAnalyze(targetSymbol);
  };

  const handleOutcomeSubmit = () => {
    if (!recommendation) return;

    setError(null);

    const payload: OutcomeRequest = {
      user_id: recommendation.user_id,
      symbol: recommendation.symbol,
      pattern_name: recommendation.setup_memory.pattern_name,
      action: recommendation.action,
      market_condition: recommendation.setup_memory.market_condition,
      signal_stack: recommendation.setup_memory.signal_stack,
      entry_price: recommendation.entry_price,
      target_price: recommendation.target_price,
      stop_loss: recommendation.stop_loss,
      outcome_return_pct: Number(outcomeReturnPct),
      outcome_horizon_days: Number(outcomeHorizonDays),
      outcome_label: outcomeLabel,
    };

    startOutcomeTransition(() => {
      void fetchJson<OutcomeResponse>("/api/outcomes", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then((response) => {
          setRecommendation((current) =>
            current
              ? {
                  ...current,
                  setup_memory: response.updated_memory,
                }
              : current,
          );
          setShowOutcomeModal(false);
        })
        .catch((submitError: unknown) => {
          const message =
            submitError instanceof Error
              ? submitError.message
              : "Unable to record outcome.";
          setError(message);
        });
    });
  };

  const activeStyles = recommendation
    ? ACTION_STYLES[recommendation.action]
    : ACTION_STYLES.WATCH;

  const supportingStats = [
    {
      label: "Index State",
      title: health?.env === "dev" ? "Demo + Live Hybrid" : "Live",
      value: health?.status ?? "checking",
    },
    {
      label: "Risk Profile",
      title: riskProfile.toUpperCase(),
      value: effectiveUserId,
    },
    {
      label: "Bootstrap Portfolio",
      title: formatCompactCurrency(portfolio.total_capital),
      value: `${portfolio.holdings.length} holdings`,
    },
    {
      label: "System",
      title: health?.status === "ok" ? "Healthy" : "Unavailable",
      value: health?.env ?? "unknown",
    },
  ];

  if (isAuthChecking) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <span className="font-mono text-xs uppercase tracking-widest text-slate-400">
          Verifying Identity...
        </span>
      </div>
    );
  }

  if (!session) {
    return <Auth />;
  }

  return (
    <div className="editorial-shell min-h-screen text-[color:var(--foreground)]">
      <TopBar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        healthLabel={health?.status === "ok" ? "System Healthy" : "Backend Check"}
        userEmail={session?.user?.email}
        onSignOut={handleSignOut}
        onResetTerminal={() => {
          setRecommendation(null);
          setError(null);
          setActiveTab("Terminal");
        }}
      />
      <div className="flex pt-14">
        <SideBar 
          activeTab={activeTab} 
          setActiveTab={setActiveTab} 
          onResetTerminal={() => {
            setRecommendation(null);
            setError(null);
            setActiveTab("Terminal");
          }}
        />
        <main className="min-h-[calc(100vh-56px)] flex-1 md:ml-64">
          {error && (recommendation || isAnalyzing) ? (
            <div className="mx-6 mt-6 rounded-2xl bg-[rgba(127,29,29,0.08)] px-5 py-4 text-sm text-[color:var(--danger)] md:mx-8">
              {error}
            </div>
          ) : null}

          {activeTab === "Signals" && (
            <SignalsRadarScreen onDeployAgent={deployAgentFromRadar} />
          )}

          {activeTab === "Portfolio" && (
            <PortfolioScreen portfolio={portfolio} />
          )}

          {activeTab === "Memory" && (
            <MemoryScreen />
          )}

          {activeTab === "Terminal" && (
            isAnalyzing ? (
              <LoadingState symbol={symbol} riskProfile={riskProfile} />
            ) : recommendation ? (
              <ResultsScreen
                inferredCapital={inferredCapital}
                latestComputedAt={latestComputedAt}
                recommendation={recommendation}
                riskProfile={riskProfile}
                styles={activeStyles}
                onOpenOutcomeModal={() => setShowOutcomeModal(true)}
                onStartOver={() => {
                  setRecommendation(null);
                  setError(null);
                }}
              />
            ) : (
              <LandingScreen
                error={error}
                health={health}
                isBootstrapping={isBootstrapping}
                portfolio={portfolio}
                riskProfile={riskProfile}
                setRiskProfile={setRiskProfile}
                setSymbol={setSymbol}
                supportingStats={supportingStats}
                symbol={symbol}
                onAnalyze={() => handleAnalyze(symbol)}
              />
            )
          )}
        </main>
      </div>

      {recommendation && showOutcomeModal ? (
        <OutcomeModal
          error={error}
          isSavingOutcome={isSavingOutcome}
          outcomeHorizonDays={outcomeHorizonDays}
          outcomeLabel={outcomeLabel}
          outcomeReturnPct={outcomeReturnPct}
          recommendation={recommendation}
          setOutcomeHorizonDays={setOutcomeHorizonDays}
          setOutcomeLabel={setOutcomeLabel}
          setOutcomeReturnPct={setOutcomeReturnPct}
          onClose={() => setShowOutcomeModal(false)}
          onSubmit={handleOutcomeSubmit}
        />
      ) : null}
    </div>
  );
}

function TopBar({
  activeTab,
  setActiveTab,
  healthLabel,
  userEmail,
  onSignOut,
  onResetTerminal,
}: {
  activeTab: TabId;
  setActiveTab: (val: TabId) => void;
  healthLabel: string;
  userEmail?: string;
  onSignOut: () => void;
  onResetTerminal: () => void;
}) {
  const navItems: { label: string; id: TabId }[] = [
    { label: "Portfolio", id: "Portfolio" },
    { label: "Opportunity Radar", id: "Signals" },
  ];

  return (
    <header className="glass-panel fixed inset-x-0 top-0 z-50 flex h-14 items-center justify-between px-4 md:px-6 border-b border-slate-200/50">
      <div className="flex items-center gap-6">
        <span className="font-serif text-xl italic text-[color:var(--primary)] cursor-pointer" onClick={onResetTerminal}>
          ET GENAI
        </span>
        <nav className="hidden items-center gap-6 text-sm text-slate-500 md:flex">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={
                activeTab === item.id
                  ? "border-b-2 border-[color:var(--primary)] pb-[17px] pt-[17px] font-semibold text-[color:var(--primary)] transition-all"
                  : "pb-[17px] pt-[17px] hover:text-slate-800 transition-colors"
              }
            >
              {item.label}
            </button>
          ))}
        </nav>
      </div>
      <div className="flex items-center gap-6">
        {userEmail && (
          <div className="hidden items-center gap-4 border-r border-slate-200 pr-6 md:flex">
            <span className="font-mono text-[10px] uppercase tracking-widest text-slate-400">
              Authenticated:
            </span>
            <span className="text-sm font-semibold text-slate-700">
              {userEmail}
            </span>
          </div>
        )}
        <div className="flex items-center gap-3">
          <div className="rounded-full bg-[color:var(--surface-low)] px-3 py-1 text-[10px] uppercase tracking-[0.22em] text-slate-600">
            <span className="mr-2 inline-block h-2 w-2 rounded-full bg-emerald-500" />
            {healthLabel}
          </div>
          <button
            onClick={onSignOut}
            className="rounded-xl px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
          >
            Sign Out
          </button>
        </div>
      </div>
    </header>
  );
}

function SideBar({ 
  activeTab, 
  setActiveTab,
  onResetTerminal
}: { 
  activeTab: TabId; 
  setActiveTab: (val: TabId) => void;
  onResetTerminal: () => void;
}) {
  const items: { label: string; id: TabId }[] = [
    { label: "Terminal", id: "Terminal" },
    { label: "Memory Log", id: "Memory" },
  ];

  return (
    <aside className="fixed left-0 top-14 hidden h-[calc(100vh-56px)] w-64 flex-col bg-[color:var(--surface-low)] px-4 py-8 md:flex border-r border-slate-200/50">
      <div className="mb-10 px-2">
        <div className="mb-1 flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg primary-gradient text-white shadow-sm">
            AI
          </div>
          <span className="font-serif text-lg font-bold">v2.5.0-Alpha</span>
        </div>
        <p className="pl-12 text-[10px] uppercase tracking-[0.24em] text-slate-400 font-semibold">
          Institutional Grade
        </p>
      </div>
      <nav className="flex-1 space-y-2">
        <div className="mb-4 px-3 text-[10px] uppercase tracking-[0.24em] text-slate-400 font-bold">
          Core Engines
        </div>
        {items.map((item) => (
          <button
            onClick={() => {
              if (item.id === "Terminal") {
                onResetTerminal();
              } else {
                setActiveTab(item.id);
              }
            }}
            className={
              activeTab === item.id
                ? "w-full text-left rounded-xl bg-white px-4 py-3 text-sm font-bold text-[color:var(--primary)] editorial-shadow transition-all"
                : "w-full text-left px-4 py-3 text-sm font-medium text-slate-500 hover:text-slate-800 hover:bg-slate-200/50 rounded-xl transition-all"
            }
            key={item.id}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <button 
        onClick={onResetTerminal}
        className="primary-gradient editorial-shadow rounded-xl px-4 py-3.5 text-sm font-bold text-white uppercase tracking-wider transition-transform hover:-translate-y-0.5"
      >
        New Analysis
      </button>
    </aside>
  );
}

function SignalsRadarScreen({ onDeployAgent }: { onDeployAgent: (symbol: string) => void }) {
  const signals = [
    { 
      symbol: "TATASTEEL", 
      layer: "Layer 4",
      type: "Management Commentary", 
      time: "2m ago", 
      confidence: 88, 
      color: "var(--primary)",
      description: "NLP sentiment analysis on Q3 earnings call transcript. Detected high-conviction semantic shift: management swapped 'expansion' for 'consolidation' and 'right-sizing', an early indicator of margin defense." 
    },
    { 
      symbol: "INFY", 
      layer: "Layer 3",
      type: "Insider Cluster", 
      time: "14m ago", 
      confidence: 82, 
      color: "var(--success)",
      description: "Multiple Form C/D filings detected on SEBI disclosure portal. Promoter buying cluster (3 insiders) over a 2-week window during prolonged stock underperformance." 
    },
    { 
      symbol: "RELIANCE", 
      layer: "Layer 2",
      type: "Technical Pattern", 
      time: "1h ago", 
      confidence: 76, 
      color: "var(--warning)",
      description: "52-week breakout detected with 300% volume confirmation. Price has reclaimed the 20/50 EMA supply zone with positive RSI divergence on the daily timeframe." 
    },
    { 
      symbol: "ZOMATO", 
      layer: "Layer 1",
      type: "XBRL Filing", 
      time: "3h ago", 
      confidence: 68, 
      color: "var(--danger)",
      description: "XBRL-structured quarterly results show significant revenue surprise (+14%) against consensus estimates. Real-time NSE/BSE exchange filing processed under LODR regulations." 
    }
  ];

  return (
    <div className="mx-auto max-w-[1000px] px-6 py-12">
      <div className="mb-10">
        <h1 className="font-serif text-4xl mb-3">Opportunity Radar</h1>
        <p className="text-slate-500 max-w-2xl leading-relaxed">
          The AI continuously monitors 4 distinct signal layers across the NSE: Corporate Filings, Technical Patterns, Insider Flows, and Management Commentary NLP. Anomalies are surfaced below. Deploy the agentic pipeline to autonomously synthesize a trading plan.
        </p>
      </div>

      <div className="space-y-6">
        {signals.map((signal, i) => (
          <div key={i} className="bg-white rounded-[20px] p-6 editorial-shadow border border-slate-100 flex flex-col md:flex-row gap-6 md:items-center justify-between group hover:border-[color:var(--primary)]/30 transition-colors">
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-3 mb-3">
                <span className="font-mono text-xl font-bold bg-slate-50 px-2 py-1 rounded">{signal.symbol}</span>
                <span className="text-[10px] uppercase tracking-widest text-[color:var(--primary)] font-bold bg-[color:var(--surface-low)] px-3 py-1 rounded-full">{signal.layer}</span>
                <span className="text-[10px] uppercase tracking-widest text-slate-500 font-bold bg-slate-100 px-3 py-1 rounded-full">{signal.type}</span>
                <span className="text-[10px] uppercase tracking-[0.2em] font-mono text-slate-400">{signal.time}</span>
              </div>
              <p className="text-sm text-slate-600 leading-relaxed pr-4">
                {signal.description}
              </p>
            </div>
            
            <div className="flex flex-row md:flex-col items-center md:items-end gap-3 md:gap-4 md:pl-6 md:border-l border-slate-100 min-w-[180px]">
               <div className="flex flex-col items-start md:items-end w-full">
                 <span className="text-[10px] uppercase tracking-[0.2em] text-slate-400 mb-1">Signal Strength</span>
                 <div className="flex items-center gap-2 w-full justify-end">
                   <div className="h-2 flex-1 max-w-[80px] bg-slate-100 rounded-full overflow-hidden">
                     <div className="h-full rounded-full" style={{ width: `${signal.confidence}%`, backgroundColor: signal.color }} />
                   </div>
                   <span className="font-mono text-sm font-bold w-10 text-right" style={{ color: signal.color }}>{signal.confidence}%</span>
                 </div>
               </div>
               <button 
                onClick={() => onDeployAgent(signal.symbol)}
                className="ml-auto md:ml-0 w-full text-center bg-[color:var(--surface-low)] hover:bg-[color:var(--primary)] hover:text-white transition-all text-[color:var(--primary)] font-semibold text-xs uppercase tracking-widest px-6 py-3 rounded-xl border border-[color:var(--primary)]/10 hover:border-[color:var(--primary)]"
               >
                 Deploy Agent →
               </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PortfolioScreen({ portfolio }: { portfolio: UserPortfolio }) {
  const holdings = portfolio.holdings || [];
  
  return (
    <div className="mx-auto max-w-[1000px] px-6 py-12">
      <div className="mb-10 flex items-end justify-between">
        <div>
          <h1 className="font-serif text-4xl mb-3">Institutional Portfolio</h1>
          <p className="text-slate-500 max-w-2xl leading-relaxed">
            Personalized context used by the AI Agent for trade sizing and risk management. High-conviction signals are scaled based on your current sector exposure and liquidity.
          </p>
        </div>
        <div className="text-right pb-1">
          <span className="text-[10px] uppercase tracking-[0.22em] text-slate-400 font-bold block mb-1">Total Liquidity</span>
          <span className="font-mono text-3xl font-bold">{formatCurrency(portfolio.total_capital)}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
        <section className="bg-white rounded-[20px] p-8 border border-slate-100 editorial-shadow">
          <h3 className="text-xs uppercase tracking-widest text-slate-400 font-bold mb-6">Risk Profile</h3>
          <div className="flex items-center gap-4">
             <div className="primary-gradient w-12 h-12 rounded-xl flex items-center justify-center text-white font-bold">M</div>
             <div>
               <p className="font-serif text-xl font-bold">Moderate-Aggressive</p>
               <p className="text-xs text-slate-500">Max Drwdown Target: 12%</p>
             </div>
          </div>
        </section>
        
        <section className="bg-white rounded-[20px] p-8 border border-slate-100 editorial-shadow md:col-span-2 flex items-center justify-between">
           <div className="flex-1 border-r border-slate-100 pr-8">
             <h3 className="text-xs uppercase tracking-widest text-slate-400 font-bold mb-4">Capital Utilization</h3>
             <div className="h-3 bg-slate-100 rounded-full overflow-hidden mb-2">
               <div className="h-full bg-[color:var(--primary)]" style={{ width: '42%' }} />
             </div>
             <p className="text-xs text-slate-500">42% Deployed · 58% Reserve Liquidity</p>
           </div>
           <div className="pl-8">
             <h3 className="text-xs uppercase tracking-widest text-slate-400 font-bold mb-2">Active Nodes</h3>
             <p className="font-mono text-2xl font-bold text-emerald-500">08/08</p>
             <p className="text-[10px] text-slate-400 uppercase tracking-widest">Healthy</p>
           </div>
        </section>
      </div>

      <section className="bg-white rounded-[24px] overflow-hidden border border-slate-100 editorial-shadow">
        <div className="bg-slate-50/50 px-8 py-4 border-b border-slate-100 flex items-center justify-between">
          <h2 className="font-serif text-xl font-bold">Current Holdings</h2>
          <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">Real-time valuation provided by YFinance</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-50">
                <th className="px-8 py-5 text-[10px] uppercase tracking-widest text-slate-400 font-bold">Asset</th>
                <th className="px-8 py-5 text-[10px] uppercase tracking-widest text-slate-400 font-bold">Quantity</th>
                <th className="px-8 py-5 text-[10px] uppercase tracking-widest text-slate-400 font-bold text-right">Value</th>
                <th className="px-8 py-5 text-[10px] uppercase tracking-widest text-slate-400 font-bold text-right">Avg Price</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {holdings.length > 0 ? holdings.map((asset: any, i: number) => (
                <tr key={i} className="group hover:bg-slate-50/50 transition-colors">
                  <td className="px-8 py-6">
                    <div className="font-mono text-lg font-bold">{asset.symbol}</div>
                    <div className="text-xs text-slate-400 font-mono uppercase">SECTOR: {asset.sector || 'GENERAL'}</div>
                  </td>
                  <td className="px-8 py-6">
                    <div className="font-mono text-sm">{asset.quantity} units</div>
                  </td>
                  <td className="px-8 py-6 text-right font-mono font-bold">
                    {formatCurrency(asset.quantity * asset.avg_price)}
                  </td>
                  <td className="px-8 py-6 text-right font-mono text-slate-500">
                    {formatCurrency(asset.avg_price)}
                  </td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={4} className="px-8 py-12 text-center text-slate-400 italic">
                    No active holdings detected in institutional vault.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function MemoryScreen() {
  const history = [
    { symbol: "RELIANCE", pattern: "Mean Reversion", date: "2 days ago", outcome: "WIN", return: 4.2, status: "Verified" },
    { symbol: "ZOMATO", pattern: "Volume Breakout", date: "5 days ago", outcome: "WIN", return: 8.7, status: "Verified" },
    { symbol: "WIPRO", pattern: "Structural Alignment", date: "1 week ago", outcome: "LOSS", return: -2.1, status: "Verified" },
    { symbol: "HDFCBANK", pattern: "Options Floor", date: "10 days ago", outcome: "WIN", return: 3.5, status: "Verified" },
  ];

  return (
    <div className="mx-auto max-w-[1000px] px-6 py-12">
       <div className="mb-10">
        <h1 className="font-serif text-4xl mb-3">Model Memory Log</h1>
        <p className="text-slate-500 max-w-2xl leading-relaxed">
          Historical breakdown of every autonomous decision made by the AI. This data is fed back into the <span className="text-[color:var(--primary)] font-bold italic">pattern_memory</span> module to refine future confidence scores.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10">
         <div className="bg-white p-6 rounded-[20px] border border-slate-100 editorial-shadow">
            <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-2">Hit Rate</p>
            <p className="font-mono text-3xl font-bold text-[color:var(--primary)]">75.0%</p>
         </div>
         <div className="bg-white p-6 rounded-[20px] border border-slate-100 editorial-shadow">
            <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-2">Avg. Return</p>
            <p className="font-mono text-3xl font-bold text-emerald-500">+3.58%</p>
         </div>
         <div className="bg-white p-6 rounded-[20px] border border-slate-100 editorial-shadow">
            <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-2">Trades Analyzed</p>
            <p className="font-mono text-3xl font-bold">142</p>
         </div>
         <div className="bg-white p-6 rounded-[20px] border border-slate-100 editorial-shadow">
            <p className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-2">Active Signals</p>
            <p className="font-mono text-3xl font-bold text-amber-500">03</p>
         </div>
      </div>

      <div className="bg-white rounded-[24px] overflow-hidden border border-slate-100 editorial-shadow">
         <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-50">
                <th className="px-8 py-5 text-[10px] uppercase tracking-widest text-slate-400 font-bold">Symbol</th>
                <th className="px-8 py-5 text-[10px] uppercase tracking-widest text-slate-400 font-bold">Pattern Alignment</th>
                <th className="px-8 py-5 text-[10px] uppercase tracking-widest text-slate-400 font-bold">Date</th>
                <th className="px-8 py-5 text-[10px] uppercase tracking-widest text-slate-400 font-bold">Outcome</th>
                <th className="px-8 py-5 text-[10px] uppercase tracking-widest text-slate-400 font-bold text-right">Realized Return</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {history.map((record, i) => (
                <tr key={i} className="hover:bg-slate-50/50 transition-colors">
                  <td className="px-8 py-6">
                    <div className="font-mono font-bold">{record.symbol}</div>
                  </td>
                  <td className="px-8 py-6">
                    <div className="text-sm font-medium text-slate-700">{record.pattern}</div>
                  </td>
                  <td className="px-8 py-6">
                    <div className="text-xs text-slate-500 font-mono uppercase">{record.date}</div>
                  </td>
                  <td className="px-8 py-6">
                    <span className={`text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-full ${record.outcome === 'WIN' ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-600'}`}>
                      {record.outcome}
                    </span>
                  </td>
                  <td className={`px-8 py-6 text-right font-mono font-bold ${record.return > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                    {record.return > 0 ? '+' : ''}{record.return}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function LandingScreen({
  error,
  health,
  isBootstrapping,
  portfolio,
  riskProfile,
  setRiskProfile,
  setSymbol,
  supportingStats,
  symbol,
  onAnalyze,
}: {
  error: string | null;
  health: HealthResponse | null;
  isBootstrapping: boolean;
  portfolio: UserPortfolio;
  riskProfile: RiskProfile;
  setRiskProfile: (value: RiskProfile) => void;
  setSymbol: (value: string) => void;
  supportingStats: { label: string; title: string; value: string }[];
  symbol: string;
  onAnalyze: () => void;
}) {
  return (
    <div className="mx-auto max-w-[1280px] px-6 py-16 md:px-16 md:py-24">
      <section className="mb-16 max-w-3xl">
        <h1 className="text-balance mb-6 font-serif text-5xl leading-[1.05] md:text-7xl">
          Intelligent Capital
          <br />
          <span className="italic text-[color:var(--primary)]">Deployment.</span>
        </h1>
        <p className="max-w-2xl text-lg leading-8 text-slate-600">
          Execute high-precision market analysis using the AI Investor backend.
          The workflow is live-wired to the verified FastAPI service and returns a
          recommendation, price plan, setup memory, and portfolio-aware sizing.
        </p>
      </section>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        <section className="editorial-shadow rounded-[20px] bg-white p-8 lg:col-span-8">
          <span className="mb-6 block text-xs uppercase tracking-[0.28em] text-slate-400">
            Investment Persona
          </span>
          <div className="mb-12 flex w-fit flex-wrap gap-2 rounded-2xl bg-[color:var(--surface-low)] p-1.5">
            {RISK_OPTIONS.map((option) => (
              <button
                className={
                  option.value === riskProfile
                    ? "rounded-xl bg-white px-6 py-2.5 text-sm font-semibold text-[color:var(--primary)] shadow-sm"
                    : "rounded-xl px-6 py-2.5 text-sm font-semibold text-slate-500"
                }
                key={option.value}
                onClick={() => setRiskProfile(option.value)}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>

          <label className="mb-4 block text-xs uppercase tracking-[0.28em] text-slate-400">
            Asset Identification
          </label>
          <div className="max-w-xl">
            <input
              className="w-full rounded-2xl bg-[color:var(--surface-low)] px-5 py-5 font-mono text-xl uppercase outline-none placeholder:font-sans placeholder:text-base placeholder:normal-case placeholder:text-slate-400 focus:ring-2 focus:ring-[color:var(--primary)]/20"
              onChange={(event) => setSymbol(event.target.value.toUpperCase())}
              placeholder="Search NSE symbol (e.g. TATASTEEL)"
              value={symbol}
            />
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-2">
            <span className="mr-2 text-[10px] uppercase tracking-[0.26em] text-slate-400">
              Top Tickers:
            </span>
            {SYMBOLS.map((item) => (
              <button
                className="rounded-lg bg-[color:var(--surface-low)] px-3 py-1.5 font-mono text-xs text-slate-700"
                key={item}
                onClick={() => setSymbol(item)}
                type="button"
              >
                {item}
              </button>
            ))}
          </div>

          <div className="mt-14 flex flex-col gap-4 border-t border-slate-100 pt-8 md:flex-row md:items-center md:justify-between">
            <div className="space-y-1 text-sm text-slate-500">
              <p>Backend status: {health?.status ?? "checking"}</p>
              <p>Bootstrap capital: {formatCurrency(portfolio.total_capital)}</p>
              <p>Bootstrap holdings: {portfolio.holdings.length}</p>
            </div>
            <button
              className="primary-gradient editorial-shadow rounded-2xl px-10 py-4 text-base font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
              disabled={isBootstrapping || !symbol.trim()}
              onClick={onAnalyze}
              type="button"
            >
              Analyse
            </button>
          </div>

          {error ? (
            <div className="mt-6 rounded-2xl bg-[rgba(127,29,29,0.08)] px-5 py-4 text-sm text-[color:var(--danger)]">
              {error}
            </div>
          ) : null}
        </section>

        <section className="space-y-8 lg:col-span-4">
          <div className="relative overflow-hidden rounded-[20px] bg-[color:var(--surface-low)] p-6">
            <span className="text-xs uppercase tracking-[0.26em] text-[color:var(--primary)]">
              Market Sentiment
            </span>
            <div className="mt-4 flex items-end gap-2">
              <span className="font-serif text-4xl">Operational</span>
              <span className="mb-1 font-mono text-sm text-emerald-600">
                {health?.env ?? "dev"}
              </span>
            </div>
            <p className="mt-4 text-sm leading-7 text-slate-500">
              The browser talks to `/api/*` while Next route handlers proxy to the
              Python service. That keeps the frontend same-origin and avoids direct
              browser dependency on backend host configuration.
            </p>
          </div>

          <div className="overflow-hidden rounded-[20px] bg-slate-950 p-6 text-white">
            <div className="mb-8 flex items-start justify-between">
              <div>
                <h3 className="font-serif text-lg italic">Neural Stream</h3>
                <p className="text-xs text-slate-400">Live Recommendation Surface</p>
              </div>
              <span className="font-mono text-xs uppercase tracking-[0.24em] text-emerald-400">
                Online
              </span>
            </div>
            <div className="flex h-24 items-end gap-1 rounded-xl bg-white/5 px-2 pb-2">
              {[34, 57, 42, 78, 63, 55, 92].map((height) => (
                <div
                  className="w-full rounded-t-sm bg-emerald-400/80"
                  key={height}
                  style={{ height: `${height}%` }}
                />
              ))}
            </div>
            <p className="mt-4 text-center font-mono text-[11px] uppercase tracking-[0.28em] text-slate-500">
              Confidence-ready output via `/api/analyze`
            </p>
          </div>
        </section>
      </div>

      <section className="mt-16 grid grid-cols-2 gap-8 md:grid-cols-4">
        {supportingStats.map((stat) => (
          <div className="border-l-2 border-slate-200 pl-6" key={stat.label}>
            <span className="mb-1 block text-xs uppercase tracking-[0.24em] text-slate-400">
              {stat.label}
            </span>
            <span className="block font-mono text-lg font-semibold">
              {stat.title}
            </span>
            <span className="block font-mono text-sm text-slate-500">
              {stat.value}
            </span>
          </div>
        ))}
      </section>
    </div>
  );
}

function LoadingState({
  symbol,
  riskProfile,
}: {
  symbol: string;
  riskProfile: RiskProfile;
}) {
  const steps = [
    "Fetching Data",
    "Signal Processing",
    "Pattern Recognition",
    "Risk Assessment",
    "Final Decision",
  ];

  return (
    <div className="mx-auto max-w-7xl px-6 py-8 md:px-10">
      <div className="mb-12">
        <div className="relative mx-auto flex max-w-4xl items-center justify-between">
          <div className="absolute left-0 right-0 top-4 h-0.5 bg-[color:var(--surface-high)]" />
          {steps.map((step, index) => (
            <div className="relative flex flex-col items-center gap-2" key={step}>
              <div
                className={
                  index < 1
                    ? "flex h-8 w-8 items-center justify-center rounded-full bg-[color:var(--primary)] text-white ring-4 ring-[color:var(--background)]"
                    : index === 1
                      ? "flex h-8 w-8 items-center justify-center rounded-full bg-[color:var(--primary)] text-white ring-4 ring-[color:var(--background)]"
                      : "flex h-8 w-8 items-center justify-center rounded-full bg-[color:var(--surface-high)] text-slate-500 ring-4 ring-[color:var(--background)]"
                }
              >
                {index < 1 ? "✓" : index === 1 ? "•" : index + 1}
              </div>
              <span
                className={
                  index <= 1
                    ? "font-serif text-xs font-semibold text-[color:var(--primary)]"
                    : "font-serif text-xs text-slate-500"
                }
              >
                {step}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-10">
        <div className="space-y-8 lg:col-span-6">
          <section className="editorial-shadow animate-pulse rounded-[20px] bg-white p-8">
            <div className="mb-6 flex items-start justify-between">
              <div className="w-2/3 space-y-4">
                <div className="h-6 w-24 rounded bg-[color:var(--surface-low)]" />
                <div className="h-12 rounded bg-[color:var(--surface-low)]" />
                <div className="h-4 w-1/2 rounded bg-[color:var(--surface-low)]" />
              </div>
              <div className="h-20 w-20 rounded-full bg-[color:var(--surface-low)]" />
            </div>
            <div className="h-24 rounded-xl bg-[color:var(--surface-low)]" />
          </section>

          <section className="grid grid-cols-1 gap-6 md:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <div
                className="editorial-shadow h-48 animate-pulse rounded-[20px] bg-white p-6"
                key={index}
              >
                <div className="mb-4 h-4 w-20 rounded bg-[color:var(--surface-low)]" />
                <div className="mb-3 h-10 rounded bg-[color:var(--surface-low)]" />
                <div className="h-4 w-2/3 rounded bg-[color:var(--surface-low)]" />
              </div>
            ))}
          </section>
        </div>

        <aside className="space-y-6 lg:col-span-4">
          <div className="rounded-[20px] bg-[color:var(--surface-low)] p-6">
            <span className="mb-3 block font-mono text-xs uppercase tracking-[0.28em] text-slate-500">
              Active Request
            </span>
            <p className="font-serif text-3xl">Processing {symbol}</p>
            <p className="mt-4 text-sm leading-7 text-slate-500">
              Building a {riskProfile} recommendation by running signal detection,
              context enrichment, technical analysis, decisioning, and
              personalization against the live backend.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
}

function ResultsScreen({
  inferredCapital,
  latestComputedAt,
  recommendation,
  riskProfile,
  styles,
  onOpenOutcomeModal,
  onStartOver,
}: {
  inferredCapital: number;
  latestComputedAt: string;
  recommendation: RecommendationResponse;
  riskProfile: RiskProfile;
  styles: { badge: string; accent: string; tone: string; eyebrow: string };
  onOpenOutcomeModal: () => void;
  onStartOver: () => void;
}) {
  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-4 bg-[color:var(--surface-low)] px-8 py-6">
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <button
            className="font-semibold text-[color:var(--primary)]"
            onClick={onStartOver}
            type="button"
          >
            ← New Analysis
          </button>
          <span className="text-slate-300">|</span>
          <div className="flex items-center gap-2">
            <span className="text-slate-500">Symbol:</span>
            <span className="rounded bg-white px-2 py-1 font-mono font-bold shadow-sm">
              {recommendation.symbol}
            </span>
          </div>
          <span className="text-slate-300">|</span>
          <div className="flex items-center gap-2">
            <span className="text-slate-500">Risk:</span>
            <span className="rounded-full bg-[rgba(146,64,14,0.1)] px-3 py-1 text-xs font-bold uppercase tracking-[0.2em] text-[color:var(--warning)]">
              {riskProfile}
            </span>
          </div>
        </div>
        <div className="font-mono text-xs text-slate-500">
          Last Computed: {latestComputedAt}
        </div>
      </header>

      <div className="grid grid-cols-1 gap-8 p-8 lg:grid-cols-12">
        <div className="space-y-8 lg:col-span-8">
          <section className="editorial-shadow relative overflow-hidden rounded-[20px] bg-white p-8">
            <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className={`rounded-lg px-6 py-1.5 text-lg font-bold ${styles.badge}`}>
                    {recommendation.action}
                  </span>
                  <span className={`rounded-sm px-3 py-1 text-xs font-bold uppercase tracking-[0.22em] ${styles.tone}`}>
                    {recommendation.conviction_mode.replaceAll("_", " ")}
                  </span>
                </div>
                <h1 className="font-serif text-4xl leading-tight">
                  {styles.eyebrow}
                </h1>
              </div>
              <div className="text-right">
                <div className="font-mono text-3xl font-bold">
                  {formatCurrency(recommendation.entry_price)}
                </div>
                <div className="mt-1 text-xs uppercase tracking-[0.2em] text-slate-500">
                  Current CMP
                </div>
              </div>
            </div>

            <p className="mb-8 max-w-2xl text-lg leading-8 text-slate-700">
              {recommendation.summary}
            </p>

            <div className="space-y-2">
              <div className="mb-1 flex items-end justify-between">
                <span className="text-xs uppercase tracking-[0.26em] text-slate-500">
                  System Confidence
                </span>
                <span className="font-mono font-bold text-[color:var(--primary)]">
                  {formatPercent(recommendation.confidence_pct)}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-[color:var(--surface-high)]">
                <div
                   className="h-full transition-all duration-500"
                   style={{ 
                     width: `${recommendation.confidence_pct}%`,
                     backgroundColor: recommendation.confidence_pct < 30 
                       ? 'var(--danger)' 
                       : recommendation.confidence_pct < 60 
                         ? 'var(--warning)' 
                         : 'var(--primary)'
                   }}
                />
              </div>
            </div>
          </section>

          {recommendation.action !== "AVOID" && recommendation.confidence_pct >= 30 ? (
            <section className="editorial-shadow rounded-[20px] bg-white p-8">
              <h3 className="mb-6 text-xs uppercase tracking-[0.28em] text-slate-500">
                Execution Plan
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3">
                <div className="py-4 md:pr-8">
                  <p className="mb-2 text-xs text-slate-500">Ideal Entry Range</p>
                  <p className="font-mono text-2xl font-bold">
                    {formatCurrency(recommendation.entry_price * 0.99)} - {" "}
                    {formatCurrency(recommendation.entry_price * 1.01)}
                  </p>
                </div>
                <div className="border-y border-[color:var(--surface-high)] py-4 md:border-x md:border-y-0 md:px-8">
                  <p className="mb-2 text-xs text-slate-500">Profit Target</p>
                  <p className="font-mono text-2xl font-bold text-[color:var(--success)]">
                    {formatCurrency(recommendation.target_price)}
                  </p>
                  <p className="mt-1 text-[10px] text-slate-500">
                    Potential Upside:{" "}
                    {formatPercent(
                      ((recommendation.target_price - recommendation.entry_price) /
                        recommendation.entry_price) *
                        100,
                    )}
                  </p>
                </div>
                <div className="py-4 md:pl-8">
                  <p className="mb-2 text-xs text-slate-500">Stop Loss</p>
                  <p className="font-mono text-2xl font-bold text-[color:var(--danger)]">
                    {formatCurrency(recommendation.stop_loss)}
                  </p>
                  <p className="mt-1 text-[10px] text-slate-500">
                    Risk per unit:{" "}
                    {formatCurrency(recommendation.entry_price - recommendation.stop_loss)}
                  </p>
                </div>
              </div>
            </section>
          ) : (
            <section className="rounded-[20px] border-2 border-dashed border-[color:var(--outline-variant)]/30 p-8 text-center bg-slate-50/30">
              <p className="font-serif text-xl italic text-slate-500">
                {recommendation.action === "AVOID" 
                  ? "Execution plan suppressed. System recommends capital preservation." 
                  : "Execution plan hidden due to low structural confidence (< 30%). Wait for stronger alignment."}
              </p>
            </section>
          )}

          <section className="rounded-[20px] bg-[color:var(--surface-low)] p-8">
            <div className="mb-4 flex items-center gap-3">
              <span className="font-mono text-sm uppercase tracking-[0.22em] text-[color:var(--primary)]">
                Analyst Intelligence Note
              </span>
            </div>
            <p className="mb-4 leading-8 text-slate-700">{recommendation.analyst_note}</p>
            <details className="group cursor-pointer">
              <summary className="list-none font-semibold text-[color:var(--primary)]">
                Full Reasoning
                <span className="ml-2 inline-block transition-transform group-open:rotate-180">
                  ˅
                </span>
              </summary>
              <div className="mt-4 border-t border-[color:var(--outline-variant)]/20 pt-4 text-sm leading-7 text-slate-600">
                <p>{recommendation.reasoning}</p>
                <p className="mt-3">{recommendation.confidence_note}</p>
              </div>
            </details>
          </section>

          <section className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <SignalList
              accent="text-[color:var(--success)]"
              border="border-[color:var(--success)]"
              items={recommendation.confirmation_triggers}
              title="Confirmation Triggers"
            />
            <SignalList
              accent="text-[color:var(--danger)]"
              border="border-[color:var(--danger)]"
              items={recommendation.invalidation_triggers}
              title="Invalidation Triggers"
            />
          </section>

          <section className="rounded-[20px] border border-[color:var(--outline-variant)]/15 bg-white p-8">
            <div className="mb-8 flex items-center justify-between gap-4">
              <div>
                <h3 className="mb-1 text-xs uppercase tracking-[0.26em] text-slate-500">
                  Pattern Memory
                </h3>
                <p className="font-serif text-2xl font-bold">
                  {recommendation.setup_memory.pattern_name.replaceAll("_", " ")}
                </p>
              </div>
              <div className="text-right">
                <div className="font-mono text-2xl font-bold text-[color:var(--primary)]">
                  {recommendation.setup_memory.similar_setups > 0 
                    ? formatPercent(recommendation.setup_memory.success_rate * 100)
                    : "0%"}
                </div>
                <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">
                  {recommendation.setup_memory.similar_setups > 0 
                    ? "Historical Success" 
                    : "No Data Found"}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
              <MetricCard
                label="Similar Setups"
                value={String(recommendation.setup_memory.similar_setups)}
              />
              <MetricCard
                label="Exact Matches"
                value={String(recommendation.setup_memory.exact_matches)}
              />
              <MetricCard
                label="Avg. Return"
                value={recommendation.setup_memory.similar_setups > 0 
                  ? formatPercent(recommendation.setup_memory.avg_return_pct)
                  : "N/A"}
              />
              <MetricCard
                label="Target Hits"
                value={String(recommendation.setup_memory.target_hits)}
              />
              <MetricCard
                label="Stop-Loss Hits"
                value={String(recommendation.setup_memory.stop_loss_hits)}
              />
              <MetricCard
                label="Market Regime"
                value={recommendation.setup_memory.market_condition}
              />
            </div>
          </section>
        </div>

        <aside className="space-y-6 lg:col-span-4">
          <section className="rounded-[20px] bg-[color:var(--surface-low)] p-6">
            <span className="mb-2 block text-xs uppercase tracking-[0.26em] text-slate-500">
              Portfolio Action
            </span>
            <p className={`font-serif text-3xl ${recommendation.allocation_pct > 0 ? styles.accent : 'text-slate-400'}`}>
              {recommendation.allocation_pct > 0 ? formatPercent(recommendation.allocation_pct) : "0.0% Allocation"}
            </p>
            <p className="mt-3 text-sm leading-7 text-slate-600">
              {recommendation.allocation_pct > 0 
                ? `Allocate ${formatCurrency(recommendation.allocation_amount)} with same-sector exposure currently at ${formatPercent(recommendation.sector_exposure_pct)}.`
                : "No capital deployment recommended for this risk profile. Maintain current liquidity."}
            </p>
            <p className="mt-4 rounded-2xl bg-white px-4 py-3 text-sm text-slate-600">
              {recommendation.next_step}
            </p>
            {recommendation.personalization_warning ? (
              <p className="mt-4 rounded-2xl bg-[rgba(146,64,14,0.1)] px-4 py-3 text-sm text-[color:var(--warning)]">
                {recommendation.personalization_warning}
              </p>
            ) : null}
          </section>

          <section className="editorial-shadow rounded-[20px] bg-white p-6">
            <div className="mb-6 flex items-center justify-between gap-4">
              <div>
                <h2 className="font-serif text-2xl font-bold">Active Signal Outcomes</h2>
                <p className="text-sm text-slate-500">
                  Record realized performance back into setup memory.
                </p>
              </div>
              <button
                className="primary-gradient rounded-xl px-4 py-2 text-sm font-semibold text-white"
                onClick={onOpenOutcomeModal}
                type="button"
              >
                Record Outcome
              </button>
            </div>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className="font-mono text-lg font-bold">
                      {recommendation.symbol}
                    </span>
                    <span className="rounded bg-[color:var(--surface-low)] px-2 py-0.5 font-mono text-[10px] uppercase text-slate-500">
                      {recommendation.setup_memory.market_condition}
                    </span>
                    <span className="text-xs text-slate-400">·</span>
                    <span className="text-xs font-medium text-slate-500">
                      {recommendation.setup_memory.pattern_name.replaceAll("_", " ")}
                    </span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-xs uppercase tracking-[0.2em] text-slate-400">
                    Status
                  </div>
                  <div className="text-xs font-bold text-[color:var(--warning)]">
                    Pending Record
                  </div>
                </div>
              </div>
              <div className="rounded-2xl bg-[color:var(--surface-low)] p-4 text-sm text-slate-600">
                Backend source map: signals {recommendation.sources.signals.join(", ")},
                historical {recommendation.sources.historical}, market {" "}
                {recommendation.sources.market}, technical {recommendation.sources.technical}.
              </div>
            </div>
          </section>

          <section className="rounded-[20px] bg-slate-950 p-6 text-white">
            <span className="mb-2 block font-mono text-xs uppercase tracking-[0.26em] text-slate-500">
              Watch Next
            </span>
            <ul className="space-y-3">
              {recommendation.watch_next.map((item) => (
                <li className="leading-7 text-slate-200" key={item}>
                  {item}
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-[20px] bg-white p-6">
            <span className="mb-2 block text-xs uppercase tracking-[0.26em] text-slate-500">
              Portfolio Snapshot
            </span>
            <p className="font-serif text-3xl">{formatCompactCurrency(inferredCapital)}</p>
            <p className="mt-2 text-sm text-slate-500">
              User `{recommendation.user_id}` with sizing inferred from the backend
              recommendation payload.
            </p>
          </section>
        </aside>
      </div>
    </>
  );
}

function SignalList({
  accent,
  border,
  items,
  title,
}: {
  accent: string;
  border: string;
  items: string[];
  title: string;
}) {
  return (
    <div className={`editorial-shadow rounded-[20px] border-l-4 bg-white p-6 ${border}`}>
      <h4 className={`mb-4 text-xs uppercase tracking-[0.26em] ${accent}`}>
        {title}
      </h4>
      <ul className="space-y-3">
        {items.map((item) => (
          <li className="text-sm leading-7 text-slate-700" key={item}>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-[color:var(--surface-low)] p-4 text-center">
      <p className="font-mono text-xl font-bold">{value}</p>
      <p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-slate-500">
        {label}
      </p>
    </div>
  );
}

function OutcomeModal({
  error,
  isSavingOutcome,
  outcomeHorizonDays,
  outcomeLabel,
  outcomeReturnPct,
  recommendation,
  setOutcomeHorizonDays,
  setOutcomeLabel,
  setOutcomeReturnPct,
  onClose,
  onSubmit,
}: {
  error: string | null;
  isSavingOutcome: boolean;
  outcomeHorizonDays: string;
  outcomeLabel: OutcomeLabel;
  outcomeReturnPct: string;
  recommendation: RecommendationResponse;
  setOutcomeHorizonDays: (value: string) => void;
  setOutcomeLabel: (value: OutcomeLabel) => void;
  setOutcomeReturnPct: (value: string) => void;
  onClose: () => void;
  onSubmit: () => void;
}) {
  return (
    <div className="glass-panel fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="editorial-shadow w-full max-w-2xl rounded-[24px] bg-white">
        <div className="px-8 pb-4 pt-8">
          <div className="mb-2 flex items-start justify-between gap-4">
            <div>
              <h2 className="font-serif text-3xl font-bold">Record Trade Outcome</h2>
              <p className="mt-2 text-sm text-slate-500">
                Finalize the realized performance data for the AI-generated signal.
              </p>
            </div>
            <button
              className="text-sm font-semibold text-slate-400"
              onClick={onClose}
              type="button"
            >
              Close
            </button>
          </div>
        </div>

        <div className="space-y-8 px-8 pb-8">
          <div className="grid grid-cols-2 gap-4 rounded-[20px] bg-[color:var(--surface-low)] p-5 md:grid-cols-3">
            <ReadOnlyField label="Symbol" value={recommendation.symbol} />
            <ReadOnlyField label="Action" value={recommendation.action} />
            <ReadOnlyField
              label="Pattern"
              value={recommendation.setup_memory.pattern_name}
            />
            <ReadOnlyField
              label="Entry"
              value={formatCurrency(recommendation.entry_price)}
            />
            <ReadOnlyField
              label="Target"
              value={formatCurrency(recommendation.target_price)}
            />
            <ReadOnlyField
              label="Stop"
              value={formatCurrency(recommendation.stop_loss)}
            />
          </div>

          <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
            <label className="space-y-2">
              <span className="block text-[10px] uppercase tracking-[0.22em] text-slate-500">
                Outcome Label
              </span>
              <select
                className="w-full rounded-2xl bg-[color:var(--surface-low)] px-4 py-3 outline-none"
                onChange={(event) => setOutcomeLabel(event.target.value as OutcomeLabel)}
                value={outcomeLabel}
              >
                <option value="win">win</option>
                <option value="loss">loss</option>
                <option value="neutral">neutral</option>
              </select>
            </label>

            <label className="space-y-2">
              <span className="block text-[10px] uppercase tracking-[0.22em] text-slate-500">
                Return %
              </span>
              <input
                className="w-full rounded-2xl bg-[color:var(--surface-low)] px-4 py-3 font-mono outline-none"
                onChange={(event) => setOutcomeReturnPct(event.target.value)}
                step="0.1"
                type="number"
                value={outcomeReturnPct}
              />
            </label>

            <label className="space-y-2">
              <span className="block text-[10px] uppercase tracking-[0.22em] text-slate-500">
                Horizon Days
              </span>
              <input
                className="w-full rounded-2xl bg-[color:var(--surface-low)] px-4 py-3 font-mono outline-none"
                onChange={(event) => setOutcomeHorizonDays(event.target.value)}
                type="number"
                value={outcomeHorizonDays}
              />
            </label>
          </div>

          {error ? (
            <div className="rounded-2xl bg-[rgba(127,29,29,0.08)] px-5 py-4 text-sm text-[color:var(--danger)]">
              {error}
            </div>
          ) : null}

          <div className="flex flex-col gap-3 border-t border-slate-100 pt-6 md:flex-row md:items-center md:justify-end">
            <button
              className="rounded-2xl bg-[color:var(--surface-low)] px-5 py-3 font-semibold text-slate-600"
              onClick={onClose}
              type="button"
            >
              Cancel
            </button>
            <button
              className="primary-gradient rounded-2xl px-6 py-3 font-semibold text-white disabled:opacity-60"
              disabled={isSavingOutcome}
              onClick={onSubmit}
              type="button"
            >
              {isSavingOutcome ? "Recording..." : "Record Outcome"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="mb-1 block text-[10px] uppercase tracking-[0.22em] text-slate-400">
        {label}
      </span>
      <span className="font-mono font-bold text-slate-800">{value}</span>
    </div>
  );
}
