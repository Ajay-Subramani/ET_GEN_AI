from app.graph import run_recommendation


def test_graph_returns_recommendation():
    result = run_recommendation("TATASTEEL", "demo_moderate")
    assert result.symbol == "TATASTEEL"
    assert result.action in {"BUY", "WATCH", "AVOID"}
    assert result.confidence_pct >= 0
    assert result.target_price >= result.entry_price
