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


def run_heuristic_recommendation(symbol: str, user_id: str) -> FinalRecommendation:
    app = build_graph()
    result = app.invoke({"symbol": symbol.upper(), "user_id": user_id})
    return result["recommendation"]


def run_recommendation(symbol: str, user_id: str) -> FinalRecommendation:
    settings = get_settings()
    if settings.gemini_agent_enabled and settings.gemini_api_key:
        try:
            return run_llm_recommendation(symbol, user_id)
        except Exception as exc:  # pragma: no cover
            logging.warning("Falling back to heuristic recommendation path: %s", exc)

    return run_heuristic_recommendation(symbol, user_id)
