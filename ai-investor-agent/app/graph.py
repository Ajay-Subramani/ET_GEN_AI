from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from app.config import get_settings
from app.llm_agents import run_llm_recommendation
from app.models import AgentState, FinalRecommendation
from app.nodes import AnalystNodes


def build_graph():
    nodes = AnalystNodes()
    graph = StateGraph(AgentState)
    graph.add_node("signal_detector", nodes.signal_detector)
    graph.add_node("context_enricher", nodes.context_enricher)
    graph.add_node("technical_analyzer", nodes.technical_analyzer)
    graph.add_node("decision_engine", nodes.decision_engine)
    graph.add_node("personalizer", nodes.personalizer)

    graph.add_edge(START, "signal_detector")
    graph.add_edge("signal_detector", "context_enricher")
    graph.add_edge("context_enricher", "technical_analyzer")
    graph.add_edge("technical_analyzer", "decision_engine")
    graph.add_edge("decision_engine", "personalizer")
    graph.add_edge("personalizer", END)
    return graph.compile()


def run_heuristic_recommendation(symbol: str, user_id: str, *, llm_failure: str | None = None) -> FinalRecommendation:
    from app.models import AgentStepTrace
    app = build_graph()
    result = app.invoke({"symbol": symbol.upper(), "user_id": user_id})
    rec = result["recommendation"]
    
    # Add a pseudo-trace for UI transparency in heuristic mode
    failure_note = ""
    if llm_failure:
        failure_note = f" LLM failure: {llm_failure}"
    rec.agent_trace = [
        AgentStepTrace(
            step_name="Heuristic Engine",
            objective="Analyze core market indicators using deterministic rule-base.",
            thought=(
                f"LLM Agent path was skipped or failed. Falling back to high-performance heuristic scoring for {symbol.upper()}."
                f"{failure_note}"
            ),
            model="Rule-Engine v2.0",
            output_summary=f"Detected {len(result.get('signals', []))} structural signals. Confidence score: {rec.confidence_score * 100:.1f}%."
        )
    ]
    return rec


def run_recommendation(symbol: str, user_id: str) -> FinalRecommendation:
    settings = get_settings()
    if settings.app_env.lower() in {"test", "ci"}:
        return run_heuristic_recommendation(symbol, user_id)
    if settings.ollama_agent_enabled or (settings.gemini_agent_enabled and settings.gemini_api_key):
        try:
            return run_llm_recommendation(symbol, user_id)
        except Exception as exc:  # pragma: no cover
            logging.warning("Falling back to heuristic recommendation path: %s", exc)
            llm_failure = f"{type(exc).__name__}: {exc}"
            return run_heuristic_recommendation(symbol, user_id, llm_failure=llm_failure)

    return run_heuristic_recommendation(symbol, user_id)
