from app.graph import run_recommendation
from app.repository import Repository


def test_graph_returns_recommendation():
    result = run_recommendation("TATASTEEL", "demo_moderate")
    assert result.symbol == "TATASTEEL"
    assert result.action in {"BUY", "WATCH", "AVOID"}
    assert result.confidence_pct >= 0
    assert result.target_price >= result.entry_price
    assert result.conviction_mode in {"HIGH_CONVICTION", "ALIGNED", "NORMAL"}
    assert result.analyst_note
    assert result.watch_next
    assert result.setup_memory.similar_setups >= 0
    assert result.setup_memory.source in {"demo", "supabase"}
    assert result.execution_mode in {"heuristic", "llm_tool_agent"}
    assert isinstance(result.agent_trace, list)


def test_record_outcome_updates_demo_memory():
    repo = Repository()
    signal_stack = ["bulk_deal", "delivery_spike", "oi_buildup"]
    before = repo.get_setup_memory("TATASTEEL", "breakout", "neutral", signal_stack)

    repo.record_outcome(
        {
            "user_id": "demo_moderate",
            "symbol": "TATASTEEL",
            "pattern_name": "breakout",
            "action": "BUY",
            "market_condition": "neutral",
            "signal_stack": signal_stack,
            "entry_price": 133.0,
            "target_price": 149.0,
            "stop_loss": 126.0,
            "outcome_return_pct": 13.1,
            "outcome_horizon_days": 16,
            "outcome_label": "win",
        }
    )

    after = repo.get_setup_memory("TATASTEEL", "breakout", "neutral", signal_stack)
    assert after.exact_matches >= before.exact_matches
    assert after.success_rate >= before.success_rate
